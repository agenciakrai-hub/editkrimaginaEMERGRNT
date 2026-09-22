"""Server-side conversion of HEIC/HEIF and RAW photos to optimized JPEG."""
import io
import logging

from PIL import Image, ImageFilter

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


def finalize_edit(edited: bytes, source: bytes) -> bytes:
    """Bring an AI-edited image up to the source resolution and deliver a crisp JPEG.

    Nano Banana returns ~1024px images; real-estate delivery needs the original
    resolution. We upscale (Lanczos) to match the source's long side and apply a
    light unsharp mask so the result is client-ready.
    """
    out = Image.open(io.BytesIO(edited))
    if out.mode != "RGB":
        out = out.convert("RGB")
    try:
        with Image.open(io.BytesIO(source)) as src:
            tw, th = src.size
    except Exception:
        tw, th = out.size
    ow, oh = out.size
    if max(ow, oh) > 0 and max(tw, th) > max(ow, oh):
        scale = max(tw, th) / max(ow, oh)
        out = out.resize((max(1, round(ow * scale)), max(1, round(oh * scale))), Image.LANCZOS)
        out = out.filter(ImageFilter.UnsharpMask(radius=1.6, percent=110, threshold=2))
    buf = io.BytesIO()
    out.save(buf, format="JPEG", quality=95, subsampling=0, optimize=True)
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
