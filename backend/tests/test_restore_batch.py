import ast, asyncio, copy, unittest
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime, timezone

class HTTPException(Exception):
    def __init__(self, status_code, detail): self.status_code=status_code; self.detail=detail

def matches(row, query):
    for key, value in query.items():
        actual=row.get(key)
        if isinstance(value, dict):
            if '$ne' in value and actual == value['$ne']: return False
            if '$in' in value and actual not in value['$in']: return False
            if '$nin' in value and actual in value['$nin']: return False
        elif actual != value: return False
    return True

class Collection:
    def __init__(self, rows): self.rows=copy.deepcopy(rows); self.race=False
    async def find_one(self, query, projection=None):
        return next((copy.deepcopy(p) for p in self.rows if matches(p,query)),None)
    def find(self, query, projection=None):
        async def to_list(limit): return [copy.deepcopy(p) for p in self.rows if matches(p,query)]
        return SimpleNamespace(to_list=to_list)
    async def update_one(self, query, update):
        if self.race:
            self.rows[0]['status']='processing'; self.race=False
        for p in self.rows:
            if matches(p,query):
                p.update(copy.deepcopy(update.get('$set',{})))
                for k,v in update.get('$push',{}).items(): p.setdefault(k,[]).append(copy.deepcopy(v))
                return SimpleNamespace(modified_count=1)
        return SimpleNamespace(modified_count=0)

source=ast.parse(Path(__file__).resolve().parents[1].joinpath('server.py').read_text())
nodes=[n for n in source.body if isinstance(n,ast.AsyncFunctionDef) and n.name in {'_restore_photo_original','restore_batch'}]
for n in nodes:
    n.decorator_list=[]
    n.args.defaults=[ast.Constant(None) for _ in n.args.defaults]
ns={'HTTPException':HTTPException,'datetime':datetime,'timezone':timezone}
exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),'restore-routes','exec'),ns)

def photo(id='a',**kw):
    return {**dict(id=id,property_id='prop',user_id='owner',original_path='original/'+id,current_path='edit/'+id,edits=[{'action':'auto_pro'}],disclosure=True,status='ready'),**kw}

class RestoreTests(unittest.IsolatedAsyncioTestCase):
    def setup_db(self, photos=None, jobs=None, owner='owner'):
        db=SimpleNamespace(properties=Collection([{'id':'prop','user_id':owner}]),photos=Collection(photos or []),jobs=Collection(jobs or []));ns['db']=db;return db
    async def run_restore(self): return await ns['restore_batch']('prop',{'user_id':'owner'})
    async def test_all_visible_restored_and_history_preserved(self):
        db=self.setup_db([photo(),photo('b'),photo('deleted',is_deleted=True),photo('other',property_id='other')])
        result=await self.run_restore();self.assertEqual(result,{'restored':2,'skipped':0,'total':2})
        for p in db.photos.rows[:2]:
            self.assertEqual(p['current_path'],p['original_path']);self.assertEqual(p['edits'],[]);self.assertFalse(p['disclosure']);self.assertEqual(len(p['restore_archive']),1)
        self.assertEqual(db.photos.rows[2]['current_path'],'edit/deleted');self.assertEqual(db.photos.rows[3]['current_path'],'edit/other')
        self.assertEqual((await self.run_restore())['restored'],0)
    async def test_foreign_property_rejected(self):
        self.setup_db([photo()],owner='other')
        with self.assertRaises(HTTPException) as e: await self.run_restore()
        self.assertEqual(e.exception.status_code,404)
    async def test_active_batch_blocks_all_restores(self):
        db=self.setup_db([photo()],jobs=[{'property_id':'prop','user_id':'owner','status':'processing'}])
        with self.assertRaises(HTTPException) as e: await self.run_restore()
        self.assertEqual(e.exception.status_code,409);self.assertEqual(db.photos.rows[0]['current_path'],'edit/a')
    async def test_active_photo_blocks_all_restores(self):
        p=photo();p['status']='processing';db=self.setup_db([photo('b'),p])
        with self.assertRaises(HTTPException): await self.run_restore()
        self.assertEqual(db.photos.rows[0]['current_path'],'edit/b')
    async def test_queued_photo_blocks_restore(self):
        self.setup_db([photo(status='queued')])
        with self.assertRaises(HTTPException) as e: await self.run_restore()
        self.assertEqual(e.exception.status_code,409)
    async def test_new_edit_race_is_not_overwritten(self):
        db=self.setup_db([photo()]);db.photos.race=True
        self.assertEqual(await self.run_restore(),{'restored':0,'skipped':1,'total':1})
        self.assertEqual(db.photos.rows[0]['status'],'processing');self.assertEqual(db.photos.rows[0]['current_path'],'edit/a')
    async def test_empty_property_is_safe(self):
        self.setup_db();self.assertEqual(await self.run_restore(),{'restored':0,'skipped':0,'total':0})

if __name__=='__main__': unittest.main()
