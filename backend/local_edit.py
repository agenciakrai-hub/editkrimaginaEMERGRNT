"""Local, free photo enhancement for the ESSENTIAL (free) tools.

These run entirely on the server with OpenCV/Pillow/NumPy — no paid AI API, so
they never consume user credits nor the Emergent Universal Key balance. Premium
tools (staging, twilight, declutter, window pull, upscale) still use generative AI.

All functions take/return JPEG bytes and work at the image's native resolution.
"""
import io
import logging
import numpy as np
import cv2
from PIL import Image

logger = logging.getLogger("watchful.local_edit")

# Actions handled locally for free.
SUPPORTED = {"auto", "light", "straighten", "sky"}


def _to_bgr(data: bytes) -> np.ndarray:
    img = Image.open(io.BytesIO(data))
    if img.mode != "RGB":
        img = img.convert("RGB")
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)


def _to_jpeg(bgr: np.ndarray, quality: int = 95) -> bytes:
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    buf = io.BytesIO()
    Image.fromarray(rgb).save(buf, format="JPEG", quality=quality, subsampling=0, optimize=True)
    return buf.getvalue()


def _white_balance(bgr: np.ndarray) -> np.ndarray:
    """Gray-world white balance, clamped to avoid extreme color shifts."""
    f = bgr.astype(np.float32)
    avg = f.reshape(-1, 3).mean(axis=0)
    gray = float(avg.mean())
    scale = np.clip(gray / (avg + 1e-6), 0.82, 1.22)
    return np.clip(f * scale, 0, 255).astype(np.uint8)


def _clahe(bgr: np.ndarray, clip: float = 2.2) -> np.ndarray:
    """Local contrast (HDR-like) via CLAHE on the L channel."""
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    l = cv2.createCLAHE(clipLimit=clip, tileGridSize=(8, 8)).apply(l)
    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)


def _tone(bgr: np.ndarray, gamma: float = 0.88) -> np.ndarray:
    """Lift shadows / balance midtones with a gentle gamma curve."""
    f = bgr.astype(np.float32) / 255.0
    return np.clip(np.power(f, gamma) * 255.0, 0, 255).astype(np.uint8)


def _saturation(bgr: np.ndarray, factor: float = 1.12) -> np.ndarray:
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[..., 1] = np.clip(hsv[..., 1] * factor, 0, 255)
    return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)


def _sharpen(bgr: np.ndarray, amount: float = 0.5) -> np.ndarray:
    blur = cv2.GaussianBlur(bgr, (0, 0), 1.2)
    return cv2.addWeighted(bgr, 1 + amount, blur, -amount, 0)


def light_color(data: bytes) -> bytes:
    """Professional real-estate light & color: white balance, HDR contrast, tone, pop."""
    bgr = _to_bgr(data)
    bgr = _white_balance(bgr)
    bgr = _tone(bgr, 0.88)
    bgr = _clahe(bgr, 2.2)
    bgr = _saturation(bgr, 1.12)
    bgr = _sharpen(bgr, 0.5)
    return _to_jpeg(bgr)


def _auto_rotate(bgr: np.ndarray) -> np.ndarray:
    """Deskew: level the horizon using dominant near-horizontal lines (clamped ±5°)."""
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 60, 180)
    min_len = max(40, min(bgr.shape[:2]) // 4)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=120, minLineLength=min_len, maxLineGap=20)
    if lines is None:
        return bgr
    angles = []
    for x1, y1, x2, y2 in lines.reshape(-1, 4):
        ang = np.degrees(np.arctan2(float(y2 - y1), float(x2 - x1)))
        if abs(ang) < 20:
            angles.append(ang)
        elif abs(abs(ang) - 180) < 20:
            angles.append(ang - 180 if ang > 0 else ang + 180)
    if not angles:
        return bgr
    tilt = float(np.clip(np.median(angles), -5, 5))
    if abs(tilt) < 0.2:
        return bgr
    h, w = bgr.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), tilt, 1.0)
    return cv2.warpAffine(bgr, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def _keystone(bgr: np.ndarray) -> np.ndarray:
    """Mild vertical-perspective correction so converging verticals become plumb."""
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 60, 180)
    h, w = bgr.shape[:2]
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=120, minLineLength=h // 3, maxLineGap=25)
    if lines is None:
        return bgr
    slopes = []  # dx per unit dy for near-vertical lines
    for x1, y1, x2, y2 in lines.reshape(-1, 4):
        if abs(y2 - y1) < h // 4:
            continue
        ang = abs(np.degrees(np.arctan2(float(y2 - y1), float(x2 - x1))))
        if 70 < ang < 110:  # near vertical
            cx = (x1 + x2) / 2.0
            slope = (x2 - x1) / float(y2 - y1)
            slopes.append((cx, slope))
    if len(slopes) < 8:
        return bgr
    left = np.median([s for cx, s in slopes if cx < w / 2]) if any(cx < w / 2 for cx, _ in slopes) else 0.0
    right = np.median([s for cx, s in slopes if cx >= w / 2]) if any(cx >= w / 2 for cx, _ in slopes) else 0.0
    conv = (left - right)  # >0 when verticals converge toward the top
    if not np.isfinite(conv) or abs(conv) < 0.035:
        return bgr
    shift = float(np.clip(abs(conv) * h * 0.4, 0, w * 0.04))  # clamp to 4% width
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    if conv > 0:  # top narrower than needed -> widen the top
        dst = np.float32([[-shift, 0], [w + shift, 0], [w, h], [0, h]])
    else:
        dst = np.float32([[shift, 0], [w - shift, 0], [w, h], [0, h]])
    Mp = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(bgr, Mp, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    return warped


def straighten(data: bytes) -> bytes:
    bgr = _to_bgr(data)
    bgr = _auto_rotate(bgr)
    try:
        bgr = _keystone(bgr)
    except Exception:
        logger.warning("keystone skipped")
    return _to_jpeg(bgr)


def _sky_mask(bgr: np.ndarray) -> np.ndarray:
    """Detect a real sky region: cool/bluish, bright, in the upper frame, touching the top.

    Uses a 'coolness' test (blue channel > red channel) so warm/neutral interior
    ceilings and walls are NOT mistaken for sky.
    """
    h, w = bgr.shape[:2]
    b = bgr[..., 0].astype(np.int16)
    r = bgr[..., 2].astype(np.int16)
    cool = (b - r) > 6  # sky is bluish; lit ceilings tend to be neutral/warm
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    hh, ss, vv = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    grey_bright = (vv > 140) & (ss < 60)            # bright overcast sky
    bluish = (hh > 95) & (hh < 140) & (vv > 90)     # clearly blue sky
    cand = ((grey_bright | bluish) & cool).astype(np.uint8)
    # Restrict to the upper half of the frame.
    cand[int(h * 0.5):, :] = 0
    cand = cv2.morphologyEx(cand, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    cand = cv2.morphologyEx(cand, cv2.MORPH_CLOSE, np.ones((13, 13), np.uint8))
    n, labels = cv2.connectedComponents(cand)
    top_labels = set(np.unique(labels[0:max(2, h // 40), :])) - {0}
    if not top_labels:
        return np.zeros((h, w), np.uint8)
    mask = np.isin(labels, list(top_labels)).astype(np.uint8) * 255
    mask = cv2.GaussianBlur(mask, (0, 0), 9)  # feather edges
    return mask


def _make_sky(h: int, w: int) -> np.ndarray:
    """Procedural realistic blue sky: vertical gradient + soft clouds (BGR)."""
    # Vertical gradient: deep blue at top -> light blue near the horizon.
    top = np.array([170, 120, 60], dtype=np.float32)      # BGR deep blue
    bottom = np.array([235, 206, 165], dtype=np.float32)   # BGR light blue
    t = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    grad = (top[None, None, :] * (1 - t) + bottom[None, None, :] * t)
    sky = np.repeat(grad, w, axis=1)
    # Soft procedural clouds via upscaled low-frequency noise.
    small = np.random.rand(max(2, h // 40), max(2, w // 40)).astype(np.float32)
    clouds = cv2.resize(small, (w, h), interpolation=cv2.INTER_CUBIC)
    clouds = cv2.GaussianBlur(clouds, (0, 0), max(6, w // 120))
    clouds = np.clip((clouds - 0.55) * 3.0, 0, 1)          # keep only brighter puffs
    clouds *= np.clip(1.0 - t[..., 0], 0.25, 1.0)          # more clouds near horizon
    white = np.array([255, 255, 255], dtype=np.float32)
    sky = sky * (1 - clouds[..., None]) + white[None, None, :] * clouds[..., None]
    return np.clip(sky, 0, 255).astype(np.uint8)


def sky_replace(data: bytes) -> bytes:
    """Replace a detected real sky with a realistic blue sky (free, no AI). Interiors untouched."""
    bgr = _to_bgr(data)
    h, w = bgr.shape[:2]
    mask = _sky_mask(bgr)
    if mask.max() == 0 or (mask > 128).sum() < (h * w * 0.02):
        return light_color(data)  # no real sky -> just enhance light/color
    m = (mask.astype(np.float32) / 255.0)[..., None]
    sky = _make_sky(h, w).astype(np.float32)
    # Preserve a little of the original luminance so edges/clouds blend naturally.
    orig = bgr.astype(np.float32)
    sky = sky * 0.9 + orig * 0.1
    out = (orig * (1 - m) + sky * m).astype(np.uint8)
    out = _sharpen(out, 0.35)
    return _to_jpeg(out)


def inpaint(data: bytes, mask_bytes: bytes) -> bytes:
    """Remove painted areas (white in mask) by content-aware fill (free, no AI)."""
    bgr = _to_bgr(data)
    h, w = bgr.shape[:2]
    mimg = Image.open(io.BytesIO(mask_bytes)).convert("L")
    if mimg.size != (w, h):
        mimg = mimg.resize((w, h), Image.NEAREST)
    mask = np.array(mimg)
    mask = (mask > 40).astype(np.uint8) * 255
    if mask.sum() == 0:
        return _to_jpeg(bgr)
    mask = cv2.dilate(mask, np.ones((5, 5), np.uint8), iterations=1)
    result = cv2.inpaint(bgr, mask, 4, cv2.INPAINT_TELEA)
    return _to_jpeg(result)


def auto(data: bytes) -> bytes:
    """One-click essential enhancement: straighten + professional light/color."""
    bgr = _to_bgr(data)
    bgr = _auto_rotate(bgr)
    try:
        bgr = _keystone(bgr)
    except Exception:
        logger.warning("keystone skipped")
    bgr = _white_balance(bgr)
    bgr = _tone(bgr, 0.9)
    bgr = _clahe(bgr, 2.2)
    bgr = _saturation(bgr, 1.10)
    bgr = _sharpen(bgr, 0.55)
    return _to_jpeg(bgr)


def run(action_key: str, data: bytes) -> bytes:
    if action_key == "auto":
        return auto(data)
    if action_key == "light":
        return light_color(data)
    if action_key == "straighten":
        return straighten(data)
    if action_key == "sky":
        return sky_replace(data)
    raise ValueError(f"unsupported local action: {action_key}")
