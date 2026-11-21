"""
JAMB subscriptions paid through Flutterwave.

Lessons from the semester payments are built in:
  * every checkout attempt gets its own single-use tx_ref (a used reference can't be reused)
  * amounts are compared as Decimals, never as text
  * the payment is always confirmed with Flutterwave, never trusted from the URL
  * a missed redirect/webhook is repaired by looking the payment up again
"""
import logging
from datetime import timedelta
from decimal import Decimal, InvalidOperation

import requests
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from . import conf
from .models import JambSubscription

API = 'https://api.flutterwave.com/v3'
logger = logging.getLogger(__name__)
Status = JambSubscription.Status


def _headers():
    return {'Authorization': f"Bearer {conf.get('FLUTTERWAVE_SECRET_KEY')}"}


# --------------------------------------------------------------------------
# Access
# --------------------------------------------------------------------------
def active_subscription(user):
    return (
        JambSubscription.objects.filter(user=user, status=Status.PAID, expires_at__gt=timezone.now())
        .select_related('plan').order_by('-expires_at').first()
    )


def user_has_access(user):
    """True when the student may use mock exams and the AI Teacher."""
    if not conf.get_bool('JAMB_REQUIRE_SUBSCRIPTION', True):
        return True  # handy while developing: set JAMB_REQUIRE_SUBSCRIPTION=False
    return active_subscription(user) is not None


# --------------------------------------------------------------------------
# Checkout
# --------------------------------------------------------------------------
def start_checkout(request, plan):
    """Create a pending subscription and a Flutterwave payment link. Returns (link, error)."""
    sub = JambSubscription.objects.create(
        user=request.user, plan=plan, amount=plan.price, currency=plan.currency
    )
    payload = {
        'tx_ref': sub.tx_ref,
        'amount': str(plan.price),
        'currency': plan.currency,
        'redirect_url': request.build_absolute_uri(reverse('jamb_tutor:subscribe_verify')),
        'customer': {
            'email': request.user.email,
            'name': request.user.get_full_name() or request.user.username,
        },
        'customizations': {'title': f"JAMB Tutor: {plan.name}"},
    }
    try:
        response = requests.post(f'{API}/payments', json=payload, headers=_headers(), timeout=15)
        body = response.json()
    except (requests.RequestException, ValueError):
        logger.exception('Could not reach Flutterwave to create a payment link')
        body = {}

    if body.get('status') == 'success' and (body.get('data') or {}).get('link'):
        return body['data']['link'], ''

    logger.warning('Flutterwave refused to create a payment link: %s', body.get('message'))
    sub.status = Status.FAILED
    sub.save(update_fields=['status'])
    return '', "We couldn't start the payment. Please try again in a moment."


# --------------------------------------------------------------------------
# Confirmation
# --------------------------------------------------------------------------
def fetch_transaction(*, transaction_id=None, tx_ref=None):
    """Ask Flutterwave directly."""
    if transaction_id:
        url, params = f'{API}/transactions/{transaction_id}/verify', None
    else:
        url, params = f'{API}/transactions/verify_by_reference', {'tx_ref': tx_ref}
    try:
        response = requests.get(url, params=params, headers=_headers(), timeout=15)
        body = response.json()
    except (requests.RequestException, ValueError):
        logger.exception('Could not reach Flutterwave to verify a payment')
        return None
    if body.get('status') != 'success':
        logger.warning('Flutterwave verify returned %s: %s', response.status_code, body.get('message'))
        return None
    return body.get('data') or None


def activate_if_paid(sub, data):
    """Mark the subscription PAID only if Flutterwave's record genuinely matches it."""
    if not data or sub is None:
        return False
    try:
        paid = Decimal(str(data.get('amount')))
    except (InvalidOperation, TypeError):
        return False

    if not (
        data.get('status') == 'successful'
        and str(data.get('tx_ref', '')) == sub.tx_ref        # blocks reusing someone else's payment
        and data.get('currency') == sub.currency
        and paid >= sub.amount
    ):
        logger.warning(
            'JAMB payment for subscription %s did not match: %s', sub.pk,
            {k: data.get(k) for k in ('status', 'tx_ref', 'amount', 'currency')},
        )
        return False

    with transaction.atomic():
        locked = JambSubscription.objects.select_for_update().select_related('plan').get(pk=sub.pk)
        if locked.status == Status.PAID:
            return True
        now = timezone.now()
        current = (
            JambSubscription.objects.filter(user=locked.user, status=Status.PAID, expires_at__gt=now)
            .order_by('-expires_at').first()
        )
        start = current.expires_at if current else now      # renewals stack on the end of the current plan
        locked.status = Status.PAID
        locked.paid_at = now
        locked.starts_at = start
        locked.expires_at = start + timedelta(days=locked.plan.duration_days)
        locked.flutterwave_tx_id = str(data.get('id', ''))
        locked.save(update_fields=['status', 'paid_at', 'starts_at', 'expires_at', 'flutterwave_tx_id'])
    return True


def subscription_for_ref(tx_ref):
    return JambSubscription.objects.select_related('plan', 'user').filter(tx_ref=str(tx_ref or '')).first()


def reconcile_pending(user):
    """Repair payments whose redirect or webhook never arrived. Returns how many were activated."""
    since = timezone.now() - timedelta(days=3)
    pending = JambSubscription.objects.filter(
        user=user, status__in=[Status.PENDING, Status.FAILED], created_at__gte=since
    ).select_related('plan')[:3]
    return sum(1 for sub in pending if activate_if_paid(sub, fetch_transaction(tx_ref=sub.tx_ref)))


def handle_flutterwave_event(data):
    """Called from the shared Flutterwave webhook for references that start with 'jt-'."""
    sub = subscription_for_ref(data.get('tx_ref'))
    if sub and data.get('id'):
        return activate_if_paid(sub, fetch_transaction(transaction_id=data['id']))
    return False
