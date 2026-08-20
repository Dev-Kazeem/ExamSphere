import hashlib, hmac, requests
from django.conf import settings
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, JsonResponse

from exams.permissions import student_required
from .models import Semester, SemesterSubscription


@student_required
def initiate_payment(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id, is_active=True)
    existing = SemesterSubscription.objects.filter(student=request.user, semester=semester, status='PAID').first()
    if existing:
        messages.info(request, "You already have access to this semester.")
        return redirect('exams:student_dashboard')

    sub, _ = SemesterSubscription.objects.get_or_create(
        student=request.user, semester=semester,
        defaults={'amount': semester.price}
    )

    payload = {
        "tx_ref": sub.tx_ref,
        "amount": str(semester.price),
        "currency": semester.currency,
        "redirect_url": request.build_absolute_uri(reverse('payments:verify')),
        "customer": {"email": request.user.email, "name": request.user.get_full_name() or request.user.username},
        "customizations": {"title": f"{semester.name} Access"},
    }
    resp = requests.post(
        "https://api.flutterwave.com/v3/payments",
        json=payload,
        headers={"Authorization": f"Bearer {settings.FLUTTERWAVE_SECRET_KEY}"},
        timeout=15,
    )
    data = resp.json()
    if data.get('status') == 'success':
        return redirect(data['data']['link'])
    messages.error(request, "Couldn't start payment — please try again.")
    return redirect('exams:student_dashboard')


@student_required
def verify_payment(request):
    tx_id = request.GET.get('transaction_id')
    tx_ref = request.GET.get('tx_ref')
    if not tx_id:
        messages.error(request, "Payment verification failed.")
        return redirect('exams:student_dashboard')

    resp = requests.get(
        f"https://api.flutterwave.com/v3/transactions/{tx_id}/verify",
        headers={"Authorization": f"Bearer {settings.FLUTTERWAVE_SECRET_KEY}"},
        timeout=15,
    )
    data = resp.json().get('data', {})
    sub = get_object_or_404(SemesterSubscription, tx_ref=tx_ref, student=request.user)

    if (data.get('status') == 'successful'
            and str(data.get('amount')) == str(sub.amount)
            and data.get('currency') == sub.semester.currency):
        sub.status = 'PAID'
        sub.flutterwave_tx_id = str(tx_id)
        from django.utils import timezone
        sub.paid_at = timezone.now()
        sub.save()
        messages.success(request, f"Payment confirmed — you now have access to {sub.semester.name}.")
    else:
        sub.status = 'FAILED'
        sub.save()
        messages.error(request, "Payment could not be verified.")
    return redirect('exams:student_dashboard')


@csrf_exempt
def flutterwave_webhook(request):
    signature = request.headers.get('verif-hash')
    if not signature or not hmac.compare_digest(signature, settings.FLUTTERWAVE_WEBHOOK_SECRET):
        return HttpResponse(status=401)

    import json
    payload = json.loads(request.body)
    data = payload.get('data', {})
    tx_ref = data.get('tx_ref')
    sub = SemesterSubscription.objects.filter(tx_ref=tx_ref).first()
    if sub and data.get('status') == 'successful' and str(data.get('amount')) == str(sub.amount):
        from django.utils import timezone
        sub.status = 'PAID'
        sub.flutterwave_tx_id = str(data.get('id'))
        sub.paid_at = timezone.now()
        sub.save()
    return JsonResponse({"status": "ok"})
