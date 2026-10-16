import ast, asyncio, copy, unittest, uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from datetime import datetime, timezone
from test_edit_jobs import Collection, HTTPException
from test_krai_edit_wait import ns as provider_ns, ProviderRequestError, Timeout, response

ROOT=Path(__file__).resolve().parents[1]
class ProviderEditError(Exception):
 def __init__(self,provider='',model='',reason='',code='',status_code=503): self.code=code;self.reason=reason;super().__init__(reason)
class Photos(Collection):
 async def update_one(self,q,u):
  before=await self.find_one(q);r=await super().update_one(q,u)
  for row in self.rows:
   if before and row['id']==before['id']:
    for key in u.get('$unset',{}):row.pop(key,None)
  r.matched_count=int(before is not None);return r

def routes(names):
 tree=ast.parse((ROOT/'server.py').read_text());nodes=[n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name in names]
 for n in nodes:
  n.decorator_list=[];n.returns=None;n.args.defaults=[ast.Constant(None) for _ in n.args.defaults]
  for a in n.args.args:a.annotation=None
 return compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),'actual-server','exec')

class RecoveryTests(unittest.IsolatedAsyncioTestCase):
 async def test_failed_second_pass_resumes_saved_first_pass_only(self):
  photo={'id':'p','user_id':'u','current_path':'original','original_path':'original','status':'processing','edit_job_id':'j','edits':[]}
  photos=Photos([photo]);objects={'original':b'original'};calls=[]
  def edit(*args):
   calls.append(args[2]);
   if len(calls)==2:raise ProviderRequestError('provider_browser',503,'browser failed')
   return b'first-pass' if len(calls)==1 else b'final-result'
  def put(path,data,mime):objects[path]=data;return {'path':path}
  async def override(action):return ({'id':'provider','base_url':'gateway'},'chatgpt-kiko')
  async def log(*a,**kw):pass
  env={'db':SimpleNamespace(photos=photos),'asyncio':asyncio,'uuid':uuid,'datetime':datetime,'timezone':timezone,'get_tool_override':override,'ProviderEditError':ProviderEditError,'log_usage':log,'logger':SimpleNamespace(exception=lambda *a:None),
  'ai_providers':SimpleNamespace(is_krai_gateway=lambda x:True,run_image_edit=edit,image_mime=lambda x:'image/png',ProviderRequestError=ProviderRequestError),
  'ai_edit':SimpleNamespace(build_prompt=lambda *a:'full prompt',_validate_complete_result=lambda *a:None,PERSPECTIVE_ONLY_PROMPT='perspective',ACTIONS={'auto_pro':{'cost':0,'label':'Pro','disclosure_default':False}}),
  'storage':SimpleNamespace(APP_NAME='app',get_object=lambda path:(objects[path],'image/png'),put_object=put)}
  exec(routes({'_apply_edit'}),env)
  with self.assertRaises(ProviderEditError):await env['_apply_edit'](copy.deepcopy(photo),'auto_pro',{},None)
  stored=photos.rows[0];self.assertEqual(stored['current_path'],'original');self.assertEqual(len(stored['edits']),0);self.assertIn('edit_stage',stored)
  stored.update(status='processing',edit_job_id='new-job')
  final=await env['_apply_edit'](copy.deepcopy(stored),'auto_pro',{},None)
  self.assertEqual(calls,[b'original',b'first-pass',b'first-pass']);self.assertEqual(objects[final['current_path']],b'final-result');self.assertNotIn('edit_stage',final);self.assertEqual(len(final['edits']),1)
 async def test_remaining_excludes_saved_and_checkpointed_and_foreign(self):
  job={'id':'j','user_id':'u','property_id':'prop','kind':'batch_edit','status':'interrupted','action':'auto_pro','photo_ids':['a','b','c','d'],'completed_photo_ids':['d']}
  rows=[{'id':i,'property_id':'prop','user_id':'u','edits':[{'job_id':'j'}] if i=='a' else []} for i in 'abcd']
  env={'db':SimpleNamespace(jobs=Collection([job]),photos=Collection(rows)),'HTTPException':HTTPException}
  exec(routes({'batch_remaining'}),env)
  result=await env['batch_remaining']('j',{'user_id':'u'});self.assertEqual(result['photo_ids'],['b','c']);self.assertEqual(result['completed'],2)
  with self.assertRaises(HTTPException):await env['batch_remaining']('j',{'user_id':'other'})
 def test_rate_limit_cooldown_bounded(self):
  calls=[]
  def post(*a,**kw):calls.append(kw);return response(429 if len(calls)<3 else 200)
  provider_ns['requests']=SimpleNamespace(post=post,Timeout=Timeout)
  with patch('time.sleep') as sleep:provider_ns['_krai_edit']('https://invalid','unused','model',b'input','prompt')
  self.assertEqual([c.args[0] for c in sleep.call_args_list],[30,60]);self.assertEqual(len(calls),3)
 def test_safe_machine_code_survives_detail_envelope(self):
  for code in ['session_unavailable','upstream_error','unchanged_image']:
   r=SimpleNamespace(status_code=502,json=lambda:{'detail':{'code':code,'message':'secret must not surface'}})
   with self.assertRaises(ProviderRequestError) as e:provider_ns['_check_edit_response'](r)
   self.assertNotIn('secret',str(e.exception));self.assertNotEqual(e.exception.code,'provider_unavailable')
if __name__=='__main__':unittest.main()
