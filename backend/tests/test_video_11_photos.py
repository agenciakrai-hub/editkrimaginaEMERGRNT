"""Iteration 4 — reproduce the user-reported production bug:
'el video no se termina de generar' with a real property of ~11 photos at ~2560px.

Validates the applied fix (video.py working-resolution 1.25x, veryfast, timeout=180s;
server.py _video_sweeper marking >8min processing videos as failed+refund).

We generate 11 REAL JPEGs at ~2560px (varied colors) so ffmpeg has to do actual work.
"""
import io
import os
import time
import pytest
import requests
from PIL import Image, ImageDraw

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"
ADMIN = {"email": "admin@watchful.app", "password": "Watchful2026!"}


def _h(t):
    return {"Authorization": f"Bearer {t}"}


def _make_jpg(idx: int) -> bytes:
    """Real ~2560px JPEG w/ some detail so ffmpeg does non-trivial work."""
    w, h = 2560, 1706  # ~3:2 like a phone photo
    hue = (idx * 30) % 360
    # Simple gradient + shapes so encoding produces a real, non-tiny buffer
    img = Image.new("RGB", (w, h), (20 + idx * 15 % 200, 40 + idx * 25 % 200, 80))
    d = ImageDraw.Draw(img)
    for i in range(0, w, 80):
        d.line([(i, 0), (i + 200, h)], fill=(200, 220, 255), width=3)
    d.rectangle([w // 4, h // 4, 3 * w // 4, 3 * h // 4],
                fill=((idx * 40) % 255, (idx * 90) % 255, (idx * 130) % 255))
    d.text((100, 100), f"PHOTO {idx}", fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return buf.getvalue()


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=20)
    assert r.status_code == 200, r.text
    tok = r.json()["token"]
    # Ensure admin has enough credits (>= 20). Admin starts with 500; if depleted skip top-up.
    me = requests.get(f"{API}/auth/me", headers=_h(tok), timeout=15).json()
    print(f"admin credits at start: {me['credits']}")
    return tok


@pytest.fixture(scope="module")
def prop_11(admin_token):
    r = requests.post(f"{API}/properties",
                      json={"name": "TEST_Vid11", "address": "Calle Mayor 3, Madrid"},
                      headers=_h(admin_token), timeout=20)
    assert r.status_code == 200
    pid = r.json()["id"]
    # Upload 11 REAL ~2560px JPEGs, one at a time (multipart same field name 'files')
    for i in range(11):
        jpg = _make_jpg(i)
        files = {"files": (f"p{i}.jpg", io.BytesIO(jpg), "image/jpeg")}
        rr = requests.post(f"{API}/properties/{pid}/photos", files=files,
                           headers=_h(admin_token), timeout=60)
        assert rr.status_code == 200, f"photo {i}: {rr.status_code} {rr.text[:200]}"
    # Sanity: property must now have 11 photos
    photos = requests.get(f"{API}/properties/{pid}/photos",
                          headers=_h(admin_token), timeout=15).json()
    assert len(photos) == 11, f"expected 11 photos, got {len(photos)}"
    sample_path = photos[0].get("storage_path") or photos[0].get("current_path") or photos[0].get("path")
    yield pid, sample_path
    requests.delete(f"{API}/properties/{pid}", headers=_h(admin_token), timeout=30)


def _poll_until_done(token, vid, max_wait=150, probe_others=None):
    """Poll GET /api/videos/{vid} every 2s. If probe_others=(pid, sample_path), also probe /videos + /files."""
    deadline = time.time() + max_wait
    probes = []
    last_status = None
    while time.time() < deadline:
        if probe_others:
            pid, sample_path = probe_others
            t0 = time.time()
            try:
                rl = requests.get(f"{API}/properties/{pid}/videos",
                                  headers=_h(token), timeout=8)
                probes.append(("list", time.time() - t0, rl.status_code))
            except requests.RequestException as e:
                probes.append(("list", time.time() - t0, f"EXC:{type(e).__name__}"))
            if sample_path:
                t0 = time.time()
                try:
                    rf = requests.get(f"{API}/files/{sample_path}",
                                      params={"token": token}, timeout=10)
                    probes.append(("file", time.time() - t0, rf.status_code))
                except requests.RequestException as e:
                    probes.append(("file", time.time() - t0, f"EXC:{type(e).__name__}"))
        t0 = time.time()
        rs = requests.get(f"{API}/videos/{vid}", headers=_h(token), timeout=10)
        probes.append(("status", time.time() - t0, rs.status_code))
        assert rs.status_code == 200
        last_status = rs.json()["status"]
        if last_status in ("done", "failed"):
            return last_status, probes, rs.json()
        time.sleep(2)
    return last_status, probes, None


def test_tour_11_photos_completes_and_stays_responsive(admin_token, prop_11):
    """The exact scenario the user reported: TOUR with 11 real photos.
    Must (a) finish in <150s (b) deduct 12 credits (c) file playable video/mp4."""
    pid, sample_path = prop_11
    me = requests.get(f"{API}/auth/me", headers=_h(admin_token), timeout=15).json()
    before = me["credits"]

    t_start = time.time()
    r = requests.post(f"{API}/properties/{pid}/video",
                      json={"format": "tour", "music": True, "agency_name": "Costa Real"},
                      headers=_h(admin_token), timeout=20)
    assert r.status_code == 200, r.text
    vid = r.json()["video_id"]

    after = requests.get(f"{API}/auth/me", headers=_h(admin_token), timeout=15).json()["credits"]
    assert after == before - 12, f"tour must cost 12 (before={before}, after={after})"

    status, probes, final = _poll_until_done(admin_token, vid, max_wait=150,
                                             probe_others=(pid, sample_path))
    elapsed = time.time() - t_start
    slow = [p for p in probes if isinstance(p[1], float) and p[1] > 2.0]
    bad = [p for p in probes if not (isinstance(p[2], int) and 200 <= p[2] < 400)]
    print(f"TOUR11: elapsed={elapsed:.1f}s status={status} probes={len(probes)} "
          f"slow>2s={len(slow)} non2xx={len(bad)}")

    assert status == "done", (
        f"TOUR with 11 photos did NOT finish in 150s (status={status}). "
        f"This is the reported bug. probes={probes[-6:]}"
    )
    assert final and final.get("storage_path"), f"no storage_path on done video: {final}"
    fast_ratio = 1 - (len(slow) / max(1, len(probes)))
    assert fast_ratio >= 0.9, f"only {fast_ratio*100:.0f}% probes <2s — event loop blocked"
    assert not bad, f"non-2xx during generation: {bad[:5]}"

    # Fetch & verify final video
    rv = requests.get(f"{API}/files/{final['storage_path']}",
                      params={"token": admin_token}, timeout=60)
    assert rv.status_code == 200
    assert rv.headers.get("content-type", "").startswith("video/mp4")
    assert len(rv.content) > 50_000, f"tour mp4 suspiciously small: {len(rv.content)}"


def test_reel_11_photos_completes(admin_token, prop_11):
    """REEL 9:16 with the same 11 photos (backend will cap to 8 via FORMATS[max_photos])."""
    pid, _ = prop_11
    before = requests.get(f"{API}/auth/me", headers=_h(admin_token), timeout=15).json()["credits"]

    r = requests.post(f"{API}/properties/{pid}/video",
                      json={"format": "reel", "music": True, "agency_name": "Costa Real"},
                      headers=_h(admin_token), timeout=20)
    assert r.status_code == 200, r.text
    vid = r.json()["video_id"]

    after = requests.get(f"{API}/auth/me", headers=_h(admin_token), timeout=15).json()["credits"]
    assert after == before - 8, f"reel must cost 8 (before={before}, after={after})"

    status, probes, final = _poll_until_done(admin_token, vid, max_wait=150)
    print(f"REEL11: status={status} probes={len(probes)}")
    assert status == "done", f"reel did not finish: {status}"
    assert final.get("storage_path")
    rv = requests.get(f"{API}/files/{final['storage_path']}",
                      params={"token": admin_token}, timeout=60)
    assert rv.status_code == 200
    assert rv.headers.get("content-type", "").startswith("video/mp4")
    assert len(rv.content) > 50_000
