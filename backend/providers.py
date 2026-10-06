"""AI provider adapters for the admin panel.

Supports adding external AI sources (OpenAI-compatible endpoints such as OpenAI,
OpenRouter, Nvidia NIM, Groq, Together, plus a curated fal.ai catalogue). Handles
model discovery, key/status validation, and running a real image edit through the
selected provider so an admin can override the default Gemini engine per tool.

All functions here are synchronous (network I/O); callers must run them in a thread.
"""
import io
import logging
import requests

logger = logging.getLogger("watchful.providers")

# ---------------------------------------------------------------------------
# Capability-based model detection
# ---------------------------------------------------------------------------
# Every detected model is classified by its REAL capability, not just its name.
# A model exposes one or more of these capabilities:
#   image_edit        image -> edited image (img2img / inpaint / outpaint / retouch)
#   image_generation  text  -> image (txt2img)
#   video             text/image/video -> video
#   vision            image -> text (captioning / OCR / VLM) — NOT an editor
#   text              text  -> text (LLM / chat / embeddings)
CAP_KEYS = ("image_edit", "image_generation", "video", "vision", "text")


def _caps(image_edit=False, image_generation=False, video=False, vision=False, text=False) -> dict:
    return {
        "image_edit": image_edit, "image_generation": image_generation,
        "video": video, "vision": vision, "text": text,
    }


def _kind_from_caps(caps: dict) -> str:
    if caps.get("video"):
        return "video"
    if caps.get("image_edit") or caps.get("image_generation"):
        return "image"
    if caps.get("vision"):
        return "vision"
    return "text"


# Known media-model registry (generic, extensible). First matching entry wins;
# ordered so specific editors match before generic generators / vision models.
# Match is by substring on the lowercased model id — add new models/providers
# here without touching the detection logic.
_REGISTRY = [
    # ---- image editors (img->img); most also do txt->img ----
    (("kontext",), _caps(image_edit=True, image_generation=True)),
    (("qwen-image-edit", "qwen-image", "image-edit", "image-to-image", "img2img",
      "inpaint", "outpaint", "instruct-pix2pix", "ip2p", "seededit"),
     _caps(image_edit=True, image_generation=True)),
    (("flux.2", "flux-2", "flux2"), _caps(image_edit=True, image_generation=True)),
    (("seedream",), _caps(image_edit=True, image_generation=True)),
    (("nano-banana", "nano_banana"), _caps(image_edit=True, image_generation=True)),
    (("gemini-2.5-flash-image", "gemini-3-pro-image", "gemini-3.1-flash-image",
      "gemini-2-flash-image"), _caps(image_edit=True, image_generation=True)),
    (("gpt-image",), _caps(image_edit=True, image_generation=True)),
    # ---- pure image generation (txt->img) ----
    (("dall-e", "dalle"), _caps(image_generation=True)),
    (("imagen",), _caps(image_generation=True)),
    (("stable-diffusion", "sdxl", "sd3", "sd-3", "sd-xl", "playground-v2",
      "flux.1-dev", "flux-dev", "flux.1-schnell", "flux-schnell", "flux.1-pro",
      "flux-pro", "flux.1", "flux-1", "flux1", "text-to-image", "text2image",
      "recraft", "ideogram", "luma-photon", "hidream"),
     _caps(image_generation=True)),
    # ---- video (text/image/video -> video) ----
    (("text-to-video", "image-to-video", "video-to-video", "-t2v", "-i2v",
      "_t2v", "_i2v", "video", "wan-", "wan2", "kling", "ltx", "sora", "veo",
      "mochi", "hunyuan-video", "cogvideo", "runway", "gen-3", "gen3", "pika",
      "stable-video", "svd", "seedance", "minimax"),
     _caps(video=True)),
    # ---- vision (img->text): NOT editors ----
    (("vision", "vila", "neva", "kosmos", "florence", "paligemma", "internvl",
      "qwen-vl", "qwen2-vl", "qwen2.5-vl", "llava", "moondream", "minicpm-v",
      "pixtral", "idefics", "ocr", "caption", "-vl-", "smolvlm"),
     _caps(vision=True)),
]

# Supplemental per-provider capability catalog for providers whose /v1/models
# does NOT list their multimedia models (e.g. NVIDIA). Keyed by the base-url host.
# These are MERGED into the detected list so media models always surface.
# Generic: add future providers/models here, no code changes needed elsewhere.
_PROVIDER_CATALOG = {
    "nvidia.com": [
        {"id": "black-forest-labs/flux.2-klein-4b", "name": "FLUX.2 Klein 4B",
         "capabilities": _caps(image_edit=True, image_generation=True)},
        {"id": "black-forest-labs/flux.1-kontext-dev", "name": "FLUX.1 Kontext [dev]",
         "capabilities": _caps(image_edit=True, image_generation=True)},
        {"id": "black-forest-labs/flux.1-dev", "name": "FLUX.1 [dev]",
         "capabilities": _caps(image_generation=True)},
        {"id": "black-forest-labs/flux.1-schnell", "name": "FLUX.1 [schnell]",
         "capabilities": _caps(image_generation=True)},
        {"id": "stabilityai/stable-diffusion-3.5-large", "name": "Stable Diffusion 3.5 Large",
         "capabilities": _caps(image_generation=True)},
    ],
}

# Curated fal.ai catalogue (fal has no key-authed /models listing endpoint).
FAL_MODELS = [
    {"id": "fal-ai/nano-banana/edit", "name": "Nano Banana (edit)", "capabilities": _caps(image_edit=True, image_generation=True)},
    {"id": "fal-ai/gemini-25-flash-image/edit", "name": "Gemini 2.5 Flash Image (edit)", "capabilities": _caps(image_edit=True, image_generation=True)},
    {"id": "fal-ai/flux-pro/kontext", "name": "FLUX.1 Kontext (edit)", "capabilities": _caps(image_edit=True, image_generation=True)},
    {"id": "fal-ai/qwen-image-edit", "name": "Qwen Image Edit", "capabilities": _caps(image_edit=True, image_generation=True)},
    {"id": "fal-ai/seedream/v4/edit", "name": "Seedream v4 (edit)", "capabilities": _caps(image_edit=True, image_generation=True)},
    {"id": "fal-ai/flux/dev", "name": "FLUX.1 [dev]", "capabilities": _caps(image_generation=True)},
]


def _host(base_url: str) -> str:
    try:
        from urllib.parse import urlparse
        return (urlparse(_norm(base_url)).hostname or "").lower()
    except Exception:
        return ""


def _modalities(meta: dict):
    """Extract (input_modalities, output_modalities) from provider metadata if present."""
    if not isinstance(meta, dict):
        return None, None
    arch = meta.get("architecture") if isinstance(meta.get("architecture"), dict) else {}
    inp = (meta.get("input_modalities") or arch.get("input_modalities")
           or meta.get("input_modality") or arch.get("input_modality"))
    out = (meta.get("output_modalities") or arch.get("output_modalities")
           or meta.get("output_modality") or arch.get("output_modality"))
    # OpenRouter sometimes encodes a single "modality" like "text+image->text".
    modality = meta.get("modality") or arch.get("modality")
    if (not inp or not out) and isinstance(modality, str) and "->" in modality:
        left, right = modality.split("->", 1)
        inp = inp or [t.strip() for t in left.replace("+", ",").split(",") if t.strip()]
        out = out or [t.strip() for t in right.replace("+", ",").split(",") if t.strip()]
    norm = lambda v: ([v] if isinstance(v, str) else list(v)) if v else None
    return norm(inp), norm(out)


def _caps_from_modalities(inp, out) -> dict:
    inp = {str(x).lower() for x in (inp or [])}
    out = {str(x).lower() for x in (out or [])}
    if not out:
        return None
    caps = _caps()
    if "video" in out:
        caps["video"] = True
    if "image" in out:
        if "image" in inp:
            caps["image_edit"] = True
        if "text" in inp or not inp:
            caps["image_generation"] = True
    if "text" in out and not (caps["image_edit"] or caps["image_generation"] or caps["video"]):
        if "image" in inp or "video" in inp:
            caps["vision"] = True
        else:
            caps["text"] = True
    if not any(caps.values()):
        caps["text"] = True
    return caps


def _caps_from_name(model_id: str) -> dict:
    low = (model_id or "").lower()
    for subs, caps in _REGISTRY:
        if any(s in low for s in subs):
            return dict(caps)
    return _caps(text=True)


def classify(meta, provider_host: str = "") -> dict:
    """Classify one model's capabilities. Priority: provider modality metadata,
    then the generic model registry, then a text fallback."""
    if isinstance(meta, dict) and isinstance(meta.get("capabilities"), list):
        tasks = set(meta["capabilities"])
        return _caps(image_edit="image_edit" in tasks,
                     image_generation="image_generation" in tasks,
                     video="video_generation" in tasks,
                     vision="vision" in tasks, text="text" in tasks)
    mid = meta.get("id") if isinstance(meta, dict) else str(meta)
    inp, out = _modalities(meta if isinstance(meta, dict) else {})
    caps = _caps_from_modalities(inp, out)
    if caps is None:
        caps = _caps_from_name(mid)
    return caps


def _ensure_caps(model: dict) -> dict:
    """Backfill capabilities for models stored in the old {kind,can_edit} format."""
    if isinstance(model.get("capabilities"), dict):
        c = model["capabilities"]
        return {k: bool(c.get(k)) for k in CAP_KEYS}
    if model.get("can_edit"):
        return _caps(image_edit=True, image_generation=True)
    if model.get("kind") == "image":
        return _caps(image_generation=True)
    if model.get("kind") == "video":
        return _caps(video=True)
    return _caps(text=True)


def _finalize_model(mid: str, name: str, caps: dict) -> dict:
    return {
        "id": mid, "name": name or mid,
        "capabilities": {k: bool(caps.get(k)) for k in CAP_KEYS},
        "kind": _kind_from_caps(caps),
        "can_edit": bool(caps.get("image_edit")),
        "can_video": bool(caps.get("video")),
    }


def _merge_catalog(models: list, base_url: str) -> list:
    """Merge supplemental per-provider media models that /v1/models omits.
    Host is matched by substring so any NVIDIA/other subdomain is covered."""
    host = _host(base_url)
    have = {m["id"] for m in models}
    for key, extra in _PROVIDER_CATALOG.items():
        if key not in host:
            continue
        for e in extra:
            if e["id"] in have:
                continue
            models.append(_finalize_model(e["id"], e.get("name"), e["capabilities"]))
            have.add(e["id"])
    return models


def _sort_models(models: list) -> list:
    order = {"image": 0, "video": 1, "vision": 2, "text": 3}
    models.sort(key=lambda m: (order.get(m.get("kind"), 9), m["id"]))
    return models


def _norm(base_url: str) -> str:
    return (base_url or "").strip().rstrip("/")


def detect(provider_type: str, base_url: str, api_key: str) -> dict:
    """Return {status, models:[{id,name,kind,capabilities,can_edit,can_video}], error?}.

    status one of: valid | no_credits | invalid_key | error
    """
    if provider_type == "fal":
        if not api_key:
            return {"status": "invalid_key", "models": []}
        models = [_finalize_model(m["id"], m["name"], m["capabilities"]) for m in FAL_MODELS]
        return {"status": "valid", "models": _sort_models(models)}

    url = _norm(base_url) + "/models"
    status = "valid"
    raw = []
    try:
        r = requests.get(url, headers={"Authorization": f"Bearer {api_key}"}, timeout=20)
        if r.status_code in (401, 403):
            return {"status": "invalid_key", "models": []}
        if r.status_code in (402, 429):
            status = "no_credits"
        elif r.status_code >= 400:
            status = "error"
        else:
            payload = r.json()
            raw = payload.get("data", payload) if isinstance(payload, dict) else payload
            if not isinstance(raw, list):
                raw = []
    except Exception as e:
        logger.warning("provider detect network error: %s", e)
        # Even on network error we can still surface catalog media models below.
        status = "error"

    host = _host(base_url)
    models = []
    for m in raw:
        if is_krai_gateway(base_url) and isinstance(m, dict) and m.get("object") == "web_target":
            continue
        mid = m.get("id") if isinstance(m, dict) else str(m)
        if not mid:
            continue
        caps = classify(m, host)
        models.append(_finalize_model(mid, (m.get("name") if isinstance(m, dict) else None) or mid, caps))

    # Merge supplemental catalog (providers that hide media models from /v1/models).
    models = _merge_catalog(models, base_url)
    # If the listing failed but the catalog provided media models, treat as valid.
    if status in ("error", "no_credits") and any(
        m["capabilities"]["image_edit"] or m["capabilities"]["image_generation"] or m["capabilities"]["video"]
        for m in models
    ):
        status = "valid"
    if status == "error" and not models:
        return {"status": "error", "models": [], "error": "no se pudo listar modelos"}
    return {"status": status, "models": _sort_models(models)}


def run_image_edit(provider: dict, model_id: str, image_bytes: bytes, prompt: str) -> bytes:
    """Run an image edit through an external provider. Returns PNG bytes or raises."""
    ptype = provider.get("type")
    api_key = provider.get("api_key")
    if is_krai_gateway(provider.get("base_url")):
        return _krai_edit(_norm(provider.get("base_url")), api_key, model_id, image_bytes, prompt)
    if ptype == "fal":
        return _fal_edit(api_key, model_id, image_bytes, prompt)
    return _openai_edit(_norm(provider.get("base_url")), api_key, model_id, image_bytes, prompt)


def is_krai_gateway(base_url: str) -> bool:
    from urllib.parse import urlparse
    url = urlparse(_norm(base_url))
    return url.scheme == "https" and url.path == "/api/gateway/v1"


def image_mime(data: bytes) -> str:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    raise RuntimeError("Formato de imagen no válido: usa JPEG, PNG o WebP.")


def _krai_edit(base_url, api_key, model_id, image_bytes, prompt):
    import base64
    import uuid
    if not image_bytes or len(image_bytes) > 8 * 1024 * 1024:
        raise RuntimeError("La fotografía debe ocupar como máximo 8 MiB.")
    mime = image_mime(image_bytes)
    try:
        response = requests.post(base_url + "/execute",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"task": "image_edit", "engine_hint": model_id,
                  "input": {"prompt": prompt, "image_b64": base64.b64encode(image_bytes).decode("ascii"),
                            "image_mime_type": mime},
                  "options": {"timeout_ms": 60000}, "client_request_id": str(uuid.uuid4())},
            timeout=(10, 90))
    except requests.Timeout as exc:
        raise RuntimeError("Tiempo de edición agotado. Comprueba Gemini antes de repetir.") from exc
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(f"KRAI respondió HTTP {response.status_code} sin una respuesta válida.") from exc
    if response.status_code >= 400 or payload.get("ok") is not True:
        detail = payload.get("detail") or payload.get("message") or payload.get("error") or f"HTTP {response.status_code}"
        if isinstance(detail, dict):
            detail = detail.get("message") or detail.get("detail") or f"HTTP {response.status_code}"
        raise RuntimeError(str(detail).replace(api_key or "\0", "[clave oculta]")[:300])
    for item in payload.get("artifacts") or []:
        if item.get("type") == "image" and item.get("data_b64"):
            try:
                result = base64.b64decode(item["data_b64"], validate=True)
            except ValueError as exc:
                raise RuntimeError("KRAI devolvió una imagen dañada.") from exc
            if image_mime(result) != item.get("mime_type"):
                raise RuntimeError("KRAI devolvió un formato de imagen incoherente.")
            return result
    raise RuntimeError("KRAI terminó sin devolver una fotografía.")


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
