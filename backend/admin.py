"""Admin panel routes for Watchful (super-admin only).

Sections:
  1. Users & plans   — user list, plan CRUD, manual plan assignment.
  2. Usage           — per-user consumption (photo/video credits + real Gemini calls).
  3. AI providers    — add external AI sources, discover models, per-tool engine override.

Also exposes a PUBLIC GET /plans endpoint so the landing page renders active plans.
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import HTTPException, Depends, Request
from pydantic import BaseModel

import providers as ai_providers

logger = logging.getLogger("watchful.admin")


class PlanInput(BaseModel):
    name: str
    price_eur: float = 0
    credits: int = 0
    period: str = "monthly"  # monthly | yearly | one_time
    features: List[str] = []
    highlight: bool = False
    active: bool = True
    sort_order: int = 0


class AssignPlanInput(BaseModel):
    plan_id: Optional[str] = None
    expires_at: Optional[str] = None  # ISO date string or null


class ProviderInput(BaseModel):
    name: str
    type: str = "openai_compatible"  # openai_compatible | fal | custom
    base_url: Optional[str] = ""
    api_key: str


class ModelToggleInput(BaseModel):
    model_id: str
    photo: Optional[bool] = None
    video: Optional[bool] = None


class ToolOverrideInput(BaseModel):
    action: str
    provider_id: Optional[str] = None  # null -> back to default engine
    model_id: Optional[str] = None


def _plan_public(p: dict) -> dict:
    return {
        "id": p["id"], "name": p["name"], "price_eur": p.get("price_eur", 0),
        "credits": p.get("credits", 0), "period": p.get("period", "monthly"),
        "features": p.get("features", []), "highlight": p.get("highlight", False),
        "active": p.get("active", True), "sort_order": p.get("sort_order", 0),
    }


def _provider_public(p: dict) -> dict:
    key = p.get("api_key") or ""
    return {
        "id": p["id"], "name": p["name"], "type": p.get("type"),
        "base_url": p.get("base_url", ""), "status": p.get("status", "unknown"),
        "key_hint": ("••••" + key[-4:]) if len(key) >= 4 else "••••",
        "models": p.get("models", []), "enabled": p.get("enabled", {}),
        "last_checked": p.get("last_checked"),
        "error": p.get("error"),
    }


def register_admin_routes(api, db, current_user, action_catalog):
    """action_catalog: dict of {action_key: {label, cost, category}} from ai_edit.ACTIONS."""

    async def require_admin(user: dict = Depends(current_user)):
        if not user.get("is_super_admin"):
            raise HTTPException(status_code=403, detail="Acceso solo para administrador")
        return user

    # ---------- Public: active plans for landing ----------
    @api.get("/plans")
    async def public_plans():
        plans = await db.plans.find({"active": True}, {"_id": 0}).sort("sort_order", 1).to_list(100)
        return [_plan_public(p) for p in plans]

    # ---------- Users ----------
    @api.get("/admin/users")
    async def admin_users(_: dict = Depends(require_admin)):
        users = await db.users.find({}, {"_id": 0, "password_hash": 0}).sort("created_at", -1).to_list(2000)
        out = []
        for u in users:
            out.append({
                "user_id": u["user_id"], "email": u["email"], "name": u.get("name", ""),
                "role": u.get("role", "user"), "credits": u.get("credits", 0),
                "auth_provider": u.get("auth_provider", "email"),
                "plan_id": u.get("plan_id"), "plan_name": u.get("plan_name"),
                "plan_expires_at": u.get("plan_expires_at"),
                "created_at": u.get("created_at"),
            })
        return out

    @api.post("/admin/users/{user_id}/plan")
    async def admin_assign_plan(user_id: str, data: AssignPlanInput, _: dict = Depends(require_admin)):
        u = await db.users.find_one({"user_id": user_id})
        if not u:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        if data.plan_id:
            plan = await db.plans.find_one({"id": data.plan_id}, {"_id": 0})
            if not plan:
                raise HTTPException(status_code=404, detail="Plan no encontrado")
            update = {"plan_id": plan["id"], "plan_name": plan["name"], "plan_expires_at": data.expires_at}
            # Grant the plan's included credits only when the plan actually changes
            # (re-saving to update the expiry date must not stack credits).
            if plan.get("credits") and u.get("plan_id") != plan["id"]:
                await db.users.update_one({"user_id": user_id}, {"$inc": {"credits": plan["credits"]}})
        else:
            update = {"plan_id": None, "plan_name": None, "plan_expires_at": None}
        await db.users.update_one({"user_id": user_id}, {"$set": update})
        return {"ok": True}

    # ---------- Plans CRUD ----------
    @api.get("/admin/plans")
    async def admin_list_plans(_: dict = Depends(require_admin)):
        plans = await db.plans.find({}, {"_id": 0}).sort("sort_order", 1).to_list(100)
        return [_plan_public(p) for p in plans]

    @api.post("/admin/plans")
    async def admin_create_plan(data: PlanInput, _: dict = Depends(require_admin)):
        plan = {"id": str(uuid.uuid4()), **data.dict(),
                "created_at": datetime.now(timezone.utc).isoformat()}
        await db.plans.insert_one(plan)
        return _plan_public(plan)

    @api.put("/admin/plans/{plan_id}")
    async def admin_update_plan(plan_id: str, data: PlanInput, _: dict = Depends(require_admin)):
        r = await db.plans.update_one({"id": plan_id}, {"$set": data.dict()})
        if not r.matched_count:
            raise HTTPException(status_code=404, detail="Plan no encontrado")
        plan = await db.plans.find_one({"id": plan_id}, {"_id": 0})
        return _plan_public(plan)

    @api.delete("/admin/plans/{plan_id}")
    async def admin_delete_plan(plan_id: str, _: dict = Depends(require_admin)):
        await db.plans.delete_one({"id": plan_id})
        return {"ok": True}

    # ---------- Usage / consumption ----------
    @api.get("/admin/usage")
    async def admin_usage(admin: dict = Depends(require_admin)):
        pipeline = [
            {"$group": {
                "_id": "$user_id",
                "photo_credits": {"$sum": {"$cond": [{"$eq": ["$kind", "photo"]}, "$credits", 0]}},
                "video_credits": {"$sum": {"$cond": [{"$eq": ["$kind", "video"]}, "$credits", 0]}},
                "gemini_calls": {"$sum": "$gemini_calls"},
                "ai_calls": {"$sum": "$ai_calls"},
                "events": {"$sum": 1},
            }},
        ]
        rows = await db.usage_events.aggregate(pipeline).to_list(5000)
        by_user = {r["_id"]: r for r in rows}
        users = await db.users.find({}, {"_id": 0, "user_id": 1, "email": 1, "name": 1, "role": 1}).to_list(5000)
        umap = {u["user_id"]: u for u in users}

        def build(uid):
            r = by_user.get(uid, {})
            u = umap.get(uid, {})
            pc = r.get("photo_credits", 0)
            vc = r.get("video_credits", 0)
            return {
                "user_id": uid, "email": u.get("email", uid), "name": u.get("name", ""),
                "role": u.get("role", "user"),
                "photo_credits": pc, "video_credits": vc, "total_credits": pc + vc,
                "gemini_calls": r.get("gemini_calls", 0), "ai_calls": r.get("ai_calls", 0),
                "events": r.get("events", 0),
            }

        admin_row = build(admin["user_id"])
        others = [build(uid) for uid in by_user if uid != admin["user_id"]]
        # Include users with events; sort by total credits desc.
        others.sort(key=lambda x: x["total_credits"], reverse=True)
        totals = {
            "photo_credits": sum(o["photo_credits"] for o in others),
            "video_credits": sum(o["video_credits"] for o in others),
            "gemini_calls": sum(o["gemini_calls"] for o in others),
            "ai_calls": sum(o["ai_calls"] for o in others),
        }
        totals["total_credits"] = totals["photo_credits"] + totals["video_credits"]
        return {"admin": admin_row, "users": others, "totals": totals}

    # ---------- AI providers ----------
    @api.get("/admin/providers")
    async def admin_list_providers(_: dict = Depends(require_admin)):
        provs = await db.ai_providers.find({}, {"_id": 0}).sort("created_at", 1).to_list(100)
        return [_provider_public(p) for p in provs]

    @api.post("/admin/providers")
    async def admin_add_provider(data: ProviderInput, _: dict = Depends(require_admin)):
        import asyncio
        detected = await asyncio.to_thread(ai_providers.detect, data.type, data.base_url or "", data.api_key)
        prov = {
            "id": str(uuid.uuid4()), "name": data.name.strip(), "type": data.type,
            "base_url": (data.base_url or "").strip(), "api_key": data.api_key.strip(),
            "status": detected["status"], "models": detected["models"], "enabled": {},
            "error": detected.get("error"),
            "last_checked": datetime.now(timezone.utc).isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.ai_providers.insert_one(prov)
        return _provider_public(prov)

    @api.post("/admin/providers/{provider_id}/refresh")
    async def admin_refresh_provider(provider_id: str, _: dict = Depends(require_admin)):
        import asyncio
        p = await db.ai_providers.find_one({"id": provider_id})
        if not p:
            raise HTTPException(status_code=404, detail="Proveedor no encontrado")
        detected = await asyncio.to_thread(ai_providers.detect, p["type"], p.get("base_url", ""), p.get("api_key", ""))
        await db.ai_providers.update_one({"id": provider_id}, {"$set": {
            "status": detected["status"], "models": detected["models"],
            "error": detected.get("error"),
            "last_checked": datetime.now(timezone.utc).isoformat(),
        }})
        p = await db.ai_providers.find_one({"id": provider_id}, {"_id": 0})
        return _provider_public(p)

    @api.put("/admin/providers/{provider_id}/models")
    async def admin_toggle_model(provider_id: str, data: ModelToggleInput, _: dict = Depends(require_admin)):
        p = await db.ai_providers.find_one({"id": provider_id})
        if not p:
            raise HTTPException(status_code=404, detail="Proveedor no encontrado")
        enabled = p.get("enabled", {})
        cur = enabled.get(data.model_id, {"photo": False, "video": False})
        if data.photo is not None:
            cur["photo"] = data.photo
        if data.video is not None:
            cur["video"] = data.video
        enabled[data.model_id] = cur
        await db.ai_providers.update_one({"id": provider_id}, {"$set": {"enabled": enabled}})
        p = await db.ai_providers.find_one({"id": provider_id}, {"_id": 0})
        return _provider_public(p)

    @api.delete("/admin/providers/{provider_id}")
    async def admin_delete_provider(provider_id: str, _: dict = Depends(require_admin)):
        await db.ai_providers.delete_one({"id": provider_id})
        # Drop any tool overrides pointing to this provider.
        settings = await db.ai_settings.find_one({"id": "tool_overrides"}) or {}
        overrides = settings.get("overrides", {})
        overrides = {k: v for k, v in overrides.items() if v.get("provider_id") != provider_id}
        await db.ai_settings.update_one({"id": "tool_overrides"}, {"$set": {"overrides": overrides}}, upsert=True)
        return {"ok": True}

    # ---------- Tool -> engine overrides ----------
    @api.get("/admin/tool-overrides")
    async def admin_get_overrides(_: dict = Depends(require_admin)):
        settings = await db.ai_settings.find_one({"id": "tool_overrides"}, {"_id": 0}) or {}
        overrides = settings.get("overrides", {})
        provs = await db.ai_providers.find({}, {"_id": 0}).to_list(100)
        # Photo-capable options: models toggled for photo, per provider.
        photo_models = []
        for p in provs:
            enabled = p.get("enabled", {})
            for m in p.get("models", []):
                if enabled.get(m["id"], {}).get("photo"):
                    photo_models.append({
                        "provider_id": p["id"], "provider_name": p["name"],
                        "model_id": m["id"], "model_name": m.get("name", m["id"]),
                        "status": p.get("status"),
                    })
        tools = [
            {"action": k, "label": v["label"], "category": v["category"], "cost": v["cost"]}
            for k, v in action_catalog.items()
        ]
        return {"tools": tools, "overrides": overrides, "photo_models": photo_models}

    @api.put("/admin/tool-overrides")
    async def admin_set_override(data: ToolOverrideInput, _: dict = Depends(require_admin)):
        if data.action not in action_catalog:
            raise HTTPException(status_code=400, detail="Herramienta no válida")
        settings = await db.ai_settings.find_one({"id": "tool_overrides"}) or {"overrides": {}}
        overrides = settings.get("overrides", {})
        if data.provider_id and data.model_id:
            overrides[data.action] = {"provider_id": data.provider_id, "model_id": data.model_id}
        else:
            overrides.pop(data.action, None)
        await db.ai_settings.update_one({"id": "tool_overrides"}, {"$set": {"overrides": overrides}}, upsert=True)
        return {"ok": True, "overrides": overrides}

    @api.post("/admin/reset-engines")
    async def admin_reset_engines(delete_providers: bool = False, _: dict = Depends(require_admin)):
        """Restore every photo tool to the default Gemini Nano Banana engine.

        Clears all per-tool overrides. Optionally removes configured providers too.
        Use this to make an environment behave exactly like the default (no custom engines).
        """
        await db.ai_settings.update_one({"id": "tool_overrides"}, {"$set": {"overrides": {}}}, upsert=True)
        removed = 0
        if delete_providers:
            res = await db.ai_providers.delete_many({})
            removed = res.deleted_count
        return {"ok": True, "providers_removed": removed}
