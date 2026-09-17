import os
import bcrypt
import jwt
from datetime import datetime, timezone, timedelta
from fastapi import Request, HTTPException

JWT_ALGORITHM = "HS256"
ACCESS_TTL_DAYS = 7


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def _secret() -> str:
    return os.environ["JWT_SECRET"]


def create_access_token(user_id: str, email: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(days=ACCESS_TTL_DAYS),
    }
    return jwt.encode(payload, _secret(), algorithm=JWT_ALGORITHM)


def decode_token(token: str):
    try:
        payload = jwt.decode(token, _secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            return None
        return payload
    except jwt.InvalidTokenError:
        return None


def extract_token(request: Request, query_token: str = None) -> str:
    # Prefer an explicit Authorization header (avoids account confusion when a
    # stale cookie is also present), then cookies, then query param (for <img>).
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    token = request.cookies.get("access_token") or request.cookies.get("session_token")
    if not token and query_token:
        token = query_token
    return token


async def resolve_user(db, token: str):
    if not token:
        return None
    payload = decode_token(token)
    if payload:
        return await db.users.find_one({"user_id": payload["sub"]}, {"_id": 0, "password_hash": 0})
    session = await db.user_sessions.find_one({"session_token": token})
    if session:
        expires_at = session.get("expires_at")
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at and expires_at < datetime.now(timezone.utc):
            return None
        return await db.users.find_one({"user_id": session["user_id"]}, {"_id": 0, "password_hash": 0})
    return None
