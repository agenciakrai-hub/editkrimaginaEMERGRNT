"""Server-side conversion of HEIC/HEIF and RAW photos to optimized JPEG."""
import io
import logging

from PIL import Image

logger = logging.getLogger("watchful.imaging")

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    HEIF_OK = True
except Exception as e:  # noqa
    HEIF_OK = False
    logger.warning("pillow-heif not available: %s", e)

try:
    import rawpy  # noqa
    RAW_OK = True
except Exception as e:  # noqa
    RAW_OK = False
    logger.warning("rawpy not available: %s", e)

STANDARD_EXTS = {"jpg", "jpeg", "png", "webp"}
HEIC_EXTS = {"heic", "heif"}
RAW_EXTS = {"cr2", "cr3", "nef", "arw", "dng", "raf", "orf", "rw2", "pef", "srw", "sr2", "raw"}

MAX_DIM = 2560


def is_supported_input(ext: str) -> bool:
    return ext in STANDARD_EXTS or ext in HEIC_EXTS or ext in RAW_EXTS


def needs_conversion(ext: str) -> bool:
    return ext in HEIC_EXTS or ext in RAW_EXTS


def _downscale_and_encode(img: "Image.Image") -> bytes:
    if img.mode != "RGB":
        img = img.convert("RGB")
    w, h = img.size
    longest = max(w, h)
    if longest > MAX_DIM:
        scale = MAX_DIM / longest
        img = img.resize((round(w * scale), round(h * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90, optimize=True)
    return buf.getvalue()


def convert_to_jpeg(data: bytes, ext: str) -> bytes:
    """Convert HEIC/RAW bytes to optimized JPEG. Raises on failure."""
    if ext in HEIC_EXTS:
        if not HEIF_OK:
            raise RuntimeError("conversión HEIC no disponible")
        img = Image.open(io.BytesIO(data))
        return _downscale_and_encode(img)
    if ext in RAW_EXTS:
        if not RAW_OK:
            raise RuntimeError("conversión RAW no disponible")
        with rawpy.imread(io.BytesIO(data)) as raw:
            rgb = raw.postprocess(use_camera_wb=True, no_auto_bright=False, output_bps=8)
        return _downscale_and_encode(Image.fromarray(rgb))
    raise RuntimeError("formato no convertible")
