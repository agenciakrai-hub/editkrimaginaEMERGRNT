"""Watchful backend API tests.

Covers auth, actions catalogue, properties CRUD, photo upload,
file serving, free & paid AI edits, insufficient credits, revert,
batch edit + job polling.
"""
import io
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get("REACT_APP_BACKEND_URL") else "https://property-video-ai-3.preview.emergentagent.com"
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@watchful.app"
ADMIN_PASS = "Watchful2026!"

# Tiny 1x1 PNG
PNG_1x1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?"
    b"\x00\x05\xfe\x02\xfe\xdc\xccY\xe7\x00\x00\x00\x00IEND\xaeB`\x82"
)


# Use bare requests (no session) to avoid cookie leaking between users;
# backend's auth resolver prefers cookies over Authorization Bearer.
s = requests  # module-level alias for calls inside tests


@pytest.fixture(scope="session")
def s():  # noqa: F811 - fixture named 's' so test signatures keep working
    return requests


@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="session")
def user_ctx():
    email = f"test_user_{uuid.uuid4().hex[:8]}@watchful.app"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": "Test2026!", "name": "Test User"}, timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["credits"] == 30
    return {"email": email, "token": body["token"], "user_id": body["user"]["user_id"]}


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


# ---------- Auth ----------
def test_admin_login(admin_token):
    assert admin_token


def test_register_returns_30_credits(user_ctx):
    assert user_ctx["token"]


def test_me(s, user_ctx):
    r = s.get(f"{API}/auth/me", headers=_h(user_ctx["token"]), timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert data["email"] == user_ctx["email"]
    assert data["credits"] == 30


def test_login_wrong_password(s):
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong"}, timeout=15)
    assert r.status_code == 401


# ---------- Actions ----------
def test_actions_catalogue(s):
    r = s.get(f"{API}/actions", timeout=15)
    assert r.status_code == 200
    actions = {a["key"]: a for a in r.json()}
    assert len(actions) == 9
    assert actions["sky"]["cost"] == 0
    assert actions["light"]["cost"] == 0
    assert actions["straighten"]["cost"] == 0
    assert actions["twilight"]["cost"] == 2
    assert actions["staging"]["cost"] == 3
    assert actions["declutter"]["cost"] == 2
    assert actions["lawn"]["cost"] == 1
    assert actions["window_pull"]["cost"] == 2
    assert actions["upscale"]["cost"] == 1


# ---------- Properties CRUD ----------
@pytest.fixture(scope="session")
def property_id(s, user_ctx):
    r = s.post(f"{API}/properties", json={"name": "TEST_Casa", "address": "Calle 1"}, headers=_h(user_ctx["token"]), timeout=20)
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    yield pid
    s.delete(f"{API}/properties/{pid}", headers=_h(user_ctx["token"]), timeout=15)


def test_list_properties(s, user_ctx, property_id):
    r = s.get(f"{API}/properties", headers=_h(user_ctx["token"]), timeout=15)
    assert r.status_code == 200
    assert any(p["id"] == property_id for p in r.json())


def test_get_property(s, user_ctx, property_id):
    r = s.get(f"{API}/properties/{property_id}", headers=_h(user_ctx["token"]), timeout=15)
    assert r.status_code == 200
    assert r.json()["name"] == "TEST_Casa"


def test_property_scoped_to_user(s, admin_token, property_id):
    r = s.get(f"{API}/properties/{property_id}", headers=_h(admin_token), timeout=15)
    assert r.status_code == 404


# ---------- Photo upload + file serving ----------
@pytest.fixture(scope="session")
def photo(user_ctx, property_id):
    files = {"files": ("test.png", io.BytesIO(PNG_1x1), "image/png")}
    r = requests.post(f"{API}/properties/{property_id}/photos", files=files, headers=_h(user_ctx["token"]), timeout=60)
    assert r.status_code == 200, r.text
    photos = r.json()
    assert len(photos) == 1
    assert photos[0]["status"] == "ready"
    return photos[0]


def test_photo_listed(s, user_ctx, property_id, photo):
    r = s.get(f"{API}/properties/{property_id}/photos", headers=_h(user_ctx["token"]), timeout=15)
    assert r.status_code == 200
    assert any(p["id"] == photo["id"] for p in r.json())


def test_file_serving(s, user_ctx, photo):
    r = s.get(f"{API}/files/{photo['original_path']}", params={"token": user_ctx["token"]}, timeout=30)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/")
    assert len(r.content) > 0


def test_file_serving_no_auth(photo):
    # Bare request (no cookies), no Authorization -> 401
    r = requests.get(f"{API}/files/{photo['original_path']}", timeout=15)
    assert r.status_code == 401


# ---------- Insufficient credits ----------
def test_insufficient_credits(s, user_ctx, photo):
    """Deplete then try paid edit. We fabricate by requesting staging (cost=3) 10x is expensive.
       Instead just create a fresh user with 0 credits by setting credits via a second register+drain.
       Simpler: try a huge batch cost by calling paid staging with a fresh 0-credit scenario:
       We'll register another user, admin-set is not exposed. So skip if we can't force it easily —
       we test 402 via the batch endpoint with more credits needed than available."""
    # Create fresh user
    email = f"TEST_zero_{uuid.uuid4().hex[:6]}@w.app"
    reg = s.post(f"{API}/auth/register", json={"email": email, "password": "Pass2026!", "name": "Z"}, timeout=20).json()
    tok = reg["token"]
    # Property + upload photo
    pid = s.post(f"{API}/properties", json={"name": "TEST_Z", "address": ""}, headers=_h(tok), timeout=15).json()["id"]
    files = {"files": ("t.png", io.BytesIO(PNG_1x1), "image/png")}
    photo_z = s.post(f"{API}/properties/{pid}/photos", files=files, headers=_h(tok), timeout=30).json()[0]
    # Deplete via batch of many photos would require many edits. Instead, brute-force staging (cost 3) 10 times => 30 credits gone.
    # But we don't want to run 10 real AI edits. Rely on batch reservation only: batch of N will need N*cost credits upfront.
    # Duplicate uploads is easier: upload 20 tiny photos, then request staging batch -> requires 60 credits vs 30 => 402.
    for _ in range(19):
        s.post(f"{API}/properties/{pid}/photos", files={"files": ("t.png", io.BytesIO(PNG_1x1), "image/png")}, headers=_h(tok), timeout=30)
    r = s.post(f"{API}/properties/{pid}/batch", json={"action": "staging"}, headers=_h(tok), timeout=20)
    assert r.status_code == 402, f"expected 402, got {r.status_code}: {r.text}"
    assert "crédito" in r.text.lower() or "credit" in r.text.lower()
    # cleanup
    s.delete(f"{API}/properties/{pid}", headers=_h(tok), timeout=15)


# ---------- Free AI edit (real Gemini call) ----------
def test_free_edit_sky(s, user_ctx, photo):
    r = s.post(f"{API}/photos/{photo['id']}/edit", json={"action": "sky"}, headers=_h(user_ctx["token"]), timeout=120)
    if r.status_code == 500:
        pytest.skip(f"Gemini image edit failed (likely upstream issue): {r.text[:200]}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["credits"] == 30  # free
    p = body["photo"]
    assert p["current_path"] != photo["original_path"]
    assert len(p["edits"]) >= 1
    assert p["edits"][-1]["action"] == "sky"
    # both original and current retrievable
    r_o = s.get(f"{API}/files/{p['original_path']}", params={"token": user_ctx["token"]}, timeout=30)
    r_c = s.get(f"{API}/files/{p['current_path']}", params={"token": user_ctx["token"]}, timeout=30)
    assert r_o.status_code == 200 and r_c.status_code == 200


# ---------- Revert ----------
def test_revert(s, user_ctx, photo):
    r = s.post(f"{API}/photos/{photo['id']}/revert", headers=_h(user_ctx["token"]), timeout=15)
    assert r.status_code == 200
    p = r.json()
    assert p["current_path"] == photo["original_path"]
    assert p["edits"] == []


# ---------- Paid edit (twilight cost 2) ----------
def test_paid_edit_deducts_credits(s, user_ctx, photo):
    before = s.get(f"{API}/auth/me", headers=_h(user_ctx["token"]), timeout=15).json()["credits"]
    r = s.post(f"{API}/photos/{photo['id']}/edit", json={"action": "twilight"}, headers=_h(user_ctx["token"]), timeout=120)
    if r.status_code == 500:
        pytest.skip(f"Gemini twilight failed: {r.text[:200]}")
    assert r.status_code == 200, r.text
    assert r.json()["credits"] == before - 2
    me = s.get(f"{API}/auth/me", headers=_h(user_ctx["token"]), timeout=15).json()
    assert me["credits"] == before - 2


# ---------- Batch ----------
def test_batch_free_action(s, user_ctx, property_id, photo):
    # revert first
    s.post(f"{API}/photos/{photo['id']}/revert", headers=_h(user_ctx["token"]), timeout=15)
    r = s.post(f"{API}/properties/{property_id}/batch", json={"action": "light"}, headers=_h(user_ctx["token"]), timeout=20)
    assert r.status_code == 200, r.text
    job_id = r.json()["job_id"]
    # Poll job
    for _ in range(40):
        j = s.get(f"{API}/jobs/{job_id}", headers=_h(user_ctx["token"]), timeout=15).json()
        if j.get("status") == "done":
            break
        time.sleep(3)
    assert j["status"] == "done"
    assert j["processed"] == j["total"]
