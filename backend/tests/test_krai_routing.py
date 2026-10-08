import ast
import asyncio
import io
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Optional
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock
from PIL import Image
import ai_edit


def image(size=(1500, 1000)):
    b = io.BytesIO()
    Image.new("RGB", size, "white").save(b, "JPEG")
    return b.getvalue()


class KraiRoutingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        tree = ast.parse(Path(__file__).resolve().parents[1].joinpath("server.py").read_text())
        nodes = [n for n in tree.body if isinstance(n, (ast.ClassDef, ast.AsyncFunctionDef)) and n.name in {"ProviderEditError", "_apply_edit"}]
        self.data = image()
        self.engine = Mock(return_value=self.data)
        self.fallback = AsyncMock()
        self.lookup = AsyncMock(return_value=({"name": "krai api", "base_url": "krai"}, "gemini-image"))
        self.photos = SimpleNamespace(update_one=AsyncMock(), find_one=AsyncMock(return_value={"id": "photo"}))
        self.store = Mock(return_value={"path":"stored"})
        self.env = dict(asyncio=asyncio, Optional=Optional, uuid=uuid, datetime=datetime, timezone=timezone,
            get_tool_override=self.lookup, db=SimpleNamespace(photos=self.photos),
            ai_edit=SimpleNamespace(ACTIONS=ai_edit.ACTIONS, MODEL="forbidden", run_edit=self.fallback, build_prompt=ai_edit.build_prompt,
                                   _validate_complete_result=ai_edit._validate_complete_result, PERSPECTIVE_ONLY_PROMPT=ai_edit.PERSPECTIVE_ONLY_PROMPT),
            ai_providers=SimpleNamespace(is_krai_gateway=lambda u:u == "krai", run_image_edit=self.engine,
                image_mime=lambda b:"image/jpeg", ProviderRequestError=RuntimeError),
            storage=SimpleNamespace(get_object=Mock(return_value=(self.data,"image/jpeg")), put_object=self.store, APP_NAME="test"),
            local_edit=SimpleNamespace(SUPPORTED={"auto"}, run=Mock()),
            imaging=SimpleNamespace(finalize_edit=Mock()), logger=Mock(), log_usage=AsyncMock())
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "server_routing", "exec"), self.env)
        self.apply = self.env["_apply_edit"]
        self.error = self.env["ProviderEditError"]
        self.photo = {"id":"photo", "user_id":"user", "original_path":"original"}

    async def test_selected_krai_is_used_and_original_bytes_are_stored(self):
        await self.apply(self.photo, "complete", {}, None)
        self.assertEqual(self.engine.call_args.args[1], "gemini-image")
        self.assertEqual(self.store.call_args.args[1], self.data)
        self.env["imaging"].finalize_edit.assert_not_called()
        self.fallback.assert_not_awaited()

    async def test_missing_engine_does_not_use_default_gemini(self):
        self.lookup.return_value = None
        with self.assertRaises(self.error): await self.apply(self.photo,"complete",{},None)
        self.engine.assert_not_called()
        self.fallback.assert_not_awaited()

    async def test_other_provider_is_rejected_before_transmission(self):
        self.lookup.return_value = ({"name":"other", "base_url":"other"}, "model")
        with self.assertRaises(self.error): await self.apply(self.photo,"complete",{},None)
        self.engine.assert_not_called()
        self.fallback.assert_not_awaited()

    async def test_krai_failure_does_not_fall_back(self):
        self.engine.side_effect = RuntimeError("unavailable")
        with self.assertRaises(self.error): await self.apply(self.photo,"complete",{},None)
        self.fallback.assert_not_awaited()
        self.store.assert_not_called()

    async def test_empty_krai_response_is_not_saved_or_retried_elsewhere(self):
        self.engine.return_value = None
        with self.assertRaises(self.error): await self.apply(self.photo,"complete",{},None)
        self.fallback.assert_not_awaited()
        self.store.assert_not_called()

    async def test_changed_proportions_are_rejected_before_storage(self):
        self.engine.return_value = image((1000,1000))
        with self.assertRaises(self.error): await self.apply(self.photo,"complete",{},None)
        self.store.assert_not_called()
        self.fallback.assert_not_awaited()

    async def test_selected_krai_is_respected_on_essential_tool(self):
        await self.apply(self.photo,"auto",{},None)
        self.engine.assert_called_once()
        self.env["local_edit"].run.assert_not_called()
        self.fallback.assert_not_awaited()

    async def test_pro_uses_same_krai_for_dedicated_perspective(self):
        intermediate = image((1200,800))
        final = image((900,600))
        self.engine.side_effect = [intermediate, final]
        await self.apply(self.photo,"auto_pro",{},None)
        self.assertEqual(self.engine.call_count,2)
        self.assertEqual(self.engine.call_args.args[0],self.lookup.return_value[0])
        self.assertEqual(self.engine.call_args.args[1],"gemini-image")
        self.assertEqual(self.engine.call_args.args[2],intermediate)
        self.assertEqual(self.engine.call_args.args[3],ai_edit.PERSPECTIVE_ONLY_PROMPT)
        self.assertEqual(self.store.call_args.args[1],final)
        self.assertEqual(self.env["log_usage"].call_args.kwargs["ai_calls"],2)
        self.photos.update_one.assert_awaited_once()

    async def test_second_pass_failure_does_not_commit_partial_edit(self):
        self.engine.side_effect = [self.data,RuntimeError("perspective failed")]
        with self.assertRaises(self.error): await self.apply(self.photo,"complete",{},None)
        self.store.assert_not_called()
        self.photos.update_one.assert_not_awaited()
        self.fallback.assert_not_awaited()

    async def test_exterior_keeps_approved_single_pass(self):
        await self.apply(self.photo,"complete_exterior",{},None)
        self.engine.assert_called_once()
