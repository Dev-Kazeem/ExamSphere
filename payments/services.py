import logging
import re
import uuid
from decimal import Decimal, InvalidOperation

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import SemesterSubscription

logger = logging.getLogger(__name__)

API = "https://api.flutterwave.com/v3"
REF_PREFIX = re.compile(r"^sub(\d+)-")


def auth_headers():
    return {"Authorization": f"Bearer {settings.FLUTTERWAVE_SECRET_KEY}"}


def new_tx_ref(sub):
    """A fresh single-use reference that still says which subscription it belongs to."""
    return f"sub{sub.pk}-{uuid.uuid4().hex[:16]}"


def subscription_for_ref(tx_ref):
    tx_ref = str(tx_ref or "")
    qs = SemesterSubscription.objects.select_related("semester")
    sub = qs.filter(tx_ref=tx_ref).first()        # current (or legacy) reference
    if sub is None:
        match = REF_PREFIX.match(tx_ref)          # an older reference we've since replaced
        if match:
            sub = qs.filter(pk=match.group(1)).first()
    return sub


def fetch_transaction(*, transaction_id=None, tx_ref=None):
    """Ask Flutterwave directly. Never trust amounts or statuses from the URL."""
    if transaction_id:
        url, params = f"{API}/transactions/{transaction_id}/verify", None
    else:
        url, params = f"{API}/transactions/verify_by_reference", {"tx_ref": tx_ref}
    try:
        resp = requests.get(url, params=params, headers=auth_headers(), timeout=15)
        body = resp.json()
    except (requests.RequestException, ValueError):
        logger.exception("Could not reach Flutterwave to verify a payment")
        return None
    if body.get("status") != "success":
        # Usually a wrong/missing secret key, or test/live keys mixed up.
        logger.warning("Flutterwave verify returned %s: %s", resp.status_code, body.get("message"))
        return None
    return body.get("data") or None


def activate_if_paid(sub, data):
    """Mark the subscription PAID only if Flutterwave's record genuinely matches it."""
    if not data or sub is None:
        return False
    try:
        paid = Decimal(str(data.get("amount")))   # Decimal, never string, comparison
    except (InvalidOperation, TypeError):
        return False

    ref = str(data.get("tx_ref", ""))
    belongs_to_sub = ref == str(sub.tx_ref) or ref.startswith(f"sub{sub.pk}-")

    if not (
        data.get("status") == "successful"
        and belongs_to_sub                        # blocks reusing someone else's transaction id
        and data.get("currency") == sub.semester.currency
        and paid >= sub.amount
    ):
        logger.warning(
            "Payment for subscription %s did not match: %s", sub.pk,
            {k: data.get(k) for k in ("status", "tx_ref", "amount", "currency")},
        )
        return False

    with transaction.atomic():
        locked = SemesterSubscription.objects.select_for_update().get(pk=sub.pk)
        if locked.status != SemesterSubscription.Status.PAID:
            locked.status = SemesterSubscription.Status.PAID
            locked.flutterwave_tx_id = str(data.get("id", ""))
            locked.paid_at = timezone.now()
            locked.save(update_fields=["status", "flutterwave_tx_id", "paid_at"])
    return True


def reconcile(sub):
    """Look up any payment made against this subscription's current reference."""
    return activate_if_paid(sub, fetch_transaction(tx_ref=sub.tx_ref))