import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from fastapi import HTTPException
import ai_edit


def subject(db=None):
    tree = ast.parse(Path(__file__).resolve().parents[1].joinpath("server.py").read_text())
    nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in {"_can_undo_photo", "_photo_undo_state", "_photo_public", "undo_photo"}]
    for node in nodes:
        node.decorator_list = []
    ns = {"HTTPException": HTTPException, "Depends": lambda f: None, "current_user": lambda: None, "db": db}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "server-photo-history", "exec"), ns)
    return ns


def edited_photo():
    return {"id": "photo", "property_id": "property", "user_id": "owner", "original_path": "original.jpg", "current_path": "second.jpg", "status": "ready", "disclosure": True,
            "edits": [{"action": "complete", "before_path": "original.jpg", "before_disclosure": False, "disclosure": True}, {"action": "light", "before_path": "first.jpg", "before_disclosure": True, "disclosure": False}]}


def test_undo_only_last_step_then_original():
    ns = subject()
    photo = edited_photo()
    state = ns["_photo_undo_state"](photo)
    assert state["current_path"] == "first.jpg"
    assert state["disclosure"] is True
    assert state["edits"] == photo["edits"][:1]
    restored = {**photo, **state}
    state = ns["_photo_undo_state"](restored)
    assert state["current_path"] == "original.jpg"
    assert state["disclosure"] is False
    assert state["edits"] == []
    assert not ns["_can_undo_photo"]({**photo, **state})


def test_legacy_single_edit_can_return_to_known_original():
    p = edited_photo()
    p["edits"] = [{"action": "complete"}]
    assert subject()["_photo_undo_state"](p)["current_path"] == "original.jpg"


def test_unknown_legacy_intermediate_is_not_fabricated():
    p = edited_photo()
    p["edits"] = [{"action": "complete"}, {"action": "light"}]
    ns = subject()
    assert not ns["_can_undo_photo"](p)
    with pytest.raises(HTTPException) as err:
        ns["_photo_undo_state"](p)
    assert err.value.status_code == 409


def test_empty_history_cannot_be_undone():
    p = edited_photo()
    p["edits"] = []
    with pytest.raises(HTTPException) as err:
        subject()["_photo_undo_state"](p)
    assert err.value.status_code == 409


def test_endpoint_persists_previous_version_without_ai_or_credit_calls():
    photo = edited_photo()
    db = SimpleNamespace(photos=SimpleNamespace(find_one=AsyncMock(return_value=photo), update_one=AsyncMock(return_value=SimpleNamespace(modified_count=1))))
    result = asyncio.run(subject(db)["undo_photo"]("photo", {"user_id": "owner"}))
    assert result["current_path"] == "first.jpg"
    assert result["can_undo"] is True
    query, update = db.photos.update_one.call_args.args
    assert query["user_id"] == "owner"
    assert query["current_path"] == "second.jpg"
    assert query["edits"] == photo["edits"]
    assert update["$set"]["edits"] == photo["edits"][:1]


@pytest.mark.parametrize("processing, modified", [(True, 1), (False, 0)])
def test_endpoint_blocks_processing_and_concurrent_changes(processing, modified):
    photo = edited_photo()
    if processing:
        photo["status"] = "processing"
    db = SimpleNamespace(photos=SimpleNamespace(find_one=AsyncMock(return_value=photo), update_one=AsyncMock(return_value=SimpleNamespace(modified_count=modified))))
    with pytest.raises(HTTPException) as err:
        asyncio.run(subject(db)["undo_photo"]("photo", {"user_id": "owner"}))
    assert err.value.status_code == 409
    if processing:
        db.photos.update_one.assert_not_awaited()


def test_endpoint_checks_owner_and_excludes_deleted_photos():
    db = SimpleNamespace(photos=SimpleNamespace(find_one=AsyncMock(return_value=None), update_one=AsyncMock()))
    with pytest.raises(HTTPException) as err:
        asyncio.run(subject(db)["undo_photo"]("photo", {"user_id": "someone-else"}))
    assert err.value.status_code == 404
    query = db.photos.find_one.call_args.args[0]
    assert query["user_id"] == "someone-else"
    assert query["is_deleted"] == {"$ne": True}
    db.photos.update_one.assert_not_awaited()


@pytest.mark.parametrize("action", ["complete", "auto_pro"])
def test_sunny_exterior_and_white_window_exceptions_are_explicit(action):
    prompt = ai_edit.build_prompt(action, {}).lower()
    assert "gradient" in prompt
    assert "sunny" in prompt
    assert "never invent a landscape" in prompt
    assert "never replace the sky, weather" not in prompt
