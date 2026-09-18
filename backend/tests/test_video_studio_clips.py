"""Iteration 6: VideoStudioDialog clips[] contract — multi-motion per photo, per-clip duration,
owner cost=0. Also asserts eta = 2.2 + Σsecs + 6 and MP4 playable via /api/files."""
import io
import os
import time
import uuid
import pytest
import requests
from PIL import Image

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE}/api"

OWNER_EMAIL = "krimagina2025@gmail.com"
OWNER_PASS = "Owner2026!"
USER_EMAIL = f"TEST_iter6_{uuid.uuid4().hex[:6]}@watchful.app"
USER_PASS = "Iter6Test!"


def _jpeg(color=(120, 180, 200), size=(1280, 720)):
    im = Image.new("RGB", size, color)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=80)
    return buf.getvalue()


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    if r.status_code == 200:
        return r.json()["token"]
    return None


def _register(email, password):
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": password, "name": "Iter6"}, timeout=20)
    return r


@pytest.fixture(scope="module")
def owner_token():
    tok = _login(OWNER_EMAIL, OWNER_PASS)
    if not tok:
        _register(OWNER_EMAIL, OWNER_PASS)
        tok = _login(OWNER_EMAIL, OWNER_PASS)
    assert tok, "owner login failed"
    return tok


@pytest.fixture(scope="module")
def user_token():
    _register(USER_EMAIL, USER_PASS)
    tok = _login(USER_EMAIL, USER_PASS)
    assert tok, "user login failed"
    return tok


def _me(tok):
    r = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {tok}"}, timeout=15)
    return r.json() if r.status_code == 200 else None


def _create_property_with_photos(tok, n=3, name_prefix="TEST_Iter6"):
    h = {"Authorization": f"Bearer {tok}"}
    r = requests.post(f"{API}/properties", json={"name": f"{name_prefix}_{uuid.uuid4().hex[:5]}"}, headers=h, timeout=15)
    assert r.status_code in (200, 201), r.text
    pid = r.json()["id"]

    files = [("files", (f"p{i}.jpg", _jpeg(((i * 40) % 255, 100, (255 - i * 30) % 255)), "image/jpeg")) for i in range(n)]
    r = requests.post(f"{API}/properties/{pid}/photos", files=files, headers=h, timeout=60)
    assert r.status_code in (200, 201), r.text

    r = requests.get(f"{API}/properties/{pid}/photos", headers=h, timeout=15)
    assert r.status_code == 200
    photos = r.json()
    assert len(photos) >= n
    return pid, photos[:n]


def _cleanup(tok, pid):
    try:
        requests.delete(f"{API}/properties/{pid}", headers={"Authorization": f"Bearer {tok}"}, timeout=15)
    except Exception:
        pass


def _poll_video(tok, vid, max_wait=180):
    h = {"Authorization": f"Bearer {tok}"}
    t0 = time.time()
    while time.time() - t0 < max_wait:
        r = requests.get(f"{API}/videos/{vid}", headers=h, timeout=10)
        if r.status_code == 200:
            v = r.json()
            if v.get("status") in ("done", "failed"):
                return v
        time.sleep(3)
    return None


# ---------------- Auth ----------------

class TestAuth:
    def test_owner_login_and_unlimited(self, owner_token):
        me = _me(owner_token)
        assert me and (me.get("role") == "owner" or me.get("unlimited") is True), me

    def test_user_register_and_login(self, user_token):
        me = _me(user_token)
        assert me and me.get("email") == USER_EMAIL, me


# ---------------- Owner: multi-motion clips ----------------

class TestOwnerMultiMotion:
    def test_owner_multi_motion_video_zero_cost(self, owner_token):
        pid, photos = _create_property_with_photos(owner_token, n=3)
        try:
            durations = [2, 4, 3]
            motions = ["zoom_in", "pan_right", "tilt_down"]
            clips = [
                {"photo_id": photos[i]["id"], "motion": motions[i], "duration": durations[i],
                 "style": "cinematic", "prompt": f"nice room {i}"}
                for i in range(3)
            ]
            r = requests.post(
                f"{API}/properties/{pid}/video",
                json={"format": "tour", "music": True, "agency_name": "TEST_Agency", "clips": clips},
                headers={"Authorization": f"Bearer {owner_token}"}, timeout=30,
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["cost"] == 0, f"owner should be free, got {body}"
            expected_eta = int(2.2 + sum(durations) + 6)  # 2.2+9+6 => 17
            assert body["eta_seconds"] == expected_eta, (body["eta_seconds"], expected_eta)
            vid = body["video_id"]

            # Listing responds fast during processing
            t0 = time.time()
            r2 = requests.get(f"{API}/properties/{pid}/videos",
                              headers={"Authorization": f"Bearer {owner_token}"}, timeout=10)
            assert r2.status_code == 200
            assert time.time() - t0 < 5.0

            v = _poll_video(owner_token, vid, max_wait=180)
            assert v is not None, "video did not reach terminal state in 180s"
            assert v["status"] == "done", v
            assert v.get("storage_path"), v

            # Serve the MP4 through /api/files with token
            files_url = f"{API}/files/{v['storage_path']}?token={owner_token}"
            r3 = requests.get(files_url, timeout=60)
            assert r3.status_code == 200
            assert r3.headers.get("content-type", "").startswith("video/"), r3.headers
            assert len(r3.content) > 20000, len(r3.content)
        finally:
            _cleanup(owner_token, pid)

    def test_owner_various_motions_all_valid(self, owner_token):
        """Exercise the full motion set in a single video and make sure it reaches 'done'."""
        pid, photos = _create_property_with_photos(owner_token, n=5)
        try:
            motion_set = ["none", "zoom_out", "pan_left", "tilt_up", "ken_burns"]
            clips = [
                {"photo_id": photos[i]["id"], "motion": motion_set[i], "duration": 2,
                 "style": "custom", "prompt": ""}
                for i in range(5)
            ]
            r = requests.post(
                f"{API}/properties/{pid}/video",
                json={"format": "reel", "music": False, "clips": clips},
                headers={"Authorization": f"Bearer {owner_token}"}, timeout=30,
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["cost"] == 0
            assert body["eta_seconds"] == int(2.2 + 5 * 2 + 6)  # 18
            v = _poll_video(owner_token, body["video_id"], max_wait=240)
            assert v and v["status"] == "done", v
        finally:
            _cleanup(owner_token, pid)

    def test_dolly_and_ai_motions_accepted(self, owner_token):
        pid, photos = _create_property_with_photos(owner_token, n=3)
        try:
            clips = [
                {"photo_id": photos[0]["id"], "motion": "dolly", "duration": 2, "style": "cinematic"},
                {"photo_id": photos[1]["id"], "motion": "ai", "duration": 2, "style": "custom", "prompt": "sunset"},
                {"photo_id": photos[2]["id"], "motion": "invalid_motion", "duration": 2, "style": "custom"},
            ]
            r = requests.post(
                f"{API}/properties/{pid}/video",
                json={"format": "tour", "music": False, "clips": clips},
                headers={"Authorization": f"Bearer {owner_token}"}, timeout=30,
            )
            assert r.status_code == 200, r.text
            v = _poll_video(owner_token, r.json()["video_id"], max_wait=180)
            assert v and v["status"] == "done", v
        finally:
            _cleanup(owner_token, pid)


# ---------------- Regular user: credit deduction ----------------

class TestUserCredits:
    def test_user_tour_deducts_12(self, user_token):
        me_before = _me(user_token)
        credits_before = me_before.get("credits", 0)
        if credits_before < 12:
            pytest.skip(f"user has only {credits_before} credits, needs 12 for tour")

        pid, photos = _create_property_with_photos(user_token, n=3)
        try:
            clips = [{"photo_id": p["id"], "motion": "ken_burns", "duration": 2, "style": "cinematic"} for p in photos]
            r = requests.post(
                f"{API}/properties/{pid}/video",
                json={"format": "tour", "music": True, "clips": clips},
                headers={"Authorization": f"Bearer {user_token}"}, timeout=30,
            )
            assert r.status_code == 200, r.text
            assert r.json()["cost"] == 12
            me_after = _me(user_token)
            assert me_after["credits"] == credits_before - 12, (credits_before, me_after["credits"])
        finally:
            _cleanup(user_token, pid)

    def test_user_reel_deducts_8(self, user_token):
        me_before = _me(user_token)
        credits_before = me_before.get("credits", 0)
        if credits_before < 8:
            pytest.skip(f"user has only {credits_before} credits, needs 8 for reel")

        pid, photos = _create_property_with_photos(user_token, n=3)
        try:
            clips = [{"photo_id": p["id"], "motion": "zoom_in", "duration": 2, "style": "zoom_in"} for p in photos]
            r = requests.post(
                f"{API}/properties/{pid}/video",
                json={"format": "reel", "music": False, "clips": clips},
                headers={"Authorization": f"Bearer {user_token}"}, timeout=30,
            )
            assert r.status_code == 200, r.text
            assert r.json()["cost"] == 8
            me_after = _me(user_token)
            assert me_after["credits"] == credits_before - 8
        finally:
            _cleanup(user_token, pid)


# ---------------- Regression ----------------

class TestRegression:
    def test_payments_packages(self):
        r = requests.get(f"{API}/payments/packages", timeout=15)
        assert r.status_code == 200
        pkgs = r.json()
        assert isinstance(pkgs, list) and len(pkgs) >= 1

    def test_payments_checkout(self, user_token):
        r = requests.get(f"{API}/payments/packages", timeout=15)
        pkg = r.json()[0]
        lk = pkg.get("lookup_key") or pkg.get("id") or pkg.get("key")
        r2 = requests.post(
            f"{API}/payments/checkout",
            json={"lookup_key": lk, "origin_url": BASE},
            headers={"Authorization": f"Bearer {user_token}"}, timeout=20,
        )
        assert r2.status_code == 200, r2.text
        body = r2.json()
        url = body.get("url") or body.get("checkout_url")
        assert url and "stripe.com" in url, body
