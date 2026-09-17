"""Idempotent Stripe catalogue setup for Watchful credit packages (Flow A sandbox)."""
import os
import stripe
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent / ".env")
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or "sk_test_emergent"

# Credit packages (one-time, digital). Amounts in cents, EUR (Spain sandbox).
CATALOG = [
    {
        "emergent_product_id": "watchful_credits",
        "name": "Watchful — Paquete de créditos",
        "tax_code": "txcd_10000000",  # general digital goods
        "prices": [
            {"lookup_key": "credits_100", "amount": 999, "currency": "eur"},
            {"lookup_key": "credits_300", "amount": 2499, "currency": "eur"},
            {"lookup_key": "credits_1000", "amount": 6999, "currency": "eur"},
        ],
    },
]


def get_or_create_product(entry):
    for p in stripe.Product.list(active=True, limit=100).auto_paging_iter():
        if p.to_dict().get("metadata", {}).get("emergent_product_id") == entry["emergent_product_id"]:
            return p
    return stripe.Product.create(
        name=entry["name"],
        tax_code=entry.get("tax_code"),
        metadata={"managed_by": "emergent", "emergent_product_id": entry["emergent_product_id"]},
    )


def run():
    for entry in CATALOG:
        product = get_or_create_product(entry)
        for p in entry["prices"]:
            existing = stripe.Price.list(lookup_keys=[p["lookup_key"]], active=True, limit=1).data
            if existing and (existing[0].unit_amount != p["amount"] or existing[0].currency != p["currency"]):
                stripe.Price.modify(existing[0].id, active=False)
                existing = []
            if not existing:
                stripe.Price.create(
                    product=product.id,
                    unit_amount=p["amount"],
                    currency=p["currency"],
                    lookup_key=p["lookup_key"],
                    transfer_lookup_key=True,
                )
                print("created price", p["lookup_key"])
            else:
                print("exists", p["lookup_key"])


if __name__ == "__main__":
    run()
