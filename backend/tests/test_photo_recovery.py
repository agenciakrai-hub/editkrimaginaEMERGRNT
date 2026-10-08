import ast
import unittest
from pathlib import Path
from unittest.mock import AsyncMock
from types import SimpleNamespace
from fastapi import HTTPException

class RecoveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        tree=ast.parse(Path(__file__).resolve().parents[1].joinpath("server.py").read_text())
        fn=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=="recover_photo")
        fn.decorator_list=[]
        fn.args.defaults=[]
        self.db=SimpleNamespace(properties=SimpleNamespace(find_one=AsyncMock(return_value={"id":"p"})),photos=SimpleNamespace(find_one=AsyncMock(return_value={"id":"x","property_id":"p"}),update_one=AsyncMock()))
        env={"db":self.db,"HTTPException":HTTPException}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),"recover","exec"),env)
        self.recover=env["recover_photo"]
    async def test_recovers_only_owned_deleted_photo_without_changing_edits(self):
        self.assertEqual(await self.recover("x",{"user_id":"u"}),{"ok":True})
        self.db.photos.update_one.assert_awaited_once_with({"id":"x","user_id":"u","is_deleted":True},{"$set":{"is_deleted":False}})
    async def test_foreign_photo_is_rejected(self):
        self.db.photos.find_one.return_value=None
        with self.assertRaises(HTTPException): await self.recover("x",{"user_id":"u"})
        self.db.photos.update_one.assert_not_awaited()
    async def test_deleted_or_foreign_property_is_rejected(self):
        self.db.properties.find_one.return_value=None
        with self.assertRaises(HTTPException): await self.recover("x",{"user_id":"u"})
        self.db.photos.update_one.assert_not_awaited()
