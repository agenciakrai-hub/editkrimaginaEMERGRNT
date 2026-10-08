"""KRAI video generation. No provider substitution on failure."""
import base64
import uuid
import requests
import providers

MAX_VIDEO_BYTES=128*1024*1024

def run_video(provider, model, image_bytes, prompt, seconds, aspect_ratio):
    if not providers.is_krai_gateway(provider.get("base_url")):
        raise RuntimeError("Selecciona un proveedor KRAI compatible con vídeo")
    if not image_bytes or len(image_bytes)>8*1024*1024:
        raise RuntimeError("La fotografía debe ocupar como máximo 8 MiB")
    response=requests.post(providers._norm(provider["base_url"])+"/execute",
        headers={"Authorization":f"Bearer {provider.get('api_key','')}"},
        json={"task":"video_generation","engine_hint":model,
              "input":{"prompt":prompt,"image_b64":base64.b64encode(image_bytes).decode("ascii"),"image_mime_type":providers.image_mime(image_bytes),"duration":seconds,"aspect_ratio":aspect_ratio},
              "options":{"timeout_ms":300000},"client_request_id":str(uuid.uuid4())},timeout=(10,320))
    providers._check_edit_response(response)
    payload=response.json()
    if payload.get("ok") is not True: raise RuntimeError("KRAI no pudo generar el vídeo")
    for artifact in payload.get("artifacts") or []:
        if artifact.get("type")!="video": continue
        encoded=artifact.get("data_b64")
        if encoded:
            if len(encoded)>MAX_VIDEO_BYTES*4//3+8: raise RuntimeError("Vídeo demasiado grande")
            result=base64.b64decode(encoded,validate=True)
            if len(result)<12 or result[4:8]!=b"ftyp": raise RuntimeError("KRAI no devolvió un vídeo MP4 válido")
            return result
    raise RuntimeError("KRAI terminó sin devolver un vídeo MP4 integrado. No se usará otro motor")
