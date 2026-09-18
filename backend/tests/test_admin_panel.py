"""Backend tests for the super-admin panel (users/plans/usage/providers/overrides)."""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"

SUPER = {"email": "krimagina2025@gmail.com", "password": "Admin2026!"}
NORMAL = {"email": "agente@watchful.app", "password": "Agente2026!", "name": "Agente"}


def _login_or_register(creds):
    r = requests.post(f"{API}/auth/login", json={"email": creds["email"], "password": creds["password"]})
    if r.status_code == 200:
        return r.json()["token"]
    r = requests.post(f"{API}/auth/register", json=creds)
    assert r.status_code in (200, 201), f"register failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login", json=SUPER)
    assert r.status_code == 200, f"super admin login failed: {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def user_token():
    return _login_or_register(NORMAL)


@pytest.fixture(scope="module")
def ah(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def uh(user_token):
    return {"Authorization": f"Bearer {user_token}"}


# ---------- Access control ----------
def test_admin_users_forbidden_for_normal(uh):
    r = requests.get(f"{API}/admin/users", headers=uh)
    assert r.status_code == 403


def test_admin_users_ok_for_super(ah):
    r = requests.get(f"{API}/admin/users", headers=ah)
    assert r.status_code == 200
    users = r.json()
    assert isinstance(users, list) and any(u["email"] == SUPER["email"] for u in users)


def test_me_super_admin_flag(admin_token):
    r = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    assert r.json().get("is_super_admin") is True


def test_me_normal_user_not_super(user_token):
    r = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {user_token}"})
    assert r.status_code == 200
    assert not r.json().get("is_super_admin")


# ---------- Plans CRUD + public sync ----------
def test_plan_crud_and_public_sync(ah):
    name = f"TEST_Plan_{uuid.uuid4().hex[:6]}"
    r = requests.post(f"{API}/admin/plans", headers=ah, json={
        "name": name, "price_eur": 19.9, "credits": 300, "period": "monthly",
        "features": ["300 créditos", "Soporte"], "highlight": True, "active": True, "sort_order": 99,
    })
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    assert r.json()["name"] == name and r.json()["credits"] == 300

    # public list must include it (active)
    pub = requests.get(f"{API}/plans").json()
    assert any(p["id"] == pid for p in pub)

    # update: set inactive
    r = requests.put(f"{API}/admin/plans/{pid}", headers=ah, json={
        "name": name, "price_eur": 19.9, "credits": 300, "period": "monthly",
        "features": ["300 créditos"], "highlight": False, "active": False, "sort_order": 99,
    })
    assert r.status_code == 200 and r.json()["active"] is False

    # admin still sees it
    admin_plans = requests.get(f"{API}/admin/plans", headers=ah).json()
    assert any(p["id"] == pid for p in admin_plans)
    # public no longer shows it
    pub = requests.get(f"{API}/plans").json()
    assert not any(p["id"] == pid for p in pub)

    # delete
    r = requests.delete(f"{API}/admin/plans/{pid}", headers=ah)
    assert r.status_code == 200
    admin_plans = requests.get(f"{API}/admin/plans", headers=ah).json()
    assert not any(p["id"] == pid for p in admin_plans)


# ---------- Assign plan to user ----------
def test_assign_plan_to_user(ah, user_token):
    # find normal user id
    users = requests.get(f"{API}/admin/users", headers=ah).json()
    target = next(u for u in users if u["email"] == NORMAL["email"])
    uid = target["user_id"]
    before_credits = target["credits"]

    # create plan
    r = requests.post(f"{API}/admin/plans", headers=ah, json={
        "name": "TEST_Assign", "price_eur": 9.9, "credits": 50, "period": "monthly",
        "features": [], "highlight": False, "active": True, "sort_order": 1,
    })
    pid = r.json()["id"]
    try:
        r = requests.post(f"{API}/admin/users/{uid}/plan", headers=ah, json={
            "plan_id": pid, "expires_at": "2030-12-31T00:00:00Z"
        })
        assert r.status_code == 200
        users2 = requests.get(f"{API}/admin/users", headers=ah).json()
        u2 = next(u for u in users2 if u["user_id"] == uid)
        assert u2["plan_id"] == pid and u2["plan_name"] == "TEST_Assign"
        assert u2["credits"] == before_credits + 50
        # unassign
        r = requests.post(f"{API}/admin/users/{uid}/plan", headers=ah, json={"plan_id": None})
        assert r.status_code == 200
        users3 = requests.get(f"{API}/admin/users", headers=ah).json()
        u3 = next(u for u in users3 if u["user_id"] == uid)
        assert not u3["plan_id"]
    finally:
        requests.delete(f"{API}/admin/plans/{pid}", headers=ah)


# ---------- Usage ----------
def test_usage_endpoint(ah):
    r = requests.get(f"{API}/admin/usage", headers=ah)
    assert r.status_code == 200
    data = r.json()
    assert set(data.keys()) >= {"admin", "users", "totals"}
    assert "photo_credits" in data["totals"] and "video_credits" in data["totals"]


# ---------- AI Providers ----------
def test_provider_invalid_openai_key(ah):
    r = requests.post(f"{API}/admin/providers", headers=ah, json={
        "name": "TEST_bad_openai", "type": "openai_compatible",
        "base_url": "https://api.openai.com/v1", "api_key": "sk-bad",
    })
    assert r.status_code == 200
    p = r.json()
    assert p["status"] == "invalid_key"
    assert p["models"] == []
    requests.delete(f"{API}/admin/providers/{p['id']}", headers=ah)


def test_provider_fal_valid_and_toggle_and_override(ah):
    r = requests.post(f"{API}/admin/providers", headers=ah, json={
        "name": "TEST_fal", "type": "fal", "base_url": "", "api_key": "fake-key",
    })
    assert r.status_code == 200
    p = r.json()
    assert p["status"] == "valid" and len(p["models"]) > 0
    pid = p["id"]
    model_id = p["models"][0]["id"]

    try:
        # toggle photo on
        r = requests.put(f"{API}/admin/providers/{pid}/models", headers=ah, json={
            "model_id": model_id, "photo": True
        })
        assert r.status_code == 200
        assert r.json()["enabled"][model_id]["photo"] is True

        # get tool-overrides options
        ov = requests.get(f"{API}/admin/tool-overrides", headers=ah).json()
        assert any(m["provider_id"] == pid and m["model_id"] == model_id for m in ov["photo_models"])
        assert len(ov["tools"]) > 0
        action = ov["tools"][0]["action"]

        # set an override
        r = requests.put(f"{API}/admin/tool-overrides", headers=ah, json={
            "action": action, "provider_id": pid, "model_id": model_id,
        })
        assert r.status_code == 200
        assert r.json()["overrides"][action]["provider_id"] == pid

        # delete provider — override should be cleaned up
        r = requests.delete(f"{API}/admin/providers/{pid}", headers=ah)
        assert r.status_code == 200
        pid = None
        ov2 = requests.get(f"{API}/admin/tool-overrides", headers=ah).json()
        assert action not in ov2["overrides"] or ov2["overrides"].get(action, {}).get("provider_id") != p["id"]
    finally:
        if pid:
            requests.delete(f"{API}/admin/providers/{pid}", headers=ah)


def test_refresh_provider(ah):
    r = requests.post(f"{API}/admin/providers", headers=ah, json={
        "name": "TEST_fal_refresh", "type": "fal", "base_url": "", "api_key": "abc",
    })
    pid = r.json()["id"]
    try:
        r = requests.post(f"{API}/admin/providers/{pid}/refresh", headers=ah)
        assert r.status_code == 200 and r.json()["status"] == "valid"
    finally:
        requests.delete(f"{API}/admin/providers/{pid}", headers=ah)
