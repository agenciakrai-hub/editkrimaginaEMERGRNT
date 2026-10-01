from dotenv import load_dotenv
from pathlib import Path
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

import os
import io
import uuid
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional

import requests
from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, UploadFile, File, Form, Query, Depends
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, EmailStr, Field

import auth as auth_utils
import storage
import ai_edit
import imaging
import local_edit
import video as video_gen
import payments as pay
import providers as ai_providers
from admin import register_admin_routes
import stripe
import tempfile
import shutil

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("watchful")

app = FastAPI(title="Watchful API")
api = APIRouter(prefix="/api")

FREE_CREDITS = 30
OWNER_EMAILS = {
    e.strip().lower()
    for e in os.environ.get("OWNER_EMAIL", "krimagina2025@gmail.com,krimagina@gmail.com").split(",")
    if e.strip()
}
SUPER_ADMIN_EMAILS = {
    e.strip().lower()
    for e in os.environ.get("SUPER_ADMIN_EMAIL", "krimagina2025@gmail.com").split(",")
    if e.strip()
}


def is_owner(user: dict) -> bool:
    if not user:
        return False
    return user.get("role") == "owner" or (user.get("email", "").lower() in OWNER_EMAILS)


def is_super_admin(user: dict) -> bool:
    if not user:
        return False
    return user.get("email", "").lower() in SUPER_ADMIN_EMAILS


async def log_usage(user_id: str, kind: str, action: str, credits: int, gemini_calls: int, provider: str, model: str = None):
    """Record a consumption event for the admin usage dashboard."""
    try:
        await db.usage_events.insert_one({
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "kind": kind,  # photo | video
            "action": action,
            "credits": credits,
            "gemini_calls": gemini_calls,
            "ai_calls": 1 if kind == "photo" else 0,
            "provider": provider,
            "model": model,
            "at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception:
        logger.exception("usage log failed")


async def get_tool_override(action_key: str):
    """Return the administrator-selected engine for a photo tool.

    An explicit admin selection is authoritative. If it is configured but the
    provider/model is unavailable, raise instead of silently falling back to
    Emergent/Gemini. This keeps provider routing independent from app credits.
    """
    settings = await db.ai_settings.find_one({"id": "tool_overrides"})
    if not settings:
        return None
    ov = (settings.get("overrides") or {}).get(action_key)
    if not ov or not ov.get("provider_id") or not ov.get("model_id"):
        return None

    prov = await db.ai_providers.find_one({"id": ov["provider_id"]})
    if not prov:
        raise ProviderEditError(
            provider="proveedor configurado",
            model=ov["model_id"],
            reason="El proveedor seleccionado por el administrador no existe.",
        )
    if prov.get("status") != "valid":
        raise ProviderEditError(
            provider=prov.get("name") or prov.get("type") or "proveedor",
            model=ov["model_id"],
            reason=f"El proveedor no está disponible (estado: {prov.get('status', 'desconocido')}).",
        )

    model = next((m for m in prov.get("models", []) if m.get("id") == ov["model_id"]), None)
    if not model:
        raise ProviderEditError(
            provider=prov.get("name") or prov.get("type") or "proveedor",
            model=ov["model_id"],
            reason="El modelo seleccionado ya no está disponible en el proveedor.",
        )
    if not model.get("can_edit"):
        raise ProviderEditError(
            provider=prov.get("name") or prov.get("type") or "proveedor",
            model=ov["model_id"],
            reason="El modelo seleccionado no está habilitado para edición de imágenes.",
        )
    if not prov.get("enabled", {}).get(ov["model_id"], {}).get("photo"):
        raise ProviderEditError(
            provider=prov.get("name") or prov.get("type") or "proveedor",
            model=ov["model_id"],
            reason="El modelo seleccionado no está habilitado para Foto.",
        )
    return prov, ov["model_id"]

class ProviderEditError(RuntimeError):
    """Safe, user-facing error for an explicitly selected external image engine."""

    def __init__(self, provider: str, model: str, reason: str = ""):
        self.provider = provider
        self.model = model
        self.reason = reason
        super().__init__(f"provider_edit_failed:{provider}:{model}:{reason}")

COOKIE_KW = dict(httponly=True, secure=True, samesite="none", path="/")


# ---------- Models ----------
class RegisterInput(BaseModel):
    email: EmailStr
    password: str
    name: str


class LoginInput(BaseModel):
    email: EmailStr
    password: str


class SessionInput(BaseModel):
    session_id: str


class PropertyInput(BaseModel):
    name: str
    address: Optional[str] = ""


class EditInput(BaseModel):
    action: str
    options: Optional[dict] = None
    disclosure: Optional[bool] = None


class BatchInput(BaseModel):
    action: str
    options: Optional[dict] = None
    disclosure: Optional[bool] = None
    photo_ids: Optional[List[str]] = None


class VideoInput(BaseModel):
    format: str = "tour"  # tour | reel
    photo_ids: Optional[List[str]] = None
    clips: Optional[List[dict]] = None  # [{photo_id, motion, duration, style, prompt}]
    music: bool = True
    agency_name: Optional[str] = None


class CheckoutInput(BaseModel):
    lookup_key: str
    origin_url: str


class WatermarkInput(BaseModel):
    enabled: Optional[bool] = None
    position: Optional[str] = None
    opacity: Optional[float] = None
    scale: Optional[float] = None


WATERMARK_DEFAULTS = {"enabled": False, "position": "bottom-right", "opacity": 0.75, "scale": 0.18, "logo_path": None}
EXPORT_PRESETS = {
    "original": None,
    "idealista": (2048, 1536),
    "fotocasa": (2000, 1500),
    "zillow": (2048, 1536),
    "mls": (1024, 768),
}


VIDEO_COSTS = {"tour": 12, "reel": 8}


# ---------- Auth dependency ----------
async def current_user(request: Request):
    token = auth_utils.extract_token(request)
    user = await auth_utils.resolve_user(db, token)
    if not user:
        raise HTTPException(status_code=401, detail="No autenticado")
    user["is_super_admin"] = is_super_admin(user)
    return user


def public_user(user: dict) -> dict:
    owner = is_owner(user)
    return {
        "user_id": user["user_id"],
        "email": user["email"],
        "name": user.get("name", ""),
        "picture": user.get("picture"),
        "role": "owner" if owner else user.get("role", "user"),
        "credits": user.get("credits", 0),
        "unlimited": owner,
        "is_super_admin": is_super_admin(user),
        "plan_name": user.get("plan_name"),
        "plan_expires_at": user.get("plan_expires_at"),
        "watermark": {**WATERMARK_DEFAULTS, **(user.get("watermark") or {})},
    }


# ---------- Auth routes ----------
@api.post("/auth/register")
async def register(data: RegisterInput, response: Response):
    email = data.email.lower().strip()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Este email ya está registrado")
    user_id = f"user_{uuid.uuid4().hex[:12]}"
    user = {
        "user_id": user_id,
        "email": email,
        "name": data.name.strip() or email.split("@")[0],
        "password_hash": auth_utils.hash_password(data.password),
        "role": "user",
        "credits": FREE_CREDITS,
        "auth_provider": "email",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.users.insert_one(user)
    token = auth_utils.create_access_token(user_id, email)
    response.set_cookie("access_token", token, max_age=7 * 24 * 3600, **COOKIE_KW)
    return {"user": public_user(user), "token": token}


@api.post("/auth/login")
async def login(data: LoginInput, response: Response):
    email = data.email.lower().strip()
    user = await db.users.find_one({"email": email})
    if not user or not user.get("password_hash") or not auth_utils.verify_password(data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Email o contraseña incorrectos")
    token = auth_utils.create_access_token(user["user_id"], email)
    response.set_cookie("access_token", token, max_age=7 * 24 * 3600, **COOKIE_KW)
    return {"user": public_user(user), "token": token}


@api.post("/auth/session")
async def google_session(data: SessionInput, response: Response):
    try:
        r = requests.get(
            "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
            headers={"X-Session-ID": data.session_id}, timeout=15,
        )
        r.raise_for_status()
        profile = r.json()
    except Exception:
        raise HTTPException(status_code=401, detail="Sesión de Google inválida")

    email = profile["email"].lower().strip()
    user = await db.users.find_one({"email": email})
    if not user:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        user = {
            "user_id": user_id,
            "email": email,
            "name": profile.get("name", email.split("@")[0]),
            "picture": profile.get("picture"),
            "role": "user",
            "credits": FREE_CREDITS,
            "auth_provider": "google",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.users.insert_one(user)
    else:
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"picture": profile.get("picture")}})

    session_token = profile.get("session_token") or f"sess_{uuid.uuid4().hex}"
    await db.user_sessions.insert_one({
        "user_id": user["user_id"],
        "session_token": session_token,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    response.set_cookie("session_token", session_token, max_age=7 * 24 * 3600, **COOKIE_KW)
    return {"user": public_user(user), "token": session_token}


@api.get("/auth/me")
async def me(user: dict = Depends(current_user)):
    return public_user(user)


@api.post("/auth/logout")
async def logout(request: Request, response: Response):
    token = auth_utils.extract_token(request)
    if token:
        await db.user_sessions.delete_many({"session_token": token})
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("session_token", path="/")
    return {"ok": True}


# ---------- Actions catalogue ----------
@api.get("/actions")
async def list_actions():
    return [
        {
            "key": k,
            "label": v["label"],
            "description": v["description"],
            "cost": v["cost"],
            "category": v["category"],
            "disclosure_default": v["disclosure_default"],
        }
        for k, v in ai_edit.ACTIONS.items()
    ]


# ---------- Properties ----------
async def _property_summary(prop: dict) -> dict:
    photos = await db.photos.find({"property_id": prop["id"], "is_deleted": {"$ne": True}}, {"_id": 0}).to_list(1000)
    cover = None
    for p in photos:
        cover = p.get("current_path") or p.get("original_path")
        break
    return {
        "id": prop["id"],
        "name": prop["name"],
        "address": prop.get("address", ""),
        "photo_count": len(photos),
        "cover_path": cover,
        "created_at": prop.get("created_at"),
    }


@api.get("/properties")
async def list_properties(user: dict = Depends(current_user)):
    props = await db.properties.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return [await _property_summary(p) for p in props]


@api.post("/properties")
async def create_property(data: PropertyInput, user: dict = Depends(current_user)):
    prop = {
        "id": str(uuid.uuid4()),
        "user_id": user["user_id"],
        "name": data.name.strip(),
        "address": data.address.strip() if data.address else "",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.properties.insert_one(prop)
    return await _property_summary(prop)


@api.get("/properties/{property_id}")
async def get_property(property_id: str, user: dict = Depends(current_user)):
    prop = await db.properties.find_one({"id": property_id, "user_id": user["user_id"]}, {"_id": 0})
    if not prop:
        raise HTTPException(status_code=404, detail="Propiedad no encontrada")
    summary = await _property_summary(prop)
    return summary


@api.delete("/properties/{property_id}")
async def delete_property(property_id: str, user: dict = Depends(current_user)):
    prop = await db.properties.find_one({"id": property_id, "user_id": user["user_id"]})
    if not prop:
        raise HTTPException(status_code=404, detail="Propiedad no encontrada")
    await db.photos.update_many({"property_id": property_id}, {"$set": {"is_deleted": True}})
    await db.properties.delete_one({"id": property_id})
    return {"ok": True}


# ---------- Photos ----------
def _photo_public(p: dict) -> dict:
    return {
        "id": p["id"],
        "property_id": p["property_id"],
        "original_path": p["original_path"],
        "current_path": p.get("current_path") or p["original_path"],
        "original_filename": p.get("original_filename"),
        "status": p.get("status", "ready"),
        "disclosure": p.get("disclosure", False),
        "edits": p.get("edits", []),
        "created_at": p.get("created_at"),
    }


@api.post("/properties/{property_id}/photos")
async def upload_photos(property_id: str, files: List[UploadFile] = File(...), user: dict = Depends(current_user)):
    prop = await db.properties.find_one({"id": property_id, "user_id": user["user_id"]})
    if not prop:
        raise HTTPException(status_code=404, detail="Propiedad no encontrada")

    created = []
    for f in files:
        ext = (f.filename.rsplit(".", 1)[-1] if "." in f.filename else "jpg").lower()
        if not imaging.is_supported_input(ext):
            raise HTTPException(status_code=400, detail=f"Formato no soportado: .{ext}. Usa JPG, PNG, WEBP, HEIC o RAW.")
        data = await f.read()
        if len(data) > 60 * 1024 * 1024:
            raise HTTPException(status_code=400, detail=f"{f.filename} supera el límite de 60MB")
        original_filename = f.filename
        if imaging.needs_conversion(ext):
            try:
                data = imaging.convert_to_jpeg(data, ext)
            except Exception as e:
                logger.exception("conversion failed")
                raise HTTPException(status_code=400, detail=f"No se pudo convertir {f.filename}: {e}")
            ext = "jpg"
        content_type = storage.MIME_TYPES.get(ext, "image/jpeg")
        path = f"{storage.APP_NAME}/uploads/{user['user_id']}/{uuid.uuid4()}.{ext}"
        result = storage.put_object(path, data, content_type)
        photo = {
            "id": str(uuid.uuid4()),
            "property_id": property_id,
            "user_id": user["user_id"],
            "original_path": result["path"],
            "current_path": result["path"],
            "content_type": content_type,
            "original_filename": original_filename,
            "status": "ready",
            "disclosure": False,
            "edits": [],
            "is_deleted": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.photos.insert_one(photo)
        created.append(_photo_public(photo))
    return created


@api.get("/properties/{property_id}/photos")
async def list_photos(property_id: str, user: dict = Depends(current_user)):
    prop = await db.properties.find_one({"id": property_id, "user_id": user["user_id"]})
    if not prop:
        raise HTTPException(status_code=404, detail="Propiedad no encontrada")
    photos = await db.photos.find(
        {"property_id": property_id, "is_deleted": {"$ne": True}}, {"_id": 0}
    ).sort("created_at", 1).to_list(1000)
    return [_photo_public(p) for p in photos]


@api.get("/photos/{photo_id}")
async def get_photo(photo_id: str, user: dict = Depends(current_user)):
    p = await db.photos.find_one({"id": photo_id, "user_id": user["user_id"], "is_deleted": {"$ne": True}}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Foto no encontrada")
    return _photo_public(p)


@api.delete("/photos/{photo_id}")
async def delete_photo(photo_id: str, user: dict = Depends(current_user)):
    p = await db.photos.find_one({"id": photo_id, "user_id": user["user_id"]})
    if not p:
        raise HTTPException(status_code=404, detail="Foto no encontrada")
    await db.photos.update_one({"id": photo_id}, {"$set": {"is_deleted": True}})
    return {"ok": True}


@api.post("/photos/{photo_id}/revert")
async def revert_photo(photo_id: str, user: dict = Depends(current_user)):
    p = await db.photos.find_one({"id": photo_id, "user_id": user["user_id"]}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Foto no encontrada")
    await db.photos.update_one(
        {"id": photo_id},
        {"$set": {"current_path": p["original_path"], "edits": [], "disclosure": False, "status": "ready"}},
    )
    p = await db.photos.find_one({"id": photo_id}, {"_id": 0})
    return _photo_public(p)


async def _apply_edit(photo: dict, action_key: str, options: dict, disclosure: Optional[bool]):
    """Runs the AI edit on the photo's current image and persists a new result. Returns updated photo."""
    src_path = photo.get("current_path") or photo["original_path"]
    data, _ = await asyncio.to_thread(storage.get_object, src_path)

    # Essential/free tools are deterministic local operations. Keep them local
    # even if stale provider overrides exist in the database; provider overrides
    # are reserved for AI/generative photo engines.
    override = None if action_key in local_edit.SUPPORTED else await get_tool_override(action_key)
    result_bytes = None
    used_provider = "gemini"
    used_model = ai_edit.MODEL
    gemini_calls = 1
    is_local = False
    if override:
        prov, model_id = override
        prompt = ai_edit.build_prompt(action_key, options)
        try:
            result_bytes = await asyncio.to_thread(ai_providers.run_image_edit, prov, model_id, data, prompt)
            used_provider = prov.get("name") or prov.get("type")
            used_model = model_id
            gemini_calls = 0
        except Exception as e:
            # An explicit provider override must never silently fall back to the
            # Emergent/Gemini engine. A silent fallback can surface an unrelated
            # "credits" error even though the configured provider is the one the
            # administrator selected for this tool.
            logger.exception(
                "provider override failed: provider=%s model=%s",
                prov.get("name") or prov.get("type"),
                model_id,
            )
            raise ProviderEditError(
                provider=prov.get("name") or prov.get("type") or "proveedor",
                model=model_id,
                reason=str(e)[:300],
            ) from e
    if not result_bytes and not override and action_key in local_edit.SUPPORTED:
        # Essential (free) tools run locally — no AI API, no credits, no key balance.
        result_bytes = await asyncio.to_thread(local_edit.run, action_key, data)
        used_provider = "local"
        used_model = "opencv"
        gemini_calls = 0
        is_local = True
    if not result_bytes:
        result_bytes = await ai_edit.run_edit(data, action_key, options, session_id=f"edit_{photo['id']}")
        used_provider = "gemini"
        used_model = ai_edit.MODEL
        gemini_calls = 1
        is_local = False
    if not result_bytes:
        raise RuntimeError("no_image")
    if not is_local:
        result_bytes = await asyncio.to_thread(imaging.finalize_edit, result_bytes, data)
    out_path = f"{storage.APP_NAME}/edits/{photo['user_id']}/{uuid.uuid4()}.jpg"
    stored = await asyncio.to_thread(storage.put_object, out_path, result_bytes, "image/jpeg")
    action = ai_edit.ACTIONS[action_key]
    disc = action["disclosure_default"] if disclosure is None else disclosure
    edit_entry = {"action": action_key, "label": action["label"], "at": datetime.now(timezone.utc).isoformat()}
    await db.photos.update_one(
        {"id": photo["id"]},
        {
            "$set": {"current_path": stored["path"], "status": "ready",
                     "disclosure": bool(photo.get("disclosure", False) or disc)},
            "$push": {"edits": edit_entry},
        },
    )
    await log_usage(photo["user_id"], "photo", action_key, action["cost"], gemini_calls, used_provider, used_model)
    return await db.photos.find_one({"id": photo["id"]}, {"_id": 0})


@api.post("/photos/{photo_id}/edit")
async def edit_photo(photo_id: str, data: EditInput, user: dict = Depends(current_user)):
    if data.action not in ai_edit.ACTIONS:
        raise HTTPException(status_code=400, detail="Acción no válida")
    photo = await db.photos.find_one({"id": photo_id, "user_id": user["user_id"], "is_deleted": {"$ne": True}}, {"_id": 0})
    if not photo:
        raise HTTPException(status_code=404, detail="Foto no encontrada")

    cost = ai_edit.ACTIONS[data.action]["cost"]
    charge = 0 if is_owner(user) else cost
    if charge > 0:
        fresh = await db.users.find_one({"user_id": user["user_id"]})
        if fresh.get("credits", 0) < charge:
            raise HTTPException(status_code=402, detail="Créditos insuficientes")
        await db.users.update_one({"user_id": user["user_id"]}, {"$inc": {"credits": -charge}})
    await db.photos.update_one({"id": photo_id}, {"$set": {"status": "processing"}})
    try:
        updated = await _apply_edit(photo, data.action, data.options, data.disclosure)
    except ProviderEditError as e:
        logger.error(
            "selected provider edit failed: provider=%s model=%s reason=%s",
            e.provider, e.model, e.reason,
        )
        if charge > 0:
            await db.users.update_one({"user_id": user["user_id"]}, {"$inc": {"credits": charge}})
        await db.photos.update_one({"id": photo_id}, {"$set": {"status": "ready"}})
        raise HTTPException(
            status_code=502,
            detail=(
                f"El motor seleccionado ({e.provider} · {e.model}) no pudo editar la imagen. "
                "No se ha usado el motor Gemini ni se han consumido créditos de Emergent. "
                "Revisa que el modelo seleccionado sea compatible con edición de imágenes."
            ),
        )
    except Exception:
        logger.exception("edit failed")
        if charge > 0:
            await db.users.update_one({"user_id": user["user_id"]}, {"$inc": {"credits": charge}})
        await db.photos.update_one({"id": photo_id}, {"$set": {"status": "ready"}})
        raise HTTPException(status_code=500, detail="La edición falló. Tus créditos han sido reembolsados.")

    newbal = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0, "password_hash": 0})
    return {"photo": _photo_public(updated), "credits": newbal.get("credits", 0)}


# ---------- Watermark settings ----------
@api.get("/settings/watermark")
async def get_watermark(user: dict = Depends(current_user)):
    return {**WATERMARK_DEFAULTS, **(user.get("watermark") or {})}


@api.put("/settings/watermark")
async def update_watermark(data: WatermarkInput, user: dict = Depends(current_user)):
    wm = {**WATERMARK_DEFAULTS, **(user.get("watermark") or {})}
    for k, v in data.dict(exclude_none=True).items():
        wm[k] = v
    wm["opacity"] = max(0.1, min(1.0, float(wm["opacity"])))
    wm["scale"] = max(0.05, min(0.5, float(wm["scale"])))
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"watermark": wm}})
    return wm


@api.post("/settings/watermark/logo")
async def upload_watermark_logo(file: UploadFile = File(...), user: dict = Depends(current_user)):
    ext = (file.filename.rsplit(".", 1)[-1] if "." in file.filename else "png").lower()
    if ext not in ("png", "jpg", "jpeg", "webp"):
        raise HTTPException(status_code=400, detail="Usa PNG (con transparencia), JPG o WEBP")
    data = await file.read()
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="El logo supera 8MB")
    path = f"{storage.APP_NAME}/watermarks/{user['user_id']}/logo.png"
    stored = storage.put_object(path, data, "image/png")
    wm = {**WATERMARK_DEFAULTS, **(user.get("watermark") or {}), "logo_path": stored["path"], "enabled": True}
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"watermark": wm}})
    return wm


# ---------- Export with portal presets (+ optional watermark) ----------
@api.get("/photos/{photo_id}/export")
async def export_photo(photo_id: str, request: Request, preset: str = "original",
                       watermark: bool = False, token: str = Query(None)):
    tok = auth_utils.extract_token(request, query_token=token)
    user = await auth_utils.resolve_user(db, tok)
    if not user:
        raise HTTPException(status_code=401, detail="No autenticado")
    photo = await db.photos.find_one({"id": photo_id, "user_id": user["user_id"], "is_deleted": {"$ne": True}}, {"_id": 0})
    if not photo:
        raise HTTPException(status_code=404, detail="Foto no encontrada")
    if preset not in EXPORT_PRESETS:
        raise HTTPException(status_code=400, detail="Preset no válido")
    data, _ = await asyncio.to_thread(storage.get_object, photo.get("current_path") or photo["original_path"])
    wm = {**WATERMARK_DEFAULTS, **(user.get("watermark") or {})}
    if watermark and wm.get("logo_path"):
        try:
            logo, _ = await asyncio.to_thread(storage.get_object, wm["logo_path"])
            data = await asyncio.to_thread(imaging.apply_watermark, data, logo, wm["position"], wm["opacity"], wm["scale"])
        except Exception:
            logger.exception("watermark apply failed")
    data = await asyncio.to_thread(imaging.resize_preset, data, EXPORT_PRESETS[preset])
    base = (photo.get("original_filename") or "editkrimagina").rsplit(".", 1)[0]
    fname = f"{base}_{preset}.jpg"
    return Response(content=data, media_type="image/jpeg",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


# ---------- Download ALL project photos as a ZIP ----------
def _build_zip(items: list) -> bytes:
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in items:
            zf.writestr(name, content)
    return buf.getvalue()


@api.get("/properties/{property_id}/download-all")
async def download_all_photos(property_id: str, request: Request, preset: str = "original",
                              watermark: bool = False, token: str = Query(None)):
    tok = auth_utils.extract_token(request, query_token=token)
    user = await auth_utils.resolve_user(db, tok)
    if not user:
        raise HTTPException(status_code=401, detail="No autenticado")
    prop = await db.properties.find_one({"id": property_id, "user_id": user["user_id"]})
    if not prop:
        raise HTTPException(status_code=404, detail="Propiedad no encontrada")
    if preset not in EXPORT_PRESETS:
        raise HTTPException(status_code=400, detail="Preset no válido")
    photos = await db.photos.find(
        {"property_id": property_id, "user_id": user["user_id"], "is_deleted": {"$ne": True}}, {"_id": 0}
    ).sort("created_at", 1).to_list(1000)
    if not photos:
        raise HTTPException(status_code=400, detail="No hay fotos para descargar")

    wm = {**WATERMARK_DEFAULTS, **(user.get("watermark") or {})}
    logo_bytes = None
    if watermark and wm.get("logo_path"):
        try:
            logo_bytes, _ = await asyncio.to_thread(storage.get_object, wm["logo_path"])
        except Exception:
            logo_bytes = None

    def _process_all():
        items, used = [], set()
        for idx, p in enumerate(photos, 1):
            try:
                raw, _ = storage.get_object(p.get("current_path") or p["original_path"])
                if logo_bytes:
                    raw = imaging.apply_watermark(raw, logo_bytes, wm["position"], wm["opacity"], wm["scale"])
                raw = imaging.resize_preset(raw, EXPORT_PRESETS[preset])
                base = (p.get("original_filename") or f"foto_{idx}").rsplit(".", 1)[0]
                name = f"{base}.jpg"
                n = 1
                while name in used:
                    name = f"{base}_{n}.jpg"
                    n += 1
                used.add(name)
                items.append((name, raw))
            except Exception:
                logger.exception("zip item failed for %s", p.get("id"))
        return _build_zip(items)

    zip_bytes = await asyncio.to_thread(_process_all)
    safe = "".join(c for c in (prop["name"] or "proyecto") if c.isalnum() or c in " -_").strip() or "proyecto"
    return Response(content=zip_bytes, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{safe}.zip"'})


# ---------- Local free object removal (brush inpaint) ----------
@api.post("/photos/{photo_id}/inpaint")
async def inpaint_photo(photo_id: str, request: Request, user: dict = Depends(current_user)):
    photo = await db.photos.find_one({"id": photo_id, "user_id": user["user_id"], "is_deleted": {"$ne": True}}, {"_id": 0})
    if not photo:
        raise HTTPException(status_code=404, detail="Foto no encontrada")
    body = await request.json()
    mask_b64 = (body or {}).get("mask", "")
    if not mask_b64:
        raise HTTPException(status_code=400, detail="Falta la máscara")
    import base64
    try:
        mask_bytes = base64.b64decode(mask_b64.split(",", 1)[-1])
    except Exception:
        raise HTTPException(status_code=400, detail="Máscara no válida")
    src, _ = await asyncio.to_thread(storage.get_object, photo.get("current_path") or photo["original_path"])
    try:
        result = await asyncio.to_thread(local_edit.inpaint, src, mask_bytes)
    except Exception:
        logger.exception("inpaint failed")
        raise HTTPException(status_code=500, detail="No se pudo borrar el objeto")
    out_path = f"{storage.APP_NAME}/edits/{user['user_id']}/{uuid.uuid4()}.jpg"
    stored = await asyncio.to_thread(storage.put_object, out_path, result, "image/jpeg")
    edit_entry = {"action": "spot_remove", "label": "Borrador (local)", "at": datetime.now(timezone.utc).isoformat()}
    await db.photos.update_one({"id": photo_id}, {"$set": {"current_path": stored["path"], "status": "ready"}, "$push": {"edits": edit_entry}})
    await log_usage(user["user_id"], "photo", "spot_remove", 0, 0, "local", "opencv")
    updated = await db.photos.find_one({"id": photo_id}, {"_id": 0})
    return {"photo": _photo_public(updated)}


# ---------- Batch jobs ----------
async def _process_batch(job_id: str, user_id: str, photo_ids: List[str], action_key: str, options: dict, disclosure, unit_cost: int):
    for pid in photo_ids:
        photo = await db.photos.find_one({"id": pid, "user_id": user_id, "is_deleted": {"$ne": True}}, {"_id": 0})
        if not photo:
            await db.jobs.update_one({"id": job_id}, {"$inc": {"failed": 1, "processed": 1}})
            continue
        await db.photos.update_one({"id": pid}, {"$set": {"status": "processing"}})
        try:
            await _apply_edit(photo, action_key, options, disclosure)
            await db.jobs.update_one({"id": job_id}, {"$inc": {"done": 1, "processed": 1}})
        except Exception:
            logger.exception("batch item failed %s", pid)
            if unit_cost > 0:
                await db.users.update_one({"user_id": user_id}, {"$inc": {"credits": unit_cost}})
            await db.photos.update_one({"id": pid}, {"$set": {"status": "ready"}})
            await db.jobs.update_one({"id": job_id}, {"$inc": {"failed": 1, "processed": 1}})
    await db.jobs.update_one({"id": job_id}, {"$set": {"status": "done", "finished_at": datetime.now(timezone.utc).isoformat()}})


@api.post("/properties/{property_id}/batch")
async def batch_edit(property_id: str, data: BatchInput, user: dict = Depends(current_user)):
    if data.action not in ai_edit.ACTIONS:
        raise HTTPException(status_code=400, detail="Acción no válida")
    prop = await db.properties.find_one({"id": property_id, "user_id": user["user_id"]})
    if not prop:
        raise HTTPException(status_code=404, detail="Propiedad no encontrada")

    query = {"property_id": property_id, "user_id": user["user_id"], "is_deleted": {"$ne": True}}
    if data.photo_ids:
        query["id"] = {"$in": data.photo_ids}
    photos = await db.photos.find(query, {"_id": 0}).to_list(1000)
    if not photos:
        raise HTTPException(status_code=400, detail="No hay fotos para procesar")

    unit_cost = 0 if is_owner(user) else ai_edit.ACTIONS[data.action]["cost"]
    total_cost = unit_cost * len(photos)
    if total_cost > 0:
        fresh = await db.users.find_one({"user_id": user["user_id"]})
        if fresh.get("credits", 0) < total_cost:
            raise HTTPException(status_code=402, detail=f"Necesitas {total_cost} créditos para este lote")
        await db.users.update_one({"user_id": user["user_id"]}, {"$inc": {"credits": -total_cost}})

    job = {
        "id": str(uuid.uuid4()),
        "user_id": user["user_id"],
        "property_id": property_id,
        "action": data.action,
        "label": ai_edit.ACTIONS[data.action]["label"],
        "total": len(photos),
        "processed": 0,
        "done": 0,
        "failed": 0,
        "status": "processing",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.jobs.insert_one(job)
    photo_ids = [p["id"] for p in photos]
    asyncio.create_task(_process_batch(job["id"], user["user_id"], photo_ids, data.action, data.options, data.disclosure, unit_cost))
    job.pop("_id", None)
    return {"job_id": job["id"], "total": len(photos), "cost": total_cost}


@api.get("/jobs/{job_id}")
async def get_job(job_id: str, user: dict = Depends(current_user)):
    job = await db.jobs.find_one({"id": job_id, "user_id": user["user_id"]}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado")
    return job


# ---------- Files ----------
@api.get("/files/{path:path}")
async def serve_file(path: str, request: Request, token: str = Query(None)):
    tok = auth_utils.extract_token(request, query_token=token)
    user = await auth_utils.resolve_user(db, tok)
    if not user:
        raise HTTPException(status_code=401, detail="No autenticado")
    record = await db.photos.find_one({"$or": [{"original_path": path}, {"current_path": path}], "user_id": user["user_id"]})
    if record:
        data, content_type = await asyncio.to_thread(storage.get_object, path)
        return Response(content=data, media_type=content_type, headers={"Cache-Control": "private, max-age=3600"})
    vid = await db.videos.find_one({"storage_path": path, "user_id": user["user_id"]})
    if vid:
        data, content_type = await asyncio.to_thread(storage.get_object, path)
        return Response(content=data, media_type="video/mp4", headers={"Cache-Control": "private, max-age=3600"})
    raise HTTPException(status_code=404, detail="Archivo no encontrado")


# ---------- Videos ----------
def _video_public(v: dict) -> dict:
    return {
        "id": v["id"],
        "property_id": v["property_id"],
        "format": v.get("format", "tour"),
        "status": v.get("status", "processing"),
        "storage_path": v.get("storage_path"),
        "photo_count": v.get("photo_count", 0),
        "eta_seconds": v.get("eta_seconds"),
        "created_at": v.get("created_at"),
    }


async def _process_video(video_id, user_id, items, fmt, title, subtitle, music, cost, watermark=None):
    tmpdir = tempfile.mkdtemp()
    try:
        logo_bytes = None
        if watermark and watermark.get("enabled") and watermark.get("logo_path"):
            try:
                logo_bytes, _ = await asyncio.to_thread(storage.get_object, watermark["logo_path"])
            except Exception:
                logo_bytes = None
        local_items = []
        for i, it in enumerate(items):
            data, _ = await asyncio.to_thread(storage.get_object, it["path"])
            if logo_bytes:
                try:
                    data = await asyncio.to_thread(
                        imaging.apply_watermark, data, logo_bytes,
                        watermark.get("position", "bottom-right"),
                        float(watermark.get("opacity", 0.75)),
                        float(watermark.get("scale", 0.18)),
                    )
                except Exception:
                    logger.exception("video watermark failed")
            fp = os.path.join(tmpdir, f"src{i}.jpg")
            with open(fp, "wb") as fh:
                fh.write(data)
            local_items.append({"path": fp, "motion": it.get("motion", "ken_burns"), "secs": it.get("secs")})
        out = os.path.join(tmpdir, "out.mp4")
        await video_gen.generate_video(local_items, out, fmt=fmt, title=title, subtitle=subtitle, music=music)
        with open(out, "rb") as fh:
            vbytes = fh.read()
        path = f"{storage.APP_NAME}/videos/{user_id}/{uuid.uuid4()}.mp4"
        stored = await asyncio.to_thread(storage.put_object, path, vbytes, "video/mp4")
        await db.videos.update_one(
            {"id": video_id},
            {"$set": {"status": "done", "storage_path": stored["path"],
                      "finished_at": datetime.now(timezone.utc).isoformat()}},
        )
        await log_usage(user_id, "video", fmt, VIDEO_COSTS.get(fmt, 0), 0, "ffmpeg", None)
    except Exception:
        logger.exception("video generation failed")
        if cost > 0:
            await db.users.update_one({"user_id": user_id}, {"$inc": {"credits": cost}})
        await db.videos.update_one({"id": video_id}, {"$set": {"status": "failed"}})
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


MOTIONS = {"none", "zoom_in", "zoom_out", "pan_left", "pan_right", "tilt_up", "tilt_down", "ken_burns", "dolly", "ai"}


@api.post("/properties/{property_id}/video")
async def create_video(property_id: str, data: VideoInput, user: dict = Depends(current_user)):
    fmt = data.format if data.format in VIDEO_COSTS else "tour"
    prop = await db.properties.find_one({"id": property_id, "user_id": user["user_id"]})
    if not prop:
        raise HTTPException(status_code=404, detail="Propiedad no encontrada")

    query = {"property_id": property_id, "user_id": user["user_id"], "is_deleted": {"$ne": True}}
    if data.clips:
        query["id"] = {"$in": [c.get("photo_id") for c in data.clips if c.get("photo_id")]}
    elif data.photo_ids:
        query["id"] = {"$in": data.photo_ids}
    photos = await db.photos.find(query, {"_id": 0}).sort("created_at", 1).to_list(1000)
    if not photos:
        raise HTTPException(status_code=400, detail="No hay fotos para el video")
    photo_by_id = {p["id"]: p for p in photos}

    default_secs = 3.5 if fmt == "tour" else 2.5
    items = []
    if data.clips:
        for c in data.clips:
            p = photo_by_id.get(c.get("photo_id"))
            if not p:
                continue
            motion = c.get("motion") if c.get("motion") in MOTIONS else "ken_burns"
            try:
                secs = float(c.get("duration") or default_secs)
            except (TypeError, ValueError):
                secs = default_secs
            secs = min(max(secs, 1.5), 8.0)
            items.append({"path": p.get("current_path") or p["original_path"], "motion": motion, "secs": secs})
    if not items:
        items = [{"path": p.get("current_path") or p["original_path"], "motion": "ken_burns", "secs": default_secs} for p in photos]

    cost = 0 if is_owner(user) else VIDEO_COSTS[fmt]
    if cost > 0:
        fresh = await db.users.find_one({"user_id": user["user_id"]})
        if fresh.get("credits", 0) < cost:
            raise HTTPException(status_code=402, detail=f"Necesitas {cost} créditos para generar este video")
        await db.users.update_one({"user_id": user["user_id"]}, {"$inc": {"credits": -cost}})

    eta_seconds = int(2.2 + sum(it["secs"] for it in items) + 6)
    video_doc = {
        "id": str(uuid.uuid4()),
        "user_id": user["user_id"],
        "property_id": property_id,
        "format": fmt,
        "status": "processing",
        "cost": cost,
        "photo_count": len(items),
        "eta_seconds": eta_seconds,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.videos.insert_one(video_doc)
    subtitle = data.agency_name or prop.get("address") or ""
    watermark = {**WATERMARK_DEFAULTS, **(user.get("watermark") or {})}
    asyncio.create_task(_process_video(video_doc["id"], user["user_id"], items, fmt, prop["name"], subtitle, data.music, cost, watermark))
    return {"video_id": video_doc["id"], "cost": cost, "eta_seconds": eta_seconds}


@api.get("/properties/{property_id}/videos")
async def list_videos(property_id: str, user: dict = Depends(current_user)):
    prop = await db.properties.find_one({"id": property_id, "user_id": user["user_id"]})
    if not prop:
        raise HTTPException(status_code=404, detail="Propiedad no encontrada")
    vids = await db.videos.find({"property_id": property_id, "user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return [_video_public(v) for v in vids]


@api.get("/videos/{video_id}")
async def get_video(video_id: str, user: dict = Depends(current_user)):
    v = await db.videos.find_one({"id": video_id, "user_id": user["user_id"]}, {"_id": 0})
    if not v:
        raise HTTPException(status_code=404, detail="Video no encontrado")
    return _video_public(v)


# ---------- Payments (Stripe credit packages) ----------
@api.get("/payments/packages")
async def payment_packages():
    return [{"lookup_key": k, **v} for k, v in pay.PACKAGES.items()]


@api.post("/payments/checkout")
async def payment_checkout(data: CheckoutInput, user: dict = Depends(current_user)):
    if data.lookup_key not in pay.PACKAGES:
        raise HTTPException(status_code=400, detail="Paquete no válido")
    prices = stripe.Price.list(lookup_keys=[data.lookup_key], active=True, limit=1).data
    if not prices:
        raise HTTPException(status_code=500, detail="Precio no encontrado")
    price = prices[0]
    kwargs = dict(
        line_items=[{"price": price.id, "quantity": 1}],
        mode="payment",
        success_url=f"{data.origin_url}/payment/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{data.origin_url}/payment/cancel",
        metadata={"user_id": user["user_id"], "lookup_key": data.lookup_key},
    )
    try:
        session = stripe.checkout.Session.create(**kwargs, managed_payments={"enabled": True})
    except stripe.error.InvalidRequestError as e:
        msg = (getattr(e, "user_message", "") or "").lower()
        if "managed payments" in msg or "ineligible" in msg:
            session = stripe.checkout.Session.create(**kwargs, automatic_tax={"enabled": True}, billing_address_collection="required")
        else:
            raise
    await db.payment_transactions.insert_one({
        "session_id": session.id,
        "user_id": user["user_id"],
        "lookup_key": data.lookup_key,
        "credits": pay.PACKAGES[data.lookup_key]["credits"],
        "amount": (price.unit_amount or 0),
        "currency": price.currency,
        "status": "initiated",
        "payment_status": "pending",
        "credited": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"checkout_url": session.url, "session_id": session.id}


@api.get("/payments/status/{session_id}")
async def payment_status(session_id: str):
    record = await db.payment_transactions.find_one({"session_id": session_id})
    if not record:
        raise HTTPException(status_code=404, detail="Transacción no encontrada")
    if record.get("payment_status") != "paid":
        try:
            s = stripe.checkout.Session.retrieve(session_id)
            if s.payment_status == "paid" or s.status == "complete":
                await db.payment_transactions.update_one(
                    {"session_id": session_id, "payment_status": {"$ne": "paid"}},
                    {"$set": {"status": "completed", "payment_status": "paid",
                              "stripe_payment_intent_id": s.payment_intent,
                              "updated_at": datetime.now(timezone.utc).isoformat()}},
                )
                await pay.grant_credits(db, session_id)
                record = await db.payment_transactions.find_one({"session_id": session_id})
        except stripe.error.StripeError:
            pass
    return {
        "session_id": record["session_id"],
        "status": record["status"],
        "payment_status": record["payment_status"],
        "credits": record.get("credits"),
    }


@api.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig, pay.STRIPE_WEBHOOK_SECRET)
    except Exception:
        raise HTTPException(status_code=400, detail="Firma inválida")
    obj, t = event["data"]["object"], event["type"]
    if t == "checkout.session.completed":
        await db.payment_transactions.update_one(
            {"session_id": obj["id"], "payment_status": {"$ne": "paid"}},
            {"$set": {"status": "completed", "payment_status": obj.get("payment_status", "paid"),
                      "stripe_payment_intent_id": obj.get("payment_intent"),
                      "updated_at": datetime.now(timezone.utc).isoformat()}},
        )
        await pay.grant_credits(db, obj["id"])
    elif t == "checkout.session.async_payment_succeeded":
        await db.payment_transactions.update_one(
            {"session_id": obj["id"]},
            {"$set": {"payment_status": "paid", "updated_at": datetime.now(timezone.utc).isoformat()}},
        )
        await pay.grant_credits(db, obj["id"])
    elif t in ("checkout.session.async_payment_failed", "checkout.session.expired"):
        await db.payment_transactions.update_one(
            {"session_id": obj["id"]},
            {"$set": {"status": "failed", "payment_status": "failed", "updated_at": datetime.now(timezone.utc).isoformat()}},
        )
    return {"status": "ok"}


@api.get("/")
async def root():
    return {"message": "Watchful API", "status": "ok"}


register_admin_routes(api, db, current_user, ai_edit.ACTIONS)

app.include_router(api)

_cors = os.environ.get("CORS_ORIGINS", "*").strip()
if _cors == "*":
    # Reflect any origin so preview, production and custom domains all work with cookie credentials.
    app.add_middleware(
        CORSMiddleware,
        allow_credentials=True,
        allow_origin_regex=".*",
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_credentials=True,
        allow_origins=[o.strip() for o in _cors.split(",") if o.strip()],
        allow_methods=["*"],
        allow_headers=["*"],
    )


async def _video_sweeper():
    """Safety net: mark videos stuck in 'processing' > 8 min as failed and refund credits."""
    while True:
        try:
            await asyncio.sleep(120)
            cutoff = (datetime.now(timezone.utc) - timedelta(minutes=8)).isoformat()
            stuck = await db.videos.find(
                {"status": "processing", "created_at": {"$lt": cutoff}}, {"_id": 0}
            ).to_list(100)
            for v in stuck:
                r = await db.videos.update_one(
                    {"id": v["id"], "status": "processing"}, {"$set": {"status": "failed"}}
                )
                if r.modified_count and v.get("cost"):
                    await db.users.update_one({"user_id": v["user_id"]}, {"$inc": {"credits": v["cost"]}})
                    logger.info("swept stuck video %s, refunded %s", v["id"], v["cost"])
        except Exception:
            logger.exception("video sweeper error")


@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.users.create_index("user_id")
    await db.user_sessions.create_index("session_token")
    await db.properties.create_index("user_id")
    await db.photos.create_index("property_id")
    try:
        storage.init_storage()
        logger.info("Object storage initialized")
    except Exception as e:
        logger.error("Storage init failed: %s", e)

    # Recover orphaned work from a previous pod: async tasks die on restart/redeploy.
    orphaned_videos = await db.videos.find({"status": "processing"}, {"_id": 0}).to_list(1000)
    for v in orphaned_videos:
        await db.videos.update_one({"id": v["id"], "status": "processing"}, {"$set": {"status": "failed"}})
        if v.get("cost"):
            await db.users.update_one({"user_id": v["user_id"]}, {"$inc": {"credits": v["cost"]}})
    if orphaned_videos:
        logger.info("Recovered %s orphaned videos", len(orphaned_videos))
    await db.photos.update_many({"status": "processing"}, {"$set": {"status": "ready"}})
    await db.jobs.update_many({"status": "processing"}, {"$set": {"status": "done"}})

    asyncio.create_task(_video_sweeper())

    admin_email = os.environ.get("ADMIN_EMAIL", "admin@watchful.app").lower()
    admin_password = os.environ.get("ADMIN_PASSWORD", "Watchful2026!")
    existing = await db.users.find_one({"email": admin_email})
    if not existing:
        await db.users.insert_one({
            "user_id": f"user_{uuid.uuid4().hex[:12]}",
            "email": admin_email,
            "name": "Admin Watchful",
            "password_hash": auth_utils.hash_password(admin_password),
            "role": "admin",
            "credits": 500,
            "auth_provider": "email",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    elif not auth_utils.verify_password(admin_password, existing.get("password_hash", "")):
        await db.users.update_one({"email": admin_email}, {"$set": {"password_hash": auth_utils.hash_password(admin_password)}})

    # Promote the app owner(s) (unlimited, non-consuming credits) if the account already exists.
    if OWNER_EMAILS:
        await db.users.update_many(
            {"email": {"$in": list(OWNER_EMAILS)}},
            {"$set": {"role": "owner", "credits": 999999}},
        )


@app.on_event("shutdown")
async def shutdown():
    client.close()
