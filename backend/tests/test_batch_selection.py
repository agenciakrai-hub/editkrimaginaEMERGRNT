import ast
import asyncio
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock
from fastapi import HTTPException
import ai_edit

class BatchSelectionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        tree=ast.parse(Path(__file__).resolve().parents[1].joinpath("server.py").read_text())
        fn=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=="batch_edit")
        fn.decorator_list=[]
        fn.args.defaults=[]
        fn.args.args[1].annotation=None
        self.photos=SimpleNamespace(find=Mock(return_value=SimpleNamespace(to_list=AsyncMock(return_value=[{"id":"inside"}]))))
        self.db=SimpleNamespace(properties=SimpleNamespace(find_one=AsyncMock(return_value={"id":"property"})),photos=self.photos,jobs=SimpleNamespace(insert_one=AsyncMock()),users=SimpleNamespace(find_one=AsyncMock(),update_one=AsyncMock()))
        self.process=AsyncMock()
        self.schedule=Mock(side_effect=lambda coro:coro.close())
        env=dict(HTTPException=HTTPException,ai_edit=ai_edit,db=self.db,is_owner=lambda u:True,uuid=uuid,datetime=datetime,timezone=timezone,asyncio=SimpleNamespace(create_task=self.schedule),_process_batch=self.process)
        exec(compile(ast.Module(body=[fn],type_ignores=[]),"batch_selection","exec"),env)
        self.run_batch=env["batch_edit"]
    def payload(self,ids):
        return SimpleNamespace(action="complete",photo_ids=ids,options=None,disclosure=None)
    async def test_only_selected_ids_are_queried_and_scheduled(self):
        result=await self.run_batch("property",self.payload(["inside"]),{"user_id":"owner"})
        query=self.photos.find.call_args.args[0]
        self.assertEqual(query["id"],{"$in":["inside"]})
        self.assertEqual(query["property_id"],"property")
        self.assertEqual(result["total"],1)
        self.assertEqual(self.process.call_args.args[2],["inside"])
    async def test_empty_selection_cannot_expand_to_all_photos(self):
        with self.assertRaises(HTTPException): await self.run_batch("property",self.payload([]),{"user_id":"owner"})
        self.photos.find.assert_not_called()
        self.schedule.assert_not_called()
    async def test_missing_or_foreign_ids_reject_entire_selection(self):
        with self.assertRaises(HTTPException): await self.run_batch("property",self.payload(["inside","foreign"]),{"user_id":"owner"})
        self.schedule.assert_not_called()
        self.db.users.update_one.assert_not_awaited()
