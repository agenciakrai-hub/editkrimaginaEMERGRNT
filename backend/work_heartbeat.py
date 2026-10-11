"""Keep live edits safe when another API worker starts."""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
STALE_AFTER = timedelta(minutes=20)
def stale_work_filter(now=None):
    cutoff = ((now or datetime.now(timezone.utc)) - STALE_AFTER).isoformat()
    return {"$or": [{"heartbeat_at": {"$lt": cutoff}}, {"heartbeat_at": {"$exists": False}, "created_at": {"$lt": cutoff}}]}
async def run_with_heartbeat(db, job_id, operation, *args, interval=30):
    async def beat():
        while True:
            try:
                await db.jobs.update_one({"id": job_id, "status": {"$in": ["starting", "processing"]}}, {"$set": {"heartbeat_at": datetime.now(timezone.utc).isoformat()}})
            except Exception:
                logging.exception("Could not renew edit heartbeat %s", job_id)
            await asyncio.sleep(interval)
    task = asyncio.create_task(beat())
    try:
        return await operation(*args)
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

def batch_public(job):
    if not job:
        return job
    job = dict(job)
    if job.get("total", 0) > 0 and job.get("processed", 0) >= job["total"] and job.get("status") == "interrupted":
        job["status"] = "done"
    if job.get("status") == "done" and str(job.get("error_message") or "").startswith("El lote se interrumpió"):
        failed = job.get("failed", 0)
        job["error_message"] = f"Lote terminado: {failed} fotos no pudieron editarse. Sus originales se conservan." if failed else None
    return job
