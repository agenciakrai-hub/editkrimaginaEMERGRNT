"""AI provider adapters for the admin panel.

Supports adding external AI sources (OpenAI-compatible endpoints such as OpenAI,
OpenRouter, Nvidia NIM, Groq, Together, plus a curated fal.ai catalogue). Handles
model discovery, key/status validation, and running a real image edit through the
selected provider so an admin can override the default Gemini engine per tool.

All functions here are synchronous (network I/O); callers must run them in a thread.
"""
import io
import logging
import json
import requests

logger = logging.getLogger("watchful.providers")

# NVIDIA hosted Visual GenAI endpoint for FLUX.2 Klein 4B.
NVIDIA_FLUX2_KLEIN_MODEL = "black-forest-labs/flux.2-klein-4b"
NVIDIA_FLUX2_KLEIN_URL = (
    "https://ai.api.nvidia.com/v1/genai/black-forest-labs/flux.2-klein-4b"
)

# Capability hints used only when the provider does not expose structured
# input/output modalities. We intentionally do NOT classify generic vision/VLM
# models as image editors: seeing an image is not the same as editing one.
_IMAGE_EDIT_HINTS = (
    "image-edit", "image_edit", "image/edit", "qwen-image-edit",
    "flux.2-klein", "flux.1-kontext", "kontext", "seedream", "nano-banana/edit",
    "instruct-pix2pix", "omnigen", "kolors-ip-adapter",
)
_VIDEO_HINTS = (
    "text-to-video", "image-to-video", "video-to-video", "video-generation",
    "video-edit", "video_edit", "wan2", "wan-", "hunyuanvideo", "ltx-video",
    "cogvideo", "kling", "seedance", "vidu", "sora", "veo", "cosmos3-nano",
    "cosmos-transfer", "animate-2", "lipsync", "video-super-resolution",
)

NVIDIA_MEDIA_CATALOG = [
    {"id": "black-forest-labs/flux.2-klein-4b", "name": "FLUX.2 Klein 4B (Image Edit)", "kind": "image", "can_edit": True, "can_video": False},
    {"id": "nvidia/qwen-image-edit-nvpcb-ovsl2sl", "name": "Qwen Image Edit NVIDIA PCB", "kind": "image", "can_edit": True, "can_video": False},
    {"id": "nvidia/cosmos3-nano", "name": "Cosmos3 Nano (Video)", "kind": "video", "can_edit": False, "can_video": True},
    {"id": "nvidia/cosmos-transfer2.5-2b", "name": "Cosmos Transfer 2.5 (Video)", "kind": "video", "can_edit": False, "can_video": True},
    {"id": "wan-ai/wan2.2-animate-2-14b", "name": "Wan2.2 Animate 2 (Video)", "kind": "video", "can_edit": False, "can_video": True},
]

# Curated fal.ai catalogue (fal has no key-authed /models listing endpoint).
FAL_MODELS = [
    {"id": "fal-ai/nano-banana/edit", "name": "Nano Banana (edit)", "kind": "image", "can_edit": True, "can_video": False},
    {"id": "fal-ai/gemini-25-flash-image/edit", "name": "Gemini 2.5 Flash Image (edit)", "kind": "image", "can_edit": True},
    {"id": "fal-ai/flux-pro/kontext", "name": "FLUX.1 Kontext (edit)", "kind": "image", "can_edit": True},
    {"id": "fal-ai/flux/dev", "name": "FLUX.1 [dev]", "kind": "image", "can_edit": False, "can_video": False},
    {"id": "fal-ai/qwen-image-edit", "name": "Qwen Image Edit", "kind": "image", "can_edit": True},
    {"id": "fal-ai/seedream/v4/edit", "name": "Seedream v4 (edit)", "kind": "image", "can_edit": True},
]


def _capabilities_for_model(model) -> tuple[str, bool, bool]:
    """Return (kind, can_edit, can_video) from provider metadata first."""
    if isinstance(model, dict):
        mid = str(model.get("id") or "").strip()
        raw = json.dumps(model, ensure_ascii=False, default=str).lower()
    else:
        mid = str(model or "").strip()
        raw = mid.lower()

    # These consume media but do not produce edited/generated media.
    analysis_only = any(x in raw for x in (
        "vision-language", "vision language", "vlm", "image-to-text",
        "video understanding", "ocr", "embedding", "embed-", "retriever",
        "rerank", "caption", "classification", "content-safety",
        "topic-control", "guard", "asr", "translation",
    ))

    edit_signal = any(x in raw for x in (
        "image editing", "image_edit", "image-edit", "image-to-image",
        "image2image", "img2img", "inpainting", "outpainting",
    ))
    video_signal = any(x in raw for x in (
        "text-to-video", "image-to-video", "video-to-video",
        "video generation", "video-generation", "video editing",
        "video-to-world", "output_video", "b64_video", "mp4",
    ))

    # Structured input/output metadata, when the provider exposes it.
    has_input_image = any(x in raw for x in (
        '"input_modalities": ["image"', '"input_modalities": ["text", "image"',
        '"input": "image"', '"input_type": "image"', '"image" input',
    ))
    has_output_image = any(x in raw for x in (
        '"output_modalities": ["image"', '"output": "image"',
        '"output_type": "image"', '"b64_image"',
    ))
    structured_image_io = has_input_image and has_output_image

    edit_name = any(h in mid.lower() for h in _IMAGE_EDIT_HINTS)
    video_name = any(h in mid.lower() for h in _VIDEO_HINTS)

    can_edit = not analysis_only and (edit_signal or structured_image_io or edit_name)
    can_video = not analysis_only and (video_signal or video_name)

    if can_edit:
        return "image", True, False
    if can_video:
        return "video", False, True
    return "other", False, False


def _public_model(model) -> dict | None:
    mid = model.get("id") if isinstance(model, dict) else str(model)
    if not mid:
        return None
    kind, can_edit, can_video = _capabilities_for_model(model)
    if not (can_edit or can_video):
        return None
    name = model.get("name", mid) if isinstance(model, dict) else mid
    return {
        "id": mid,
        "name": name,
        "kind": kind,
        "can_edit": can_edit,
        "can_video": can_video,
    }


def _norm(base_url: str) -> str:
    return (base_url or "").strip().rstrip("/")


def _is_nvidia_openai_base(base_url: str) -> bool:
    return _norm(base_url).lower() == "https://integrate.api.nvidia.com/v1"


def _nvidia_catalog_models():
    # NVIDIA's /v1/models endpoint currently exposes the LLM catalogue and does
    # not list FLUX.2 Klein 4B. Add the hosted Visual GenAI model explicitly so
    # the admin UI can route it through its image-specific endpoint.
    return [{
        "id": NVIDIA_FLUX2_KLEIN_MODEL,
        "name": "FLUX.2 Klein 4B (NVIDIA Image Editing)",
        "kind": "image",
        "can_edit": True,
    }]


def detect(provider_type: str, base_url: str, api_key: str) -> dict:
    """Return {status, models:[{id,name,kind,can_edit}], error?}.

    status one of: valid | no_credits | invalid_key | error
    """
    if provider_type == "fal":
        if not api_key:
            return {"status": "invalid_key", "models": []}
        return {"status": "valid", "models": [dict(m) for m in FAL_MODELS]}

    url = _norm(base_url) + "/models"
    try:
        r = requests.get(url, headers={"Authorization": f"Bearer {api_key}"}, timeout=20)
    except Exception as e:
        logger.warning("provider detect network error: %s", e)
        return {"status": "error", "models": [], "error": str(e)}

    if r.status_code in (401, 403):
        return {"status": "invalid_key", "models": []}
    if r.status_code in (402, 429):
        return {"status": "no_credits", "models": []}
    if r.status_code >= 400:
        return {"status": "error", "models": [], "error": f"HTTP {r.status_code}"}

    try:
        payload = r.json()
        raw = payload.get("data", payload) if isinstance(payload, dict) else payload
        if not isinstance(raw, list):
            raw = []

        models = []
        for m in raw:
            public = _public_model(m)
            if public:
                models.append(public)

        if _is_nvidia_openai_base(base_url):
            existing = {m["id"] for m in models}
            for m in _nvidia_catalog_models():
                if m["id"] not in existing:
                    models.append(m)

        models.sort(key=lambda x: (x["kind"] != "image", x["kind"] != "video", x["id"]))
        return {"status": "valid", "models": models}
    except Exception as e:
        logger.warning("provider detect parse error: %s", e)
        return {"status": "error", "models": [], "error": "respuesta no válida"}


def run_image_edit(provider: dict, model_id: str, image_bytes: bytes, prompt: str) -> bytes:
    """Run an image edit through an external provider. Returns image bytes or raises."""
    ptype = provider.get("type")
    api_key = provider.get("api_key")
    base_url = _norm(provider.get("base_url"))

    if ptype == "fal":
        return _fal_edit(api_key, model_id, image_bytes, prompt)

    # NVIDIA's hosted FLUX.2 Klein endpoint is not exposed through the normal
    # OpenAI-compatible /images/edits route. It requires its Visual GenAI URL
    # and a JSON body containing the image(s).
    if _is_nvidia_openai_base(base_url) and model_id == NVIDIA_FLUX2_KLEIN_MODEL:
        return _nvidia_flux2_edit(api_key, image_bytes, prompt)

    return _openai_edit(base_url, api_key, model_id, image_bytes, prompt)


def _openai_edit(base_url: str, api_key: str, model_id: str, image_bytes: bytes, prompt: str) -> bytes:
    import base64
    files = {"image": ("photo.jpg", io.BytesIO(image_bytes), "image/jpeg")}
    data = {"model": model_id, "prompt": prompt, "n": "1", "size": "auto"}
    r = requests.post(
        base_url + "/images/edits",
        headers={"Authorization": f"Bearer {api_key}"},
        files=files, data=data, timeout=(15, 180),
    )
    r.raise_for_status()
    payload = r.json()
    item = payload["data"][0]
    if item.get("b64_json"):
        return base64.b64decode(item["b64_json"])
    if item.get("url"):
        img = requests.get(item["url"], timeout=30)
        img.raise_for_status()
        return img.content
    raise RuntimeError("provider_no_image")


def _nvidia_flux2_edit(api_key: str, image_bytes: bytes, prompt: str) -> bytes:
    """Edit a user image through NVIDIA's hosted FLUX.2 Klein 4B endpoint.

    NVIDIA documents this endpoint separately from /v1/models and /v1/chat.
    The hosted Preview API currently documents a restricted image input set;
    if NVIDIA rejects a user-provided image, the error is surfaced to the app
    rather than silently falling back to Gemini.
    """
    import base64

    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    payload = {
        "mode": "Image Editing",
        "prompt": prompt,
        "image": [f"data:image/jpeg;base64,{image_b64}"],
        "n": 1,
        "samples": 1,
        "response_format": "b64_json",
        "seed": 0,
        "steps": 4,
        "width": 1024,
        "height": 1024,
    }
    r = requests.post(
        NVIDIA_FLUX2_KLEIN_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=(20, 240),
    )
    if r.status_code >= 400:
        detail = r.text[:1000]
        raise RuntimeError(f"nvidia_flux2_http_{r.status_code}:{detail}")

    payload_out = r.json()

    # OpenAI-compatible response shape.
    data = payload_out.get("data") if isinstance(payload_out, dict) else None
    if isinstance(data, list) and data:
        item = data[0] if isinstance(data[0], dict) else {}
        if item.get("b64_json"):
            return base64.b64decode(item["b64_json"])
        if item.get("url"):
            img = requests.get(item["url"], timeout=60)
            img.raise_for_status()
            return img.content

    # NIM Visual GenAI response shape.
    artifacts = payload_out.get("artifacts") if isinstance(payload_out, dict) else None
    if isinstance(artifacts, list) and artifacts:
        item = artifacts[0] if isinstance(artifacts[0], dict) else {}
        if item.get("base64"):
            return base64.b64decode(item["base64"])

    raise RuntimeError("nvidia_flux2_no_image")


def _fal_edit(api_key: str, model_id: str, image_bytes: bytes, prompt: str) -> bytes:
    import base64
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    data_uri = f"data:image/png;base64,{b64}"
    r = requests.post(
        f"https://fal.run/{model_id}",
        headers={"Authorization": f"Key {api_key}", "Content-Type": "application/json"},
        json={"prompt": prompt, "image_url": data_uri, "num_images": 1},
        timeout=180,
    )
    r.raise_for_status()
    payload = r.json()
    images = payload.get("images") or payload.get("data", {}).get("images") or []
    if not images:
        raise RuntimeError("provider_no_image")
    url = images[0].get("url") if isinstance(images[0], dict) else images[0]
    if isinstance(url, str) and url.startswith("data:"):
        return base64.b64decode(url.split(",", 1)[1])
    img = requests.get(url, timeout=60)
    img.raise_for_status()
    return img.content
