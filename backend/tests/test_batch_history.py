import ast
import unittest
from pathlib import Path
from unittest.mock import AsyncMock
from types import SimpleNamespace
from fastapi import HTTPException

class BatchHistoryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        tree=ast.parse(Path(__file__).resolve().parents[1].joinpath('server.py').read_text())
        fn=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='latest_batch')
        fn.decorator_list=[]
        fn.args.defaults=[]
        self.db=SimpleNamespace(properties=SimpleNamespace(find_one=AsyncMock(return_value={'id':'p'})),jobs=SimpleNamespace(find_one=AsyncMock(return_value={'done':18,'failed':21,'error_message':'Provider limit','skipped':20})))
        env={'db':self.db,'HTTPException':HTTPException}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'batch_history','exec'),env)
        self.query=env['latest_batch']
    async def test_scopes_latest_job_to_owned_property_and_keeps_failure_reason(self):
        result=await self.query('p',{'user_id':'u'})
        self.assertEqual(self.db.jobs.find_one.call_args.args[0],{'property_id':'p','user_id':'u'})
        self.assertEqual(self.db.jobs.find_one.call_args.kwargs['sort'],[('created_at',-1)])
        self.assertEqual(result['error_message'],'Provider limit')
    async def test_cannot_read_another_users_batch(self):
        self.db.properties.find_one.return_value=None
        with self.assertRaises(HTTPException): await self.query('foreign',{'user_id':'u'})
        self.db.jobs.find_one.assert_not_awaited()
