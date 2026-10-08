import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
import ai_edit


def test_interior_has_no_sunny_exterior_grade():
    p = ai_edit.build_prompt("complete", {}).lower()
    assert "pure neutral white" in p
    assert "printed floral fabric is not clutter" in p
    assert "not a blank white rectangle" in p
    assert "never cream, beige, ivory or yellow" in p
    assert "leave these surfaces empty" in p
    assert "recover highlights" in p
    assert "no interior sky replacement or added sunlight" in p
    assert "replace an existing grey/rainy sky" not in p
    assert p == ai_edit.ACTIONS["complete"]["prompt"].lower()


def test_exterior_is_independent_and_available():
    p = ai_edit.build_prompt("complete_exterior", {}).lower()
    assert "clear sunny day" in p
    assert "clean neutral white" in p
    assert "exact original open/closed state" in p
    assert "no local stretching" in p
    assert ai_edit.ACTIONS["complete_exterior"]["cost"] == ai_edit.ACTIONS["complete"]["cost"]
    assert p != ai_edit.build_prompt("complete", {}).lower()


@pytest.mark.parametrize("explicit", [False, True])
def test_exterior_inherits_selected_krai_unless_explicitly_assigned(explicit):
    src = ast.parse(Path("backend/server.py").read_text())
    node = next(n for n in src.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "get_tool_override")
    overrides = {"complete": {"provider_id": "krai", "model_id": "gemini-image"}}
    if explicit:
        overrides["complete_exterior"] = {"provider_id": "krai-exterior", "model_id": "gemini-image"}
    db = SimpleNamespace(ai_settings=SimpleNamespace(find_one=AsyncMock(return_value={"overrides":overrides})), ai_providers=SimpleNamespace(find_one=AsyncMock(return_value={"id":"selected","status":"valid","models":[{"id":"gemini-image"}]})))
    ns={"db":db,"ai_providers":SimpleNamespace(_ensure_caps=lambda m:{"image_edit":True})}
    exec(compile(ast.Module(body=[node],type_ignores=[]),"route","exec"),ns)
    _,model = asyncio.run(ns["get_tool_override"]("complete_exterior"))
    assert model == "gemini-image"
    assert db.ai_providers.find_one.call_args.args[0]["id"] == ("krai-exterior" if explicit else "krai")
