"""Photo reservations and idempotent settlement; never remove photo files."""
from datetime import datetime, timezone
from work_heartbeat import stale_work_filter

ACTIVE = ["starting", "processing"]

async def settle_batch_photo(db, job, photo_id, refund=False):
    cost = job.get("unit_cost", 0)
    marker = f"{job['id']}:{photo_id}"
    if cost:
        change = {"$pull": {"batch_edit_charges": marker}}
        if refund:
            change["$inc"] = {"credits": cost}
        await db.users.update_one({"user_id": job["user_id"], "batch_edit_charges": marker}, change)

async def release_batch(db, job, refund_pending=True):
    for pid in job.get("photo_ids", []):
        photo = await db.photos.find_one({"id": pid, "user_id": job["user_id"]}, {"_id": 0})
        saved = bool(photo and any(e.get("job_id") == job["id"] for e in photo.get("edits", [])))
        await settle_batch_photo(db, job, pid, refund=refund_pending and not saved)
    await db.photos.update_many({"user_id": job["user_id"], "edit_job_id": job["id"],
                                "status": {"$in": ["queued", "processing"]}},
                               {"$set": {"status": "ready", "edit_job_id": None}})

async def recover_stale_batches(db, owner=None):
    query = {"kind": {"$ne": "photo_edit"}, "status": {"$in": ACTIVE}, **stale_work_filter()}
    if owner:
        query.update(owner)
    jobs = await db.jobs.find(query, {"_id": 0}).to_list(None)
    count = 0
    for job in jobs:
        changed = await db.jobs.update_one({**query, "id": job["id"]}, {"$set": {
            "status": "interrupted", "finished_at": datetime.now(timezone.utc).isoformat(),
            "error_message": "El proceso se interrumpió. Las ediciones guardadas se conservan y las fotos pendientes quedan libres."}})
        if changed.modified_count:
            await release_batch(db, job)
            count += 1
    return count

async def clear_failed_jobs(db, owner):
    """Soft archive terminal errors. A fresh heartbeat always protects live work."""
    await recover_stale_batches(db, owner)
    query = {**owner, "errors_cleared_at": {"$exists": False}, "$or": [
        {"status": {"$in": ["failed", "interrupted"]}},
        {"status": "done", "failed": {"$gt": 0}}]}
    jobs = await db.jobs.find(query, {"_id": 0}).to_list(None)
    cleared = 0
    for job in jobs:
        changed = await db.jobs.update_one({**query, "id": job["id"]},
            {"$set": {"errors_cleared_at": datetime.now(timezone.utc).isoformat()}})
        if not changed.modified_count:
            continue
        # Match the old reservation only: never unlock a newer edit of the same photo.
        await db.photos.update_many({"user_id": owner["user_id"], "edit_job_id": job["id"],
                                    "status": {"$in": ["queued", "processing"]}},
                                   {"$set": {"status": "ready", "edit_job_id": None}})
        cleared += 1
    return cleared
