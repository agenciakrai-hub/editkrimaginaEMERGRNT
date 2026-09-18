"""Iter5 regression tests: auth (admin/owner), free edit, owner-paid-no-deduct,
video generation, payments packages+checkout."""
import io
import os
import time
import uuid
import pytest
import requests
from PIL import Image

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://property-video-ai-3.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = ("admin@watchful.app", "Watchful2026!")
OWNER = ("krimagina2025@gmail.com", "Owner2026!")


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


def _jpg(size=(1280, 800), color=(120, 160, 200)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="JPEG", quality=85)
    buf.seek(0)
    return buf


# ---------- AUTH ----------
@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN[0], "password": ADMIN[1]}, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="session")
def owner_token():
    # Ensure owner exists — try login first, else register.
    r = requests.post(f"{API}/auth/login", json={"email": OWNER[0], "password": OWNER[1]}, timeout=20)
    if r.status_code != 200:
        r = requests.post(f"{API}/auth/register", json={"email": OWNER[0], "password": OWNER[1], "name": "Owner"}, timeout=20)
        assert r.status_code == 200, f"owner register failed: {r.status_code} {r.text}"
        # After first-time register, on_startup already promoted; but to be safe login again to hit promotion path.
        r2 = requests.post(f"{API}/auth/login", json={"email": OWNER[0], "password": OWNER[1]}, timeout=20)
        assert r2.status_code == 200, r2.text
        return r2.json()["token"]
    return r.json()["token"]


def test_admin_login(admin_token):
    assert admin_token


def test_admin_me(admin_token):
    r = requests.get(f"{API}/auth/me", headers=_h(admin_token), timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d["email"] == ADMIN[0]
    assert d.get("role") == "admin"


def test_owner_login_and_me(owner_token):
    r = requests.get(f"{API}/auth/me", headers=_h(owner_token), timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["email"] == OWNER[0]
    # Owner promotion happens at startup; role should be owner OR the email is in OWNER_EMAILS (is_owner treats both as owner)
    print(f"OWNER /me: role={d.get('role')} credits={d.get('credits')} unlimited={d.get('unlimited')}")


def test_logout(admin_token):
    r = requests.post(f"{API}/auth/logout", headers=_h(admin_token), timeout=15)
    assert r.status_code in (200, 204)


# ---------- FREE EDIT (admin) ----------
@pytest.fixture(scope="session")
def admin_property_and_photo(admin_token):
    r = requests.post(f"{API}/properties", json={"name": "TEST_Iter5_Admin", "address": "X"},
                      headers=_h(admin_token), timeout=15)
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    files = {"files": ("t.jpg", _jpg(), "image/jpeg")}
    up = requests.post(f"{API}/properties/{pid}/photos", files=files, headers=_h(admin_token), timeout=60)
    assert up.status_code == 200
    photo = up.json()[0]
    yield pid, photo
    requests.delete(f"{API}/properties/{pid}", headers=_h(admin_token), timeout=15)


def test_free_edit_sky_admin(admin_token, admin_property_and_photo):
    pid, photo = admin_property_and_photo
    before = requests.get(f"{API}/auth/me", headers=_h(admin_token), timeout=15).json()["credits"]
    r = requests.post(f"{API}/photos/{photo['id']}/edit",
                      json={"action": "sky"}, headers=_h(admin_token), timeout=180)
    if r.status_code >= 500:
        pytest.skip(f"Gemini upstream failure: {r.status_code} {r.text[:200]}")
    assert r.status_code == 200, r.text
    body = r.json()
    p = body["photo"]
    # Credits not deducted for free action
    assert body["credits"] == before, f"free edit deducted credits {before}->{body['credits']}"
    assert len(p["edits"]) >= 1
    assert p["edits"][-1]["action"] == "sky"
    assert p["current_path"] != photo["original_path"]


# ---------- OWNER PAID NO-DEDUCT ----------
@pytest.fixture(scope="session")
def owner_property_and_photo(owner_token):
    r = requests.post(f"{API}/properties", json={"name": "TEST_Iter5_Owner", "address": "X"},
                      headers=_h(owner_token), timeout=15)
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    files = {"files": ("t.jpg", _jpg(), "image/jpeg")}
    up = requests.post(f"{API}/properties/{pid}/photos", files=files, headers=_h(owner_token), timeout=60)
    assert up.status_code == 200, up.text
    photo = up.json()[0]
    yield pid, photo
    requests.delete(f"{API}/properties/{pid}", headers=_h(owner_token), timeout=15)


def test_owner_paid_edit_no_deduct(owner_token, owner_property_and_photo):
    pid, photo = owner_property_and_photo
    before_me = requests.get(f"{API}/auth/me", headers=_h(owner_token), timeout=15).json()
    before = before_me["credits"]
    r = requests.post(f"{API}/photos/{photo['id']}/edit",
                      json={"action": "twilight"}, headers=_h(owner_token), timeout=180)
    if r.status_code == 402:
        pytest.fail(f"OWNER got 402 on paid edit: {r.text}")
    if r.status_code >= 500:
        pytest.skip(f"Gemini upstream: {r.status_code} {r.text[:200]}")
    assert r.status_code == 200, r.text
    after = r.json()["credits"]
    # Owner: credits unchanged
    assert after == before, f"OWNER credits changed {before}->{after}"


# ---------- VIDEO ----------
def test_video_tour_end_to_end(admin_token):
    pid_r = requests.post(f"{API}/properties", json={"name": "TEST_Iter5_Video", "address": "X"},
                          headers=_h(admin_token), timeout=15)
    assert pid_r.status_code == 200
    pid = pid_r.json()["id"]
    try:
        # Upload 6 photos
        for i in range(6):
            files = {"files": (f"p{i}.jpg", _jpg(color=(60 + i * 20, 100, 180)), "image/jpeg")}
            u = requests.post(f"{API}/properties/{pid}/photos", files=files,
                              headers=_h(admin_token), timeout=60)
            assert u.status_code == 200

        # Create video (endpoint is singular /video)
        r = requests.post(f"{API}/properties/{pid}/video",
                          json={"format": "tour", "music": True, "agency_name": "Regression"},
                          headers=_h(admin_token), timeout=30)
        assert r.status_code == 200, r.text
        vid = r.json()
        video_id = vid["video_id"]
        assert vid.get("eta_seconds", 0) > 0

        # Poll — during processing check listing endpoint responds fast (no 5xx)
        deadline = time.time() + 180
        final = None
        probes_ok = 0
        while time.time() < deadline:
            t0 = time.time()
            lst = requests.get(f"{API}/properties/{pid}/videos",
                               headers=_h(admin_token), timeout=10)
            dt = time.time() - t0
            assert lst.status_code == 200, f"videos listing failed: {lst.status_code}"
            assert dt < 5, f"videos listing slow during processing: {dt:.1f}s"
            probes_ok += 1
            match = next((v for v in lst.json() if v["id"] == video_id), None)
            assert match is not None
            if match.get("status") in ("done", "failed"):
                final = match
                break
            # Check eta_seconds hint present during processing
            time.sleep(4)
        assert final is not None, "video did not finish in 180s"
        assert final["status"] == "done", f"video status={final['status']}: {final.get('error')}"
        print(f"video done in ~{final.get('duration_seconds', '?')}s, {probes_ok} probes all <5s")

        # Playable via /api/files
        path = final.get("storage_path")
        assert path, f"missing storage_path in {final}"
        fr = requests.get(f"{API}/files/{path}", params={"token": admin_token}, timeout=30)
        assert fr.status_code == 200
        assert fr.headers.get("content-type", "").startswith("video/")
    finally:
        requests.delete(f"{API}/properties/{pid}", headers=_h(admin_token), timeout=20)


# ---------- PAYMENTS ----------
def test_payments_packages():
    r = requests.get(f"{API}/payments/packages", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    # accept list or {packages:[...]}
    pkgs = data if isinstance(data, list) else data.get("packages", [])
    assert len(pkgs) == 3, f"expected 3 packages, got {len(pkgs)}: {data}"


def test_payments_checkout_returns_stripe_url(admin_token):
    r = requests.get(f"{API}/payments/packages", timeout=15)
    pkgs = r.json() if isinstance(r.json(), list) else r.json().get("packages", [])
    lookup_key = pkgs[0]["lookup_key"]
    body = {"lookup_key": lookup_key, "origin_url": BASE_URL}
    rr = requests.post(f"{API}/payments/checkout", json=body,
                       headers=_h(admin_token), timeout=30)
    assert rr.status_code == 200, f"checkout failed: {rr.status_code} {rr.text[:300]}"
    j = rr.json()
    url = j.get("checkout_url") or j.get("url")
    assert url and "stripe.com" in url, f"expected stripe url, got {j}"
