"""Photo-to-video transports. Submit once; never silently switch providers."""
import base64
import io
import time
import uuid
from urllib.parse import urlparse
import requests
from PIL import Image, ImageOps
import providers

MAX_VIDEO_BYTES = 128 * 1024 * 1024
NVIDIA_VIDEO_MODEL = "nvidia/cosmos3-nano"


def supports_video(provider, model):
    host = urlparse(provider.get("base_url", "")).hostname or ""
    return providers.is_krai_gateway(provider.get("base_url")) or (
        host in {"integrate.api.nvidia.com", "ai.api.nvidia.com"} and model == NVIDIA_VIDEO_MODEL
    )


def _input_image(image_bytes):
    if not image_bytes:
        raise providers.ProviderRequestError("invalid_image", 400, "No se recibió una fotografía para el vídeo.")
    # Work on a copy for inference; preserve the original stored photo.
    try:
        with Image.open(io.BytesIO(image_bytes)) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            image.thumbnail((1920, 1920), Image.Resampling.LANCZOS)
            out = io.BytesIO()
            image.save(out, format="JPEG", quality=90)
            return out.getvalue()
    except (OSError, ValueError, Image.DecompressionBombError):
        raise providers.ProviderRequestError("invalid_image", 400, "No se pudo preparar la fotografía para vídeo.") from None


def _mp4(encoded):
    try:
        if not isinstance(encoded, str) or len(encoded) > MAX_VIDEO_BYTES * 4 // 3 + 8:
            raise ValueError()
        result = base64.b64decode(encoded, validate=True)
        if len(result) < 12 or result[4:8] != b"ftyp":
            raise ValueError()
        return result
    except (ValueError, TypeError):
        raise providers.ProviderRequestError("invalid_video", 502, "El proveedor no devolvió un vídeo MP4 válido.") from None


def _check_video_response(response):
    status = response.status_code
    if status < 400:
        return
    code, message = {
        402: ("provider_credits", "El proveedor de vídeo no tiene créditos disponibles. Los créditos de la app son independientes."),
        429: ("provider_quota", "El proveedor de vídeo ha alcanzado su límite de uso. Espera a que se restablezca."),
        409: ("provider_busy", "El proveedor está ocupado con otra solicitud. Espera antes de repetir."),
        401: ("provider_auth", "La clave o sesión del proveedor de vídeo no es válida."),
        403: ("provider_auth", "La cuenta no tiene permiso para usar este modelo de vídeo."),
        404: ("provider_model", "El modelo de vídeo no está disponible con esta conexión."),
        422: ("provider_contract", "El proveedor rechazó los parámetros o la fotografía del vídeo."),
        400: ("provider_contract", "El proveedor rechazó los parámetros o la fotografía del vídeo."),
        504: ("provider_timeout", "El proveedor agotó el tiempo de vídeo. Comprueba su estado antes de repetir."),
    }.get(status, ("provider_unavailable", "El servicio de vídeo no respondió correctamente."))
    raise providers.ProviderRequestError(code, status, message)


def _nvidia_video(provider, image, prompt, seconds, aspect_ratio):
    deadline = time.monotonic() + 420
    frames = min(193, max(25, int(float(seconds) * 24) // 8 * 8 + 1))
    headers = {"Authorization": "Bearer " + provider.get("api_key", ""),
               "Accept": "application/json", "NVCF-POLL-SECONDS": "30"}
    payload = {"model_mode": "image2video", "input_reference": "data:image/jpeg;base64," + base64.b64encode(image).decode("ascii"),
               "prompt": prompt[:3000], "resolution": "480_9_16" if aspect_ratio == "9:16" else "480_16_9",
               "num_frames": frames, "num_inference_steps": 35, "fps": 24, "seed": 42}
    response = requests.post("https://ai.api.nvidia.com/v1/cosmos/nvidia/cosmos3-nano",
                             headers=headers, json=payload, timeout=(10, 60), allow_redirects=False)
    request_id = response.headers.get("NVCF-REQID") or response.headers.get("nvcf-reqid")
    while response.status_code == 202:
        try:
            request_id = str(uuid.UUID(request_id))
        except (ValueError, TypeError, AttributeError):
            raise providers.ProviderRequestError("unknown_outcome", 502, "NVIDIA aceptó el vídeo pero no devolvió un identificador. No lo reenvíes automáticamente.") from None
        if time.monotonic() >= deadline:
            raise providers.ProviderRequestError("provider_timeout", 504, "NVIDIA sigue procesando el vídeo. No se reenviará automáticamente.") 
        time.sleep(2)
        response = requests.get("https://api.nvcf.nvidia.com/v2/nvcf/pexec/status/" + request_id,
                                headers=headers, timeout=(10, min(40, max(1, deadline-time.monotonic()))), allow_redirects=False)
    _check_video_response(response)
    if response.status_code == 302:
        location = response.headers.get("Location", "")
        target = urlparse(location)
        # Only fetch NVIDIA's documented large-result download, without its API token.
        if target.scheme != "https" or not target.hostname or not (
            target.hostname.endswith(".nvidia.com") or target.hostname.endswith(".amazonaws.com")
        ) or target.username or target.password:
            raise providers.ProviderRequestError("invalid_result", 502, "NVIDIA devolvió una dirección de resultado no admitida.")
        with requests.get(location, timeout=(10, 60), stream=True, allow_redirects=False) as download:
            _check_video_response(download)
            if download.status_code != 200:
                raise providers.ProviderRequestError("invalid_result", 502, "No se pudo recuperar el resultado de NVIDIA.")
            chunks, count = [], 0
            for chunk in download.iter_content(1024*1024):
                count += len(chunk)
                if count > MAX_VIDEO_BYTES:
                    raise providers.ProviderRequestError("invalid_result", 502, "El vídeo supera el tamaño permitido.")
                chunks.append(chunk)
            raw = b"".join(chunks)
            if len(raw) >= 12 and raw[4:8] == b"ftyp":
                return raw
            import json
            return _mp4(json.loads(raw)["b64_video"])
    return _mp4(response.json().get("b64_video"))


def run_video(provider, model, image_bytes, prompt, seconds, aspect_ratio):
    if not supports_video(provider, model):
        raise providers.ProviderRequestError("unsupported_video", 400, "Este modelo no está conectado para convertir fotos en vídeo. Selecciona Gemini, Flow o NVIDIA Cosmos3 Nano.")
    image = _input_image(image_bytes)
    try:
        if not providers.is_krai_gateway(provider.get("base_url")):
            return _nvidia_video(provider, image, prompt, seconds, aspect_ratio)
        response = requests.post(providers._norm(provider["base_url"])+"/execute",
            headers={"Authorization": f"Bearer {provider.get('api_key','')}"},
            json={"task":"video_generation","engine_hint":model,
                  "input":{"prompt":prompt,"image_b64":base64.b64encode(image).decode("ascii"),
                           "image_mime_type":"image/jpeg","duration":seconds,"aspect_ratio":aspect_ratio},
                  "options":{"timeout_ms":300000},"client_request_id":str(uuid.uuid4())}, timeout=(10,320))
        _check_video_response(response)
        payload = response.json()
        if payload.get("ok") is not True:
            raise providers.ProviderRequestError("provider_unavailable", 502, "KRAI no pudo generar el vídeo.")
        for artifact in payload.get("artifacts") or []:
            if artifact.get("type") == "video":
                return _mp4(artifact.get("data_b64"))
        raise providers.ProviderRequestError("invalid_video", 502, "KRAI terminó sin devolver un vídeo MP4.")
    except requests.Timeout:
        raise providers.ProviderRequestError("provider_timeout", 504, "El proveedor agotó el tiempo de vídeo. Comprueba su estado antes de repetir.") from None
    except requests.RequestException:
        raise providers.ProviderRequestError("provider_unavailable", 503, "No se pudo conectar con el proveedor de vídeo.") from None
