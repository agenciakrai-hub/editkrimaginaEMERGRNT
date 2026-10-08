import ast
import asyncio
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from datetime import datetime, timezone
from fastapi import HTTPException, BackgroundTasks

class ProviderEditError(Exception):
    reason = "KRAI no respondió"

class AsyncPhotoTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        tree = ast.parse(Path(__file__).resolve().parents[1].joinpath("server.py").read_text())
        names = {"start_photo_edit", "_refund_photo_edit", "_process_photo_edit", "_recover_photo_edit_jobs"}
        functions = [n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name in names]
        for fn in functions:
            fn.decorator_list = []
            fn.args.defaults = []
            for arg in fn.args.args: arg.annotation = None
        self.photo = {"id": "p", "user_id": "u", "property_id": "home", "status": "ready", "current_path": "original.jpg", "edits": []}
        self.db = SimpleNamespace(
            photos=SimpleNamespace(find_one=AsyncMock(return_value=self.photo.copy()), update_one=AsyncMock(return_value=SimpleNamespace(modified_count=1))),
            jobs=SimpleNamespace(find_one=AsyncMock(return_value={"id":"j", "user_id":"u", "charge":1}), insert_one=AsyncMock(), update_one=AsyncMock(), find=Mock()),
            users=SimpleNamespace(update_one=AsyncMock(return_value=SimpleNamespace(modified_count=1))))
        self.apply = AsyncMock()
        self.env = {"db":self.db, "HTTPException":HTTPException, "uuid":uuid, "datetime":datetime, "timezone":timezone, "is_owner":lambda u:False, "ai_edit":SimpleNamespace(ACTIONS={"auto_pro":{"cost":1,"label":"Pro"}}), "_apply_edit":self.apply, "logger":Mock(), "ProviderEditError":ProviderEditError}
        exec(compile(ast.Module(body=functions,type_ignores=[]),"async_photo","exec"), self.env)
        self.data = SimpleNamespace(action="auto_pro",options={"keep":True},disclosure=False)
        self.background = Mock()
    async def test_start_returns_before_slow_provider_and_schedules_same_pipeline(self):
        result = await self.env["start_photo_edit"]("p",self.data,self.background,{"user_id":"u"})
        self.assertEqual(result["status"],"processing")
        self.apply.assert_not_awaited()
        self.background.add_task.assert_called_once()
        job = self.db.jobs.insert_one.call_args.args[0]
        self.assertNotIn("property_id",job)  # single edits must not replace latest batch history
        self.assertEqual(job["photo_id"],"p")
        task_args = self.background.add_task.call_args.args
        await task_args[0](*task_args[1:])
        self.apply.assert_awaited_once()
        self.assertEqual(self.apply.call_args.args[1:],("auto_pro",{"keep":True},False))
    async def test_duplicate_start_reuses_job_without_charging_or_editing(self):
        self.db.photos.find_one.return_value={**self.photo,"status":"processing","edit_job_id":"j"}
        self.db.jobs.find_one.return_value={"id":"j","status":"processing"}
        result=await self.env["start_photo_edit"]("p",self.data,self.background,{"user_id":"u"})
        self.assertEqual(result["job_id"],"j")
        self.db.users.update_one.assert_not_awaited()
        self.background.add_task.assert_not_called()
    async def test_foreign_photo_cannot_start(self):
        self.db.photos.find_one.return_value=None
        with self.assertRaises(HTTPException): await self.env["start_photo_edit"]("p",self.data,self.background,{"user_id":"u"})
        self.db.jobs.insert_one.assert_not_awaited()
    async def test_concurrent_claim_loser_does_not_charge(self):
        self.db.photos.update_one.return_value=SimpleNamespace(modified_count=0)
        with self.assertRaises(HTTPException): await self.env["start_photo_edit"]("p",self.data,self.background,{"user_id":"u"})
        self.db.users.update_one.assert_not_awaited()
    async def test_insufficient_credit_never_schedules_provider(self):
        self.db.users.update_one.return_value=SimpleNamespace(modified_count=0)
        with self.assertRaises(HTTPException) as exc: await self.env["start_photo_edit"]("p",self.data,self.background,{"user_id":"u"})
        self.assertEqual(exc.exception.status_code,402)
        self.background.add_task.assert_not_called()
    async def test_failure_keeps_source_and_refund_is_guarded_by_charge_marker(self):
        self.apply.side_effect=ProviderEditError()
        await self.env["_process_photo_edit"]("j",{**self.photo,"edit_job_id":"j"},self.data)
        refund=self.db.users.update_one.call_args
        self.assertEqual(refund.args[0],{"user_id":"u","photo_edit_charges":"j"})
        self.assertEqual(refund.args[1]["$inc"],{"credits":1})
        self.assertEqual(self.db.jobs.update_one.call_args.args[1]["$set"]["status"],"failed")
        self.assertTrue(all("current_path" not in call.args[1].get("$set",{}) for call in self.db.photos.update_one.call_args_list))
    async def test_restarting_after_saved_edit_does_not_refund_or_lose_result(self):
        self.db.jobs.find.return_value=SimpleNamespace(to_list=AsyncMock(return_value=[{"id":"j","photo_id":"p","user_id":"u","charge":1}]))
        self.db.photos.find_one.return_value={**self.photo,"edits":[{"job_id":"j"}]}
        await self.env["_recover_photo_edit_jobs"]()
        self.assertEqual(self.db.jobs.update_one.call_args.args[1]["$set"]["status"],"done")
        self.assertNotIn("$inc",self.db.users.update_one.call_args.args[1])
    async def test_restarting_unfinished_edit_refunds_once_and_reports_interruption(self):
        self.db.jobs.find.return_value=SimpleNamespace(to_list=AsyncMock(return_value=[{"id":"j","photo_id":"p","user_id":"u","charge":1}]))
        await self.env["_recover_photo_edit_jobs"]()
        self.assertEqual(self.db.jobs.update_one.call_args.args[1]["$set"]["status"],"interrupted")
        self.assertEqual(self.db.users.update_one.call_args.args[0]["photo_edit_charges"],"j")
