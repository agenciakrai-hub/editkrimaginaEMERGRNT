"""Authenticated panorama conversion and tour planning."""
import asyncio
import io
import os
from pathlib import Path

import requests
from fastapi import Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from PIL import Image, ImageOps
from pydantic import BaseModel, Field

import imaging

FORMATS = imaging.STANDARD_EXTS | imaging.HEIC_EXTS | {"tif", "tiff", "avif"}
MAX_UPLOAD = 40 * 1024 * 1024


class Preview(BaseModel):
    image: str = Field(pattern=r"^data:image/jpeg;base64,[A-Za-z0-9+/=]+$", max_length=180_000)


class PlanInput(BaseModel):
    scenes: list[Preview] = Field(min_length=1, max_length=20)


class Link(BaseModel):
    target: int = Field(ge=0)
    yaw: float = Field(ge=-180, le=180)
    pitch: float = Field(ge=-85, le=85)


class Scene(BaseModel):
    index: int = Field(ge=0)
    name: str = Field(min_length=1, max_length=80)
    links: list[Link] = Field(max_length=19)


class Plan(BaseModel):
    scenes: list[Scene]


def normalize(data):
    with Image.open(io.BytesIO(data)) as source:
        image = ImageOps.exif_transpose(source)
        if abs(image.width / image.height - 2) > 0.04:
            raise ValueError("La foto debe ser una panorámica equirectangular 360° en proporción 2:1.")
        image.thumbnail((4096, 2048), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        image.convert("RGB").save(output, format="JPEG", quality=92)
        return output.getvalue()


def validate_plan(plan, count):
    if sorted(scene.index for scene in plan.scenes) != list(range(count)):
        raise ValueError("invalid scenes")
    graph = {}
    for scene in plan.scenes:
        targets = {link.target for link in scene.links}
        if len(targets) != len(scene.links) or scene.index in targets or any(t >= count for t in targets):
            raise ValueError("invalid links")
        graph[scene.index] = targets
    visited = set()
    pending = [plan.scenes[0].index]
    while pending:
        index = pending.pop()
        if index not in visited:
            visited.add(index)
            pending.extend(graph[index] - visited)
    if len(visited) != count:
        raise ValueError("disconnected tour")
    return plan


def suggest_plan(data, base_url, model, key):
    content = [{
        "type": "text",
        "text": (
            "Plan a Spanish real estate virtual tour from the numbered equirectangular previews. "
            "Return JSON only, in the shape "
            '{"scenes":[{"index":0,"name":"Entrada","links":[{"target":1,"yaw":0,"pitch":0}]}]}. '
            "Include every index exactly once and put the best starting room first. Prefer real "
            "connections inferred from visible doors and hallways, and make all scenes reachable "
            "from the start. Add links in both directions. Use distinct targets per scene, no "
            "self links. Estimate hotspot yaw: center of image 0, left edge -180, right edge 180. "
            "Pitch is positive above the horizon and must be between -85 and 85. "
            "Keep scene names concise and in Spanish."
        ),
    }]
    for index, scene in enumerate(data.scenes):
        content.extend([
            {"type": "text", "text": f"Escena {index}"},
            {"type": "image_url", "image_url": {"url": scene.image}},
        ])
    result = requests.post(
        base_url.rstrip("/") + "/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": model,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": content}],
        },
        timeout=(10, 65),
    )
    result.raise_for_status()
    plan = Plan.model_validate_json(result.json()["choices"][0]["message"]["content"])
    return validate_plan(plan, len(data.scenes))


def register_tour_routes(api, current_user):
    @api.post("/tours/panorama")
    async def panorama(file: UploadFile = File(...), user=Depends(current_user)):
        if Path(file.filename or "").suffix.lower().lstrip(".") not in FORMATS:
            raise HTTPException(415, "Formato no compatible. Usa JPG, PNG, WebP, TIFF, AVIF o HEIC/HEIF.")
        data = await file.read(MAX_UPLOAD + 1)
        if len(data) > MAX_UPLOAD:
            raise HTTPException(413, "Cada panorama admite hasta 40 MB.")
        try:
            jpeg = await asyncio.to_thread(normalize, data)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except (OSError, Image.DecompressionBombError) as exc:
            raise HTTPException(422, "No se pudo leer esta panorámica.") from exc
        return Response(jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @api.post("/tours/plan")
    async def plan(data: PlanInput, user=Depends(current_user)):
        base_url = os.getenv("TOUR_AI_BASE_URL")
        model = os.getenv("TOUR_AI_MODEL")
        key = os.getenv("TOUR_AI_API_KEY")
        if not all((base_url, model, key)):
            raise HTTPException(503, "El motor de IA de Tour virtual aún no está configurado.")
        try:
            return await asyncio.to_thread(suggest_plan, data, base_url, model, key)
        except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as exc:
            raise HTTPException(502, "La IA no devolvió un recorrido válido. Puedes reintentar o editar el recorrido.") from exc
