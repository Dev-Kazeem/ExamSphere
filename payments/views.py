import hmac
import json
import logging

import requests
from django.utils import timezone
from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from exams.permissions import student_required
from .models import Semester, SemesterSubscription
from .services import (
    API, activate_if_paid, auth_headers, fetch_transaction,
    new_tx_ref, reconcile, subscription_for_ref,
)

logger = logging.getLogger(__name__)
Status = SemesterSubscription.Status


@student_required
@require_POST
def initiate_payment(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id, is_active=True)
    sub, created = SemesterSubscription.objects.get_or_create(
        student=request.user, semester=semester, defaults={"amount": semester.price}
    )

    if sub.status == Status.PAID:
        messages.info(request, "You already have access to this semester.")
        return redirect("payments:checkout")

    # They may have paid already and we just missed the confirmation.
    # Check BEFORE sending them to pay a second time.
    if not created and reconcile(sub):
        messages.success(request, f"We found your payment. {semester.name} is now unlocked.")
        return redirect("payments:checkout")

    # Every new attempt gets its own reference; a used reference can't be reused.
    sub.tx_ref = new_tx_ref(sub)
    sub.amount = semester.price
    sub.status = Status.PENDING
    sub.save(update_fields=["tx_ref", "amount", "status"])

    payload = {
        "tx_ref": sub.tx_ref,
        "amount": str(semester.price),
        "currency": semester.currency,
        "redirect_url": request.build_absolute_uri(reverse("payments:verify")),
        "customer": {
            "email": request.user.email,
            "name": request.user.get_full_name() or request.user.username,
        },
        "customizations": {"title": f"{semester.name} Access"},
    }
    try:
        resp = requests.post(f"{API}/payments", json=payload, headers=auth_headers(), timeout=15)
        data = resp.json()
    except (requests.RequestException, ValueError):
        logger.exception("Could not create a Flutterwave payment link")
        data = {}

    if data.get("status") == "success":
        return redirect(data["data"]["link"])

    logger.warning("Flutterwave refused to create a payment link: %s", data.get("message"))
    messages.error(request, "Couldn't start the payment. Please try again.")
    return redirect("payments:checkout")


@student_required
def verify_payment(request):
    tx_ref = request.GET.get("tx_ref", "")
    transaction_id = request.GET.get("transaction_id")

    sub = subscription_for_ref(tx_ref)
    if sub is None or sub.student_id != request.user.id:
        messages.error(request, "We couldn't match that payment to your account.")
        return redirect("payments:checkout")

    if request.GET.get("status") == "cancelled":
        messages.info(request, "Payment cancelled. You haven't been charged.")
        return redirect("payments:checkout")

    data = (
        fetch_transaction(transaction_id=transaction_id)
        if transaction_id else fetch_transaction(tx_ref=tx_ref)
    )
    if activate_if_paid(sub, data):
        messages.success(request, f"Payment confirmed. You now have access to {sub.semester.name}.")
    else:
        messages.warning(
            request,
            f"We couldn't confirm your payment yet. If you were charged, please don't pay again. "
            f"It will be confirmed automatically, or contact support with reference {tx_ref}.",
        )
    return redirect("payments:checkout")


@csrf_exempt
@require_POST
def flutterwave_webhook(request):
    signature = request.headers.get("verif-hash", "")
    secret = settings.FLUTTERWAVE_WEBHOOK_SECRET
    if not secret or not hmac.compare_digest(signature, secret):
        return HttpResponse(status=401)

    try:
        payload = json.loads(request.body)
    except ValueError:
        return HttpResponse(status=400)

    data = payload.get("data") or {}
    sub = subscription_for_ref(data.get("tx_ref"))
    if sub and data.get("id"):
        # Don't trust the webhook body; confirm with Flutterwave by transaction id.
        activate_if_paid(sub, fetch_transaction(transaction_id=data["id"]))
    return JsonResponse({"status": "ok"})  # always 200 so Flutterwave doesn't retry forever



@student_required
def checkout(request):
    today = timezone.now().date()
    semesters = Semester.objects.filter(is_active=True)
    my_subscriptions = SemesterSubscription.objects.filter(
        student=request.user, status=Status.PAID
    ).select_related("semester")
    paid_semester_ids = set(my_subscriptions.values_list("semester_id", flat=True))
    current_semester_ids = set(
        semesters.filter(start_date__lte=today, end_date__gte=today).values_list("id", flat=True)
    )
    return render(request, "payments/checkout.html", {
        "semesters": semesters,
        "my_subscriptions": my_subscriptions,
        "paid_semester_ids": paid_semester_ids,
        "current_semester_ids": current_semester_ids,
    })