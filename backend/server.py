from dotenv import load_dotenv
from pathlib import Path
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

import os
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

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("watchful")

app = FastAPI(title="Watchful API")
api = APIRouter(prefix="/api")

FREE_CREDITS = 30
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


# ---------- Auth dependency ----------
async def current_user(request: Request):
    token = auth_utils.extract_token(request)
    user = await auth_utils.resolve_user(db, token)
    if not user:
        raise HTTPException(status_code=401, detail="No autenticado")
    return user


def public_user(user: dict) -> dict:
    return {
        "user_id": user["user_id"],
        "email": user["email"],
        "name": user.get("name", ""),
        "picture": user.get("picture"),
        "role": user.get("role", "user"),
        "credits": user.get("credits", 0),
        "auth_provider": user.get("auth_provider", "email"),
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
        if ext not in storage.MIME_TYPES:
            raise HTTPException(status_code=400, detail=f"Formato no soportado: .{ext}. Usa JPG, PNG o WEBP.")
        data = await f.read()
        if len(data) > 25 * 1024 * 1024:
            raise HTTPException(status_code=400, detail=f"{f.filename} supera el límite de 25MB")
        path = f"{storage.APP_NAME}/uploads/{user['user_id']}/{uuid.uuid4()}.{ext}"
        content_type = storage.MIME_TYPES[ext]
        result = storage.put_object(path, data, content_type)
        photo = {
            "id": str(uuid.uuid4()),
            "property_id": property_id,
            "user_id": user["user_id"],
            "original_path": result["path"],
            "current_path": result["path"],
            "content_type": content_type,
            "original_filename": f.filename,
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
    data, _ = storage.get_object(src_path)
    result_bytes = await ai_edit.run_edit(data, action_key, options, session_id=f"edit_{photo['id']}")
    if not result_bytes:
        raise RuntimeError("no_image")
    out_path = f"{storage.APP_NAME}/edits/{photo['user_id']}/{uuid.uuid4()}.png"
    stored = storage.put_object(out_path, result_bytes, "image/png")
    action = ai_edit.ACTIONS[action_key]
    disc = action["disclosure_default"] if disclosure is None else disclosure
    new_disclosure = photo.get("disclosure", False) or (disc and action["disclosure_default"] is not None and disc)
    edit_entry = {"action": action_key, "label": action["label"], "at": datetime.now(timezone.utc).isoformat()}
    await db.photos.update_one(
        {"id": photo["id"]},
        {
            "$set": {"current_path": stored["path"], "status": "ready",
                     "disclosure": bool(photo.get("disclosure", False) or disc)},
            "$push": {"edits": edit_entry},
        },
    )
    return await db.photos.find_one({"id": photo["id"]}, {"_id": 0})


@api.post("/photos/{photo_id}/edit")
async def edit_photo(photo_id: str, data: EditInput, user: dict = Depends(current_user)):
    if data.action not in ai_edit.ACTIONS:
        raise HTTPException(status_code=400, detail="Acción no válida")
    photo = await db.photos.find_one({"id": photo_id, "user_id": user["user_id"], "is_deleted": {"$ne": True}}, {"_id": 0})
    if not photo:
        raise HTTPException(status_code=404, detail="Foto no encontrada")

    cost = ai_edit.ACTIONS[data.action]["cost"]
    fresh = await db.users.find_one({"user_id": user["user_id"]})
    if cost > 0 and fresh.get("credits", 0) < cost:
        raise HTTPException(status_code=402, detail="Créditos insuficientes")

    if cost > 0:
        await db.users.update_one({"user_id": user["user_id"]}, {"$inc": {"credits": -cost}})
    await db.photos.update_one({"id": photo_id}, {"$set": {"status": "processing"}})
    try:
        updated = await _apply_edit(photo, data.action, data.options, data.disclosure)
    except Exception as e:
        logger.exception("edit failed")
        if cost > 0:
            await db.users.update_one({"user_id": user["user_id"]}, {"$inc": {"credits": cost}})
        await db.photos.update_one({"id": photo_id}, {"$set": {"status": "ready"}})
        raise HTTPException(status_code=500, detail="La edición falló. Tus créditos han sido reembolsados.")

    newbal = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0, "password_hash": 0})
    return {"photo": _photo_public(updated), "credits": newbal.get("credits", 0)}


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

    unit_cost = ai_edit.ACTIONS[data.action]["cost"]
    total_cost = unit_cost * len(photos)
    fresh = await db.users.find_one({"user_id": user["user_id"]})
    if total_cost > 0 and fresh.get("credits", 0) < total_cost:
        raise HTTPException(status_code=402, detail=f"Necesitas {total_cost} créditos para este lote")
    if total_cost > 0:
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
    if not record:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    data, content_type = storage.get_object(path)
    return Response(content=data, media_type=content_type, headers={"Cache-Control": "private, max-age=3600"})


@api.get("/")
async def root():
    return {"message": "Watchful API", "status": "ok"}


app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=[os.environ.get("FRONTEND_URL", "http://localhost:3000")],
    allow_methods=["*"],
    allow_headers=["*"],
)


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


@app.on_event("shutdown")
async def shutdown():
    client.close()
