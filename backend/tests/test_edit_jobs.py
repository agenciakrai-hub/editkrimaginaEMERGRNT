import ast, asyncio, copy, sys, unittest
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime, timezone, timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from edit_jobs import clear_failed_jobs, recover_stale_batches, release_batch, settle_batch_photo

class HTTPException(Exception):
    def __init__(self,status_code,detail): self.status_code=status_code; self.detail=detail
class ProviderEditError(Exception):
    def __init__(self,code='provider_timeout',reason='timeout'): self.code=code; self.reason=reason

def match(row,q):
    for k,v in q.items():
        if k=='$or':
            if not any(match(row,t) for t in v): return False
            continue
        a=row.get(k)
        if isinstance(v,dict):
            for op,b in v.items():
                if op=='$in' and a not in b: return False
                if op=='$nin' and a in b: return False
                if op=='$ne' and a==b: return False
                if op=='$exists' and (k in row)!=b: return False
                if op=='$gt' and not(a is not None and a>b): return False
                if op=='$gte' and not(a is not None and a>=b): return False
                if op=='$lt' and not(a is not None and a<b): return False
        elif isinstance(a,list):
            if v not in a: return False
        elif a!=v: return False
    return True
class Collection:
    def __init__(self,rows=()): self.rows=copy.deepcopy(list(rows)); self.race=None
    async def find_one(self,q,projection=None,**kw): return next((copy.deepcopy(r) for r in self.rows if match(r,q)),None)
    def find(self,q,projection=None):
        async def to_list(n): return [copy.deepcopy(r) for r in self.rows if match(r,q)]
        return SimpleNamespace(to_list=to_list)
    async def update_one(self,q,u):
        if self.race: self.race(self); self.race=None
        for r in self.rows:
            if match(r,q):
                before=copy.deepcopy(r);r.update(copy.deepcopy(u.get('$set',{})))
                for k,v in u.get('$inc',{}).items(): r[k]=r.get(k,0)+v
                for k,v in u.get('$pull',{}).items(): r[k]=[x for x in r.get(k,[]) if x!=v]
                for k,v in u.get('$push',{}).items(): r.setdefault(k,[]).append(copy.deepcopy(v))
                for k,v in u.get('$addToSet',{}).items():
                    for x in v.get('$each',[]) if isinstance(v,dict) else [v]:
                        if x not in r.setdefault(k,[]): r[k].append(x)
                return SimpleNamespace(modified_count=int(before!=r))
        return SimpleNamespace(modified_count=0)
    async def update_many(self,q,u):
        count=0
        for row in list(self.rows):
            if match(row,q): count+=(await self.update_one({'id':row.get('id'),**q},u)).modified_count
        return SimpleNamespace(modified_count=count)
    async def insert_one(self,row): self.rows.append(copy.deepcopy(row))

def db(jobs=(),photos=(),users=()): return SimpleNamespace(jobs=Collection(jobs),photos=Collection(photos),users=Collection(users),properties=Collection([{'id':'p','user_id':'u'}]))
def job(**kw): return dict(id='j',property_id='p',user_id='u',kind='batch_edit',photo_ids=['a','b'],unit_cost=1,total=2,processed=0,done=0,failed=0,status='processing',heartbeat_at=datetime.now(timezone.utc).isoformat(),**kw)
def photo(pid='a',**kw): return {**dict(id=pid,user_id='u',property_id='p',status='queued',edit_job_id='j',current_path='original',original_path='original',edits=[]),**kw}
source=ast.parse(Path(__file__).resolve().parents[1].joinpath('server.py').read_text());names={'_process_batch','batch_edit','clear_property_failed_processes'}
nodes=[n for n in source.body if isinstance(n,ast.AsyncFunctionDef) and n.name in names]
for n in nodes:
    n.decorator_list=[];n.returns=None;n.args.defaults=[ast.Constant(None) for _ in n.args.defaults]
    for a in n.args.args: a.annotation=None
ns={'HTTPException':HTTPException,'ProviderEditError':ProviderEditError,'datetime':datetime,'timezone':timezone,'asyncio':asyncio,'settle_batch_photo':settle_batch_photo,'release_batch':release_batch,'clear_failed_jobs':clear_failed_jobs,'logger':SimpleNamespace(exception=lambda *a:None)}
exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),'batch-routes','exec'),ns)

class JobsTests(unittest.IsolatedAsyncioTestCase):
    async def test_terminal_cleanup_keeps_photos_and_newer_locks(self):
        j=job();j.update(status='done',failed=1)
        d=db([j],[photo(),photo('b',edit_job_id='new')])
        self.assertEqual(await clear_failed_jobs(d,{'user_id':'u','property_id':'p'}),1)
        self.assertEqual(d.photos.rows[0]['status'],'ready');self.assertEqual(d.photos.rows[1]['edit_job_id'],'new');self.assertEqual(d.photos.rows[0]['current_path'],'original')
        self.assertEqual(await clear_failed_jobs(d,{'user_id':'u','property_id':'p'}),0)
    async def test_live_and_foreign_jobs_untouched(self):
        foreign=job();foreign.update(id='other',user_id='other',status='failed')
        d=db([job(),foreign],[photo()]);self.assertEqual(await clear_failed_jobs(d,{'user_id':'u','property_id':'p'}),0);self.assertEqual(d.photos.rows[0]['status'],'queued')
    async def test_stale_recovery_refunds_unsaved_only_once(self):
        j=job();j['heartbeat_at']=(datetime.now(timezone.utc)-timedelta(minutes=21)).isoformat()
        a=photo();a['edits']=[{'job_id':'j'}]
        d=db([j],[a,photo('b')],[{'user_id':'u','credits':0,'batch_edit_charges':['j:a','j:b']}])
        self.assertEqual(await recover_stale_batches(d),1);self.assertEqual(d.users.rows[0]['credits'],1);self.assertEqual(d.users.rows[0]['batch_edit_charges'],[])
        await release_batch(d,j);self.assertEqual(d.users.rows[0]['credits'],1)
    async def test_heartbeat_race_prevents_recovery(self):
        j=job();j['heartbeat_at']=(datetime.now(timezone.utc)-timedelta(minutes=21)).isoformat();d=db([j],[photo()])
        d.jobs.race=lambda c:c.rows[0].update(heartbeat_at=datetime.now(timezone.utc).isoformat())
        self.assertEqual(await recover_stale_batches(d),0);self.assertEqual(d.photos.rows[0]['status'],'queued')
    async def run_worker(self,edit):
        d=db([job()],[photo(),photo('b')],[{'user_id':'u','credits':0,'batch_edit_charges':['j:a','j:b']}]);ns.update(db=d,_apply_edit=edit,asyncio=asyncio)
        await ns['_process_batch']('j','u',['a','b'],'auto_pro',{},False,1);return d
    async def test_timeout_stops_other_requests_refunds_and_releases(self):
        calls=[]
        async def edit(p,*args): calls.append(p['id']);raise ProviderEditError()
        d=await self.run_worker(edit);self.assertEqual(calls,['a']);self.assertEqual(d.jobs.rows[0]['status'],'interrupted');self.assertEqual(d.jobs.rows[0]['pending'],1);self.assertEqual(d.users.rows[0]['credits'],2);self.assertTrue(all(p['status']=='ready' for p in d.photos.rows))
    async def test_successes_tagged_and_not_refunded(self):
        async def edit(p,*args):
            await ns['db'].photos.update_one({'id':p['id']},{'$push':{'edits':{'job_id':p['edit_job_id']}},'$set':{'current_path':'edited'}})
        d=await self.run_worker(edit);self.assertEqual(d.jobs.rows[0]['done'],2);self.assertEqual(d.users.rows[0]['credits'],0);self.assertEqual(d.jobs.rows[0]['status'],'done')
    async def test_unexpected_cancel_finally_unlocks_and_refunds(self):
        async def edit(p,*args): raise asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError): await self.run_worker(edit)
        d=ns['db'];self.assertTrue(all(p['status']=='ready' for p in d.photos.rows));self.assertEqual(d.users.rows[0]['credits'],2);self.assertEqual(d.jobs.rows[0]['status'],'interrupted')
    async def test_photo_error_continues_without_losing_success(self):
        async def edit(p,*args):
            if p['id']=='a': raise ProviderEditError('invalid_image_geometry')
            await ns['db'].photos.update_one({'id':'b'},{'$push':{'edits':{'job_id':'j'}}})
        d=await self.run_worker(edit);self.assertEqual(d.jobs.rows[0]['done'],1);self.assertEqual(d.jobs.rows[0]['failed'],1);self.assertEqual(d.users.rows[0]['credits'],1)

class ReservationTests(unittest.IsolatedAsyncioTestCase):
    def prepare(self,photos,credits=2):
        import uuid
        d=db(photos=photos,users=[{'user_id':'u','credits':credits,'batch_edit_charges':[]}]);ns.update(db=d,uuid=uuid,is_owner=lambda u:False,ai_edit=SimpleNamespace(ACTIONS={'auto_pro':{'cost':1,'label':'Pro'}}))
        async def heartbeat(*args): pass
        def schedule(coro): coro.close()
        ns.update(run_with_heartbeat=heartbeat,asyncio=SimpleNamespace(create_task=schedule))
        return d
    async def start(self):
        return await ns['batch_edit']('p',SimpleNamespace(action='auto_pro',photo_ids=['a','b'],options={},disclosure=False),{'user_id':'u'})
    async def test_all_photos_reserved_before_dispatch_and_charged_once(self):
        d=self.prepare([photo(status='ready',edit_job_id=None),photo('b',status='ready',edit_job_id=None)])
        result=await self.start();self.assertTrue(all(p['status']=='queued' and p['edit_job_id']==result['job_id'] for p in d.photos.rows));self.assertEqual(d.users.rows[0]['credits'],0);self.assertEqual(len(d.users.rows[0]['batch_edit_charges']),2)
    async def test_insufficient_credit_releases_all_reservations(self):
        d=self.prepare([photo(status='ready',edit_job_id=None),photo('b',status='ready',edit_job_id=None)],credits=1)
        with self.assertRaises(HTTPException) as e: await self.start()
        self.assertEqual(e.exception.status_code,402);self.assertTrue(all(p['status']=='ready' and p['edit_job_id'] is None for p in d.photos.rows));self.assertEqual(d.users.rows[0]['credits'],1)
    async def test_competing_photo_lock_is_not_removed(self):
        d=self.prepare([photo(status='ready',edit_job_id=None),photo('b',status='ready',edit_job_id=None)])
        d.photos.race=lambda c:c.rows[1].update(status='processing',edit_job_id='other')
        with self.assertRaises(HTTPException) as e: await self.start()
        self.assertEqual(e.exception.status_code,409);self.assertEqual(d.photos.rows[0]['status'],'ready');self.assertEqual(d.photos.rows[1]['edit_job_id'],'other');self.assertEqual(d.users.rows[0]['credits'],2)
    async def test_already_queued_photo_cannot_start_second_batch(self):
        d=self.prepare([photo(),photo('b')])
        with self.assertRaises(HTTPException) as e: await self.start()
        self.assertEqual(e.exception.status_code,409);self.assertEqual(d.users.rows[0]['credits'],2)
    async def test_cleanup_foreign_property_rejected(self):
        d=self.prepare([]);d.properties.rows[0]['user_id']='other'
        with self.assertRaises(HTTPException) as e: await ns['clear_property_failed_processes']('p',{'user_id':'u'})
        self.assertEqual(e.exception.status_code,404)

if __name__=='__main__': unittest.main()
