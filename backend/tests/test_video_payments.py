"""Watchful iteration 2 tests: VIDEO generation + STRIPE credit packages."""
import io
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@watchful.app"
ADMIN_PASS = "Watchful2026!"

# Tiny 1x1 PNG (still enough for ffmpeg via image loop)
PNG_1x1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?"
    b"\x00\x05\xfe\x02\xfe\xdc\xccY\xe7\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_property(admin_token):
    r = requests.post(f"{API}/properties", json={"name": "TEST_VideoProp", "address": "Test 1"},
                      headers=_h(admin_token), timeout=20)
    assert r.status_code == 200
    pid = r.json()["id"]
    # Upload 3 photos
    for _ in range(3):
        files = {"files": ("t.png", io.BytesIO(PNG_1x1), "image/png")}
        rr = requests.post(f"{API}/properties/{pid}/photos", files=files, headers=_h(admin_token), timeout=30)
        assert rr.status_code == 200
    yield pid
    requests.delete(f"{API}/properties/{pid}", headers=_h(admin_token), timeout=15)


# ---------------- Auth basic ----------------
def test_admin_login(admin_token):
    assert admin_token


def test_register_new_user():
    email = f"test_reg_{uuid.uuid4().hex[:6]}@watchful.app"
    r = requests.post(f"{API}/auth/register",
                      json={"email": email, "password": "Pass2026!", "name": "Reg"}, timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["credits"] == 30
    assert body["token"]


# ---------------- VIDEO backend ----------------
def _wait_video(video_id, token, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        r = requests.get(f"{API}/videos/{video_id}", headers=_h(token), timeout=15)
        assert r.status_code == 200
        data = r.json()
        if data["status"] in ("done", "failed"):
            return data
        time.sleep(3)
    return {"status": "timeout"}


def test_video_tour_generation(admin_token, admin_property):
    before = requests.get(f"{API}/auth/me", headers=_h(admin_token), timeout=15).json()["credits"]
    r = requests.post(f"{API}/properties/{admin_property}/video",
                      json={"format": "tour", "music": True, "agency_name": "TEST Agencia"},
                      headers=_h(admin_token), timeout=20)
    assert r.status_code == 200, r.text
    vid = r.json()["video_id"]
    # credits deducted immediately
    after = requests.get(f"{API}/auth/me", headers=_h(admin_token), timeout=15).json()["credits"]
    assert after == before - 12

    result = _wait_video(vid, admin_token, timeout=120)
    assert result["status"] == "done", f"Video did not finish: {result}"
    assert result.get("storage_path")

    # Serve file
    r2 = requests.get(f"{API}/files/{result['storage_path']}",
                      params={"token": admin_token}, timeout=60)
    assert r2.status_code == 200
    assert r2.headers.get("content-type", "").startswith("video/mp4")
    assert len(r2.content) > 1024


def test_video_reel_generation(admin_token, admin_property):
    before = requests.get(f"{API}/auth/me", headers=_h(admin_token), timeout=15).json()["credits"]
    r = requests.post(f"{API}/properties/{admin_property}/video",
                      json={"format": "reel", "music": False},
                      headers=_h(admin_token), timeout=20)
    assert r.status_code == 200, r.text
    vid = r.json()["video_id"]
    after = requests.get(f"{API}/auth/me", headers=_h(admin_token), timeout=15).json()["credits"]
    assert after == before - 8
    result = _wait_video(vid, admin_token, timeout=120)
    assert result["status"] == "done", f"Reel did not finish: {result}"


def test_video_insufficient_credits():
    email = f"TEST_vid_{uuid.uuid4().hex[:6]}@w.app"
    reg = requests.post(f"{API}/auth/register",
                        json={"email": email, "password": "Pass2026!", "name": "V"}, timeout=15).json()
    tok = reg["token"]
    pid = requests.post(f"{API}/properties", json={"name": "TEST_lowcred", "address": ""},
                        headers=_h(tok), timeout=15).json()["id"]
    files = {"files": ("t.png", io.BytesIO(PNG_1x1), "image/png")}
    requests.post(f"{API}/properties/{pid}/photos", files=files, headers=_h(tok), timeout=30)
    # user has 30 credits. tour=12 ok; reel=8 ok. Need to drain first.
    # Cheapest: 3 tours = 36 > 30, so do two tours (24 used, 6 remaining) then request tour (12) -> 402.
    for _ in range(2):
        r = requests.post(f"{API}/properties/{pid}/video",
                          json={"format": "tour", "music": False},
                          headers=_h(tok), timeout=15)
        assert r.status_code == 200
    r = requests.post(f"{API}/properties/{pid}/video",
                      json={"format": "tour", "music": False},
                      headers=_h(tok), timeout=15)
    assert r.status_code == 402
    body = r.json()
    assert "crédito" in body.get("detail", "").lower() or "credit" in body.get("detail", "").lower()
    requests.delete(f"{API}/properties/{pid}", headers=_h(tok), timeout=15)


# ---------------- Videos list ----------------
def test_list_videos(admin_token, admin_property):
    r = requests.get(f"{API}/properties/{admin_property}/videos",
                     headers=_h(admin_token), timeout=15)
    assert r.status_code == 200
    videos = r.json()
    assert len(videos) >= 1


# ---------------- PAYMENTS ----------------
def test_payment_packages():
    r = requests.get(f"{API}/payments/packages", timeout=15)
    assert r.status_code == 200
    pkgs = {p["lookup_key"]: p for p in r.json()}
    assert set(pkgs.keys()) == {"credits_100", "credits_300", "credits_1000"}
    assert pkgs["credits_100"]["credits"] == 100
    assert pkgs["credits_300"]["credits"] == 300
    assert pkgs["credits_1000"]["credits"] == 1000


def test_payment_checkout_creates_session(admin_token):
    r = requests.post(f"{API}/payments/checkout",
                      json={"lookup_key": "credits_300", "origin_url": BASE_URL},
                      headers=_h(admin_token), timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "checkout_url" in body and "session_id" in body
    assert "checkout.stripe.com" in body["checkout_url"]
    # Status now pending
    st = requests.get(f"{API}/payments/status/{body['session_id']}", timeout=15)
    assert st.status_code == 200
    sd = st.json()
    assert sd["session_id"] == body["session_id"]
    assert sd["status"] in ("initiated", "completed")
    assert sd["credits"] == 300


def test_payment_checkout_invalid_package(admin_token):
    r = requests.post(f"{API}/payments/checkout",
                      json={"lookup_key": "credits_evil", "origin_url": BASE_URL},
                      headers=_h(admin_token), timeout=15)
    assert r.status_code == 400


def test_payment_checkout_requires_auth():
    r = requests.post(f"{API}/payments/checkout",
                      json={"lookup_key": "credits_100", "origin_url": BASE_URL}, timeout=15)
    assert r.status_code == 401
