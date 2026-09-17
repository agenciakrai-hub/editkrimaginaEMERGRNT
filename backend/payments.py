"""Stripe credit-package payment helpers (Flow A sandbox)."""
import os
import logging
from datetime import datetime, timezone

import stripe

logger = logging.getLogger("watchful.payments")

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or "sk_test_emergent"
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

# lookup_key -> credits granted + display metadata
PACKAGES = {
    "credits_100": {"credits": 100, "label": "100 créditos", "eur": "9,99 €", "popular": False},
    "credits_300": {"credits": 300, "label": "300 créditos", "eur": "24,99 €", "popular": True},
    "credits_1000": {"credits": 1000, "label": "1.000 créditos", "eur": "69,99 €", "popular": False},
}


async def grant_credits(db, session_id: str):
    """Idempotently grant package credits once a transaction is paid."""
    txn = await db.payment_transactions.find_one({"session_id": session_id})
    if not txn or txn.get("payment_status") != "paid" or txn.get("credited"):
        return
    res = await db.payment_transactions.update_one(
        {"session_id": session_id, "credited": {"$ne": True}},
        {"$set": {"credited": True, "credited_at": datetime.now(timezone.utc).isoformat()}},
    )
    credits = txn.get("credits", 0)
    if res.modified_count == 1 and txn.get("user_id") and credits:
        await db.users.update_one({"user_id": txn["user_id"]}, {"$inc": {"credits": credits}})
        logger.info("granted %s credits to %s", credits, txn["user_id"])
