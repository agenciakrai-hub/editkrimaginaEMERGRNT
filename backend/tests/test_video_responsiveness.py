"""Iteration 3 — validates the reported bug fix:
- ffmpeg bundled (imageio-ffmpeg) works in preview
- Video generation completes (tour + reel)
- CRITICAL: GET /api/properties/{id}/videos and /api/files stay responsive (<2s, 200)
  while a video is still 'processing' — this was the hang causing bug in production.
- Insufficient credits => 402 Spanish, no dangling video.
"""
import io
import os
import time
import uuid
import concurrent.futures
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"
ADMIN = {"email": "admin@watchful.app", "password": "Watchful2026!"}

PNG_1x1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?"
    b"\x00\x05\xfe\x02\xfe\xdc\xccY\xe7\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _h(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def prop_with_photos(admin_token):
    r = requests.post(f"{API}/properties",
                      json={"name": "TEST_VidResp", "address": "Calle Test 3, Madrid"},
                      headers=_h(admin_token), timeout=20)
    assert r.status_code == 200
    pid = r.json()["id"]
    # 6 photos — enough to keep ffmpeg busy for ~25-40s
    for _ in range(6):
        files = {"files": ("t.png", io.BytesIO(PNG_1x1), "image/png")}
        rr = requests.post(f"{API}/properties/{pid}/photos", files=files,
                           headers=_h(admin_token), timeout=30)
        assert rr.status_code == 200
    # snapshot one photo path for /api/files responsiveness test
    photos = requests.get(f"{API}/properties/{pid}/photos",
                          headers=_h(admin_token), timeout=15).json()
    sample_path = photos[0].get("storage_path") or photos[0].get("current_path") or photos[0].get("path")
    yield pid, sample_path
    requests.delete(f"{API}/properties/{pid}", headers=_h(admin_token), timeout=15)


def test_ffmpeg_bundled_available():
    """Sanity — imageio-ffmpeg should provide the binary that video.py uses."""
    import imageio_ffmpeg
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    assert os.path.exists(exe), f"bundled ffmpeg missing at {exe}"


def test_tour_generation_and_responsiveness(admin_token, prop_with_photos):
    pid, sample_path = prop_with_photos
    me = requests.get(f"{API}/auth/me", headers=_h(admin_token), timeout=15).json()
    before = me["credits"]

    r = requests.post(f"{API}/properties/{pid}/video",
                      json={"format": "tour", "music": True, "agency_name": "Mi Agencia"},
                      headers=_h(admin_token), timeout=20)
    assert r.status_code == 200, r.text
    vid = r.json()["video_id"]

    after = requests.get(f"{API}/auth/me", headers=_h(admin_token), timeout=15).json()["credits"]
    assert after == before - 12, f"tour should deduct 12 credits (before={before}, after={after})"

    # ---- Responsiveness probe: while status == processing, hit /videos and /files repeatedly.
    max_wait = 150
    deadline = time.time() + max_wait
    probes = []  # (endpoint, elapsed_s, status_code)
    last_status = None
    while time.time() < deadline:
        # Probe: list videos
        t0 = time.time()
        try:
            rl = requests.get(f"{API}/properties/{pid}/videos",
                              headers=_h(admin_token), timeout=5)
            probes.append(("list", time.time() - t0, rl.status_code))
        except requests.RequestException as e:
            probes.append(("list", time.time() - t0, f"EXC:{e}"))
        # Probe: serve one property photo file (io path)
        if sample_path:
            t0 = time.time()
            try:
                rf = requests.get(f"{API}/files/{sample_path}",
                                  params={"token": admin_token}, timeout=5)
                probes.append(("file", time.time() - t0, rf.status_code))
            except requests.RequestException as e:
                probes.append(("file", time.time() - t0, f"EXC:{e}"))
        # Probe: status of the video itself
        t0 = time.time()
        rs = requests.get(f"{API}/videos/{vid}", headers=_h(admin_token), timeout=10)
        probes.append(("status", time.time() - t0, rs.status_code))
        assert rs.status_code == 200
        last_status = rs.json()["status"]
        if last_status in ("done", "failed"):
            break
        time.sleep(2)

    # Analyse probes
    print(f"total probes: {len(probes)}, final status={last_status}")
    slow = [p for p in probes if isinstance(p[1], float) and p[1] > 2.0]
    bad = [p for p in probes if not (isinstance(p[2], int) and 200 <= p[2] < 400)]
    print(f"slow(>2s): {slow[:5]} … total {len(slow)}")
    print(f"non-2xx:   {bad[:5]}   total {len(bad)}")

    assert last_status == "done", f"video did not finish, last status={last_status}"
    # We tolerate an occasional single slow probe, but the majority must be fast.
    fast_ratio = 1 - (len(slow) / max(1, len(probes)))
    assert fast_ratio >= 0.9, f"only {fast_ratio*100:.0f}% probes were <2s — event loop blocked!"
    assert len(bad) == 0, f"non-2xx responses during video generation: {bad}"

    # Fetch the final video file
    final = requests.get(f"{API}/videos/{vid}", headers=_h(admin_token), timeout=15).json()
    assert final.get("storage_path")
    rv = requests.get(f"{API}/files/{final['storage_path']}",
                      params={"token": admin_token}, timeout=60)
    assert rv.status_code == 200
    assert rv.headers.get("content-type", "").startswith("video/mp4")
    assert len(rv.content) > 10_000, "video too small — likely broken"


def test_reel_generation(admin_token, prop_with_photos):
    pid, _ = prop_with_photos
    before = requests.get(f"{API}/auth/me", headers=_h(admin_token), timeout=15).json()["credits"]
    r = requests.post(f"{API}/properties/{pid}/video",
                      json={"format": "reel", "music": True, "agency_name": "Mi Agencia"},
                      headers=_h(admin_token), timeout=20)
    assert r.status_code == 200
    vid = r.json()["video_id"]
    assert requests.get(f"{API}/auth/me", headers=_h(admin_token), timeout=15).json()["credits"] == before - 8
    # Poll status
    deadline = time.time() + 150
    status = None
    while time.time() < deadline:
        st = requests.get(f"{API}/videos/{vid}", headers=_h(admin_token), timeout=10)
        assert st.status_code == 200
        status = st.json()["status"]
        if status in ("done", "failed"):
            break
        time.sleep(3)
    assert status == "done", f"reel didn't finish: {status}"


def test_concurrent_list_not_blocked(admin_token, prop_with_photos):
    """Fire 15 concurrent list-videos requests. All should return in <2s and 200 even
    while any residual generation is happening."""
    pid, _ = prop_with_photos

    def one():
        t0 = time.time()
        r = requests.get(f"{API}/properties/{pid}/videos",
                         headers=_h(admin_token), timeout=6)
        return time.time() - t0, r.status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as ex:
        results = list(ex.map(lambda _: one(), range(15)))
    slow = [r for r in results if r[0] > 2.0]
    bad = [r for r in results if r[1] != 200]
    print(f"concurrent results: {results}")
    assert not bad, f"non-200 responses: {bad}"
    assert len(slow) <= 1, f"too many slow responses: {slow}"


def test_insufficient_credits_no_dangling_video():
    email = f"TEST_lowc_{uuid.uuid4().hex[:6]}@w.app"
    reg = requests.post(f"{API}/auth/register",
                       json={"email": email, "password": "Pass2026!", "name": "Low"}, timeout=15).json()
    tok = reg["token"]
    pid = requests.post(f"{API}/properties", json={"name": "TEST_low", "address": ""},
                        headers=_h(tok), timeout=15).json()["id"]
    files = {"files": ("t.png", io.BytesIO(PNG_1x1), "image/png")}
    requests.post(f"{API}/properties/{pid}/photos", files=files, headers=_h(tok), timeout=30)
    # 30 credits: use 2 tours (24), leaves 6, next tour must 402.
    for _ in range(2):
        rr = requests.post(f"{API}/properties/{pid}/video",
                           json={"format": "tour", "music": False},
                           headers=_h(tok), timeout=15)
        assert rr.status_code == 200
    n_before = len(requests.get(f"{API}/properties/{pid}/videos", headers=_h(tok), timeout=10).json())
    r = requests.post(f"{API}/properties/{pid}/video",
                      json={"format": "tour", "music": False},
                      headers=_h(tok), timeout=15)
    assert r.status_code == 402
    body = r.json()
    assert "crédito" in body.get("detail", "").lower(), body
    # No new video row created (no dangling processing)
    time.sleep(1)
    n_after = len(requests.get(f"{API}/properties/{pid}/videos", headers=_h(tok), timeout=10).json())
    assert n_after == n_before, f"video was created despite 402 (before={n_before}, after={n_after})"
    requests.delete(f"{API}/properties/{pid}", headers=_h(tok), timeout=15)
