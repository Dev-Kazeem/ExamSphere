import json
import logging
import random
from datetime import timedelta

from django.contrib import messages
from django.db import transaction
from django.db.models import Avg, Count, ExpressionWrapper, FloatField
from django.db.models.functions import Cast
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from accounts.utils import send_verification_email

from . import ai, billing, chat, conf, logic
from .constants import (
    COMBINATIONS, JAMB_MAX_SCORE, MOCK_GRACE_SECONDS, MOCK_MIN_QUESTIONS, MOCK_QUESTIONS, MOCK_SECONDS,
)
from .decorators import jamb_student_required, subscription_required
from .forms import JambSignupForm
from .models import (
    ChatMessage, JambPlan, JambSubscription, MockAnswer, MockAttempt, Question, Subject, Topic,
)

logger = logging.getLogger(__name__)
Status = MockAttempt.Status
LETTERS = ('A', 'B', 'C', 'D')
CHAT_PAGE = 30


def _pct(prefix=''):
    """Per-attempt percentage as a float, computed in the database (works on SQLite and Postgres)."""
    return ExpressionWrapper(
        Cast(f'{prefix}score', FloatField()) * 100.0 / Cast(f'{prefix}total_questions', FloatField()),
        output_field=FloatField(),
    )


def _finished(user):
    return MockAttempt.objects.filter(user=user, status__in=MockAttempt.FINISHED, total_questions__gt=0)


# ==========================================================================
# Landing and signup
# ==========================================================================
def home(request):
    if request.user.is_authenticated and hasattr(request.user, 'jamb_profile'):
        return redirect('jamb_tutor:dashboard')
    return render(request, 'jamb_tutor/landing.html')


def signup(request):
    if request.user.is_authenticated:
        return redirect('accounts:dashboard')
    form = JambSignupForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        try:
            send_verification_email(request, user)
        except Exception:
            logger.exception('Could not send the verification email to %s', user.email)
            messages.warning(
                request,
                "Your account was created, but we couldn't send the verification email. "
                "Enter your email below to get a new link.",
            )
            return redirect('accounts:resend_verification')
        return render(request, 'registration/verify_email_sent.html', {'email': user.email})
    return render(request, 'jamb_tutor/signup.html', {'form': form})


# ==========================================================================
# Dashboard
# ==========================================================================
@jamb_student_required
def dashboard(request):
    user = request.user
    profile = user.jamb_profile
    finished = _finished(user)

    stats = finished.aggregate(attempts=Count('id'), avg_pct=Avg(_pct()))
    attempts = stats['attempts'] or 0
    avg_pct = round(stats['avg_pct'] or 0, 1)
    avg_projected = round(avg_pct * JAMB_MAX_SCORE / 100)
    answered = MockAnswer.objects.filter(attempt__in=finished).exclude(selected_option='').count()

    target = profile.target_score
    progress = min(100, round(avg_projected / target * 100)) if attempts else 0

    return render(request, 'jamb_tutor/dashboard.html', {
        'profile': profile,
        'greeting': logic.greeting_for(
            user.first_name or user.username, profile.preferred_language, logic.lagos_now().hour
        ),
        'streak': profile.current_streak,
        'attempts': attempts,
        'answered': answered,
        'avg_pct': avg_pct,
        'avg_projected': avg_projected,
        'target': target,
        'progress': progress,
        'fill_pct': min(100, round(avg_projected / JAMB_MAX_SCORE * 100)),
        'target_pct': min(100, round(target / JAMB_MAX_SCORE * 100)),
        'recent': list(finished.select_related('subject')[:3]),
        'combo_subjects': COMBINATIONS.get(profile.combination, []),
        'has_access': billing.user_has_access(user),
    })


# ==========================================================================
# Study topics
# ==========================================================================
def _ordered_subjects(profile):
    subjects = list(Subject.objects.annotate(q_count=Count('questions')))
    mine = COMBINATIONS.get(profile.combination, [])
    subjects.sort(key=lambda s: (s.name not in mine, s.sort_order))
    for s in subjects:
        s.in_combination = s.name in mine
    return subjects


@jamb_student_required
def topics(request):
    return render(request, 'jamb_tutor/topics.html', {'subjects': _ordered_subjects(request.user.jamb_profile)})


@jamb_student_required
def topic_detail(request, slug):
    subject = get_object_or_404(Subject, slug=slug)
    topic_list = list(Topic.objects.filter(subject=subject).annotate(q_count=Count('questions')))
    return render(request, 'jamb_tutor/topic_detail.html', {
        'subject': subject,
        'topics': topic_list,
        'total': sum(t.q_count for t in topic_list),
    })


# ==========================================================================
# Leaderboard
# ==========================================================================
@jamb_student_required
def leaderboard(request):
    rows = list(
        MockAttempt.objects.filter(
            status__in=MockAttempt.FINISHED, total_questions__gt=0,
            user__is_active=True, user__jamb_profile__isnull=False,
        )
        .values('user_id', 'user__username', 'user__jamb_profile__target_school')
        .annotate(avg_pct=Avg(_pct()), total_attempts=Count('id'))
        .order_by('-avg_pct', '-total_attempts', 'user__username')[:10]
    )
    for rank, row in enumerate(rows, start=1):
        row['rank'] = rank
        row['avg_pct'] = round(row['avg_pct'], 1)
        row['is_me'] = row['user_id'] == request.user.id
    return render(request, 'jamb_tutor/leaderboard.html', {'rows': rows})


# ==========================================================================
# Mock exam
# ==========================================================================
@subscription_required
def mock_start(request):
    profile = request.user.jamb_profile

    if request.method == 'POST':
        subject = get_object_or_404(Subject, slug=request.POST.get('subject', ''))

        active = MockAttempt.objects.filter(
            user=request.user, source=MockAttempt.Source.WEB, status=Status.IN_PROGRESS
        ).first()
        if active:
            if active.is_expired():
                active.finalize(Status.TIMED_OUT)
            else:
                messages.info(request, "You have a mock in progress. Finish it first.")
                return redirect('jamb_tutor:mock_take', attempt_id=active.pk)

        ids = list(Question.objects.filter(subject=subject).values_list('id', flat=True))
        if len(ids) < MOCK_MIN_QUESTIONS:
            messages.error(request, f"There aren't enough {subject.name} questions yet. Try another subject.")
            return redirect('jamb_tutor:mock_start')

        chosen = random.sample(ids, min(MOCK_QUESTIONS, len(ids)))
        with transaction.atomic():
            attempt = MockAttempt.objects.create(
                user=request.user, subject=subject, total_questions=len(chosen), duration_seconds=MOCK_SECONDS,
            )
            MockAnswer.objects.bulk_create(
                [MockAnswer(attempt=attempt, question_id=qid, position=i) for i, qid in enumerate(chosen)]
            )
        return redirect('jamb_tutor:mock_take', attempt_id=attempt.pk)

    return render(request, 'jamb_tutor/mock_start.html', {
        'subjects': _ordered_subjects(profile),
        'min_questions': MOCK_MIN_QUESTIONS,
        'n_questions': MOCK_QUESTIONS,
        'minutes': MOCK_SECONDS // 60,
    })


def _web_attempt(request, attempt_id):
    """An attempt that is taken in the browser (timer, autosave)."""
    return get_object_or_404(
        MockAttempt.objects.select_related('subject'),
        pk=attempt_id, user=request.user, source=MockAttempt.Source.WEB,
    )


def _my_attempt(request, attempt_id):
    """Any of the student's attempts, including ones taken on WhatsApp (for results and review)."""
    return get_object_or_404(
        MockAttempt.objects.select_related('subject'), pk=attempt_id, user=request.user,
    )


@subscription_required
def mock_take(request, attempt_id):
    attempt = _web_attempt(request, attempt_id)
    if attempt.status != Status.IN_PROGRESS:
        return redirect('jamb_tutor:mock_result', attempt_id=attempt.pk)

    if attempt.is_expired():
        attempt.finalize(Status.TIMED_OUT)
        request.user.jamb_profile.record_activity()
        messages.warning(request, "Time was up, so your mock was submitted automatically.")
        return redirect('jamb_tutor:mock_result', attempt_id=attempt.pk)

    answers = list(attempt.answers.select_related('question'))

    if request.method == 'POST':
        # A submission far past the deadline only counts the answers that were autosaved in time.
        late = timezone.now() > attempt.deadline + timedelta(seconds=MOCK_GRACE_SECONDS)
        if not late:
            changed = []
            for answer in answers:
                choice = request.POST.get(f'q{answer.question_id}', '').upper()
                if choice in LETTERS and choice != answer.selected_option:
                    answer.selected_option = choice
                    answer.answered_at = timezone.now()
                    changed.append(answer)
            if changed:
                MockAnswer.objects.bulk_update(changed, ['selected_option', 'answered_at'])
        attempt.finalize(Status.TIMED_OUT if late else Status.COMPLETED)
        request.user.jamb_profile.record_activity()
        return redirect('jamb_tutor:mock_result', attempt_id=attempt.pk)

    return render(request, 'jamb_tutor/mock_take.html', {
        'attempt': attempt,
        'answers': answers,
        'seconds_remaining': attempt.seconds_remaining,
    })


@require_POST
@subscription_required
def mock_autosave(request, attempt_id):
    """Saves each answer as it's picked, so closing the tab or a flaky network doesn't lose work."""
    attempt = _web_attempt(request, attempt_id)
    if attempt.status != Status.IN_PROGRESS or timezone.now() > attempt.deadline + timedelta(seconds=MOCK_GRACE_SECONDS):
        return JsonResponse({'ok': False, 'finished': True}, status=409)
    try:
        data = json.loads(request.body or '{}')
        question_id = int(data.get('question_id'))
        option = str(data.get('option', '')).upper()
    except (ValueError, TypeError):
        return JsonResponse({'ok': False}, status=400)
    if option not in LETTERS and option != '':
        return JsonResponse({'ok': False}, status=400)
    updated = attempt.answers.filter(question_id=question_id).update(selected_option=option, answered_at=timezone.now())
    return JsonResponse({'ok': bool(updated)})


@jamb_student_required
def mock_result(request, attempt_id):
    attempt = _my_attempt(request, attempt_id)
    if attempt.status == Status.IN_PROGRESS:
        if attempt.source == MockAttempt.Source.WEB:
            return redirect('jamb_tutor:mock_take', attempt_id=attempt.pk)
        return redirect('jamb_tutor:dashboard')
    if attempt.status == Status.ABANDONED:
        return redirect('jamb_tutor:mock_history')
    profile = request.user.jamb_profile
    skipped = attempt.answers.filter(selected_option='').count()
    return render(request, 'jamb_tutor/mock_result.html', {
        'attempt': attempt,
        'target': profile.target_score,
        'passed': attempt.passed_for(profile.target_score),
        'skipped': skipped,
        'wrong': attempt.total_questions - attempt.score - skipped,
    })


@jamb_student_required
def mock_review(request, attempt_id):
    attempt = _my_attempt(request, attempt_id)
    if attempt.status in (Status.IN_PROGRESS, Status.ABANDONED):
        return redirect('jamb_tutor:mock_history')
    answers = attempt.answers.select_related('question')
    return render(request, 'jamb_tutor/mock_review.html', {'attempt': attempt, 'answers': answers})


@jamb_student_required
def mock_history(request):
    attempts = MockAttempt.objects.filter(
        user=request.user, status__in=MockAttempt.FINISHED
    ).select_related('subject')[:50]
    return render(request, 'jamb_tutor/mock_history.html', {
        'attempts': attempts, 'target': request.user.jamb_profile.target_score,
    })


# ==========================================================================
# Ask AI Teacher
# ==========================================================================
def _serialize(message):
    return {
        'id': message.id, 'role': message.role, 'content': message.content,
        'channel': message.channel, 'created_at': message.created_at.isoformat(),
    }


@subscription_required
def teacher_chat(request):
    qs = ChatMessage.objects.filter(user=request.user)
    recent = list(qs.order_by('-id')[:CHAT_PAGE])[::-1]
    return render(request, 'jamb_tutor/chat.html', {
        'chat_messages': recent,
        'has_more': bool(recent) and qs.filter(id__lt=recent[0].id).exists(),
        'ai_ready': ai.is_configured(),
        'profile': request.user.jamb_profile,
    })


@require_GET
@subscription_required
def teacher_history(request):
    """Older messages for scrolling back: ?before=<message id>."""
    try:
        before = int(request.GET.get('before', ''))
    except ValueError:
        return JsonResponse({'messages': [], 'has_more': False}, status=400)
    qs = ChatMessage.objects.filter(user=request.user, id__lt=before)
    older = list(qs.order_by('-id')[:CHAT_PAGE])[::-1]
    has_more = bool(older) and ChatMessage.objects.filter(user=request.user, id__lt=older[0].id).exists()
    return JsonResponse({'messages': [_serialize(m) for m in older], 'has_more': has_more})


@require_POST
@jamb_student_required
def teacher_send(request):
    user = request.user
    profile = user.jamb_profile

    if not billing.user_has_access(user):
        return JsonResponse({
            'error': 'subscription_required',
            'reply': "Subscribe to chat with your AI Teacher.",
            'redirect': reverse('jamb_tutor:subscribe'),
        }, status=402)

    try:
        text = str(json.loads(request.body or '{}').get('message', '')).strip()
    except (ValueError, AttributeError):
        return JsonResponse({'error': 'bad_request'}, status=400)
    if not text or len(text) > 1500:
        return JsonResponse({'error': 'Type a question (up to 1500 characters).'}, status=400)

    if not ai.is_configured():
        return JsonResponse({'reply': ai.FALLBACK_MESSAGE, 'fallback': True})
    if chat.rate_limited(user):
        return JsonResponse({
            'reply': "You've asked a lot of questions this hour. Take a short break and try again soon.",
            'fallback': True,
        }, status=429)

    try:
        reply = ai.teacher_reply(profile, chat.recent_history(user), text, channel='web')
    except ai.AIUnavailable:
        return JsonResponse({
            'reply': "Your teacher couldn't answer just now. Please try again in a moment.",
            'fallback': True,
        }, status=502)

    with transaction.atomic():
        ChatMessage.objects.create(user=user, role=ChatMessage.Role.USER, content=text)
        answer = ChatMessage.objects.create(user=user, role=ChatMessage.Role.ASSISTANT, content=reply)
    profile.record_activity()
    return JsonResponse({'reply': reply, 'id': answer.id, 'created_at': answer.created_at.isoformat()})


# ==========================================================================
# Subscription
# ==========================================================================
@jamb_student_required
def subscribe(request):
    activated = billing.reconcile_pending(request.user) if JambSubscription.objects.filter(
        user=request.user, status__in=[JambSubscription.Status.PENDING, JambSubscription.Status.FAILED]
    ).exists() else 0
    if activated:
        messages.success(request, "We found your payment. Your subscription is now active.")
    return render(request, 'jamb_tutor/subscribe.html', {
        'plans': JambPlan.objects.filter(is_active=True),
        'current': billing.active_subscription(request.user),
        'paywall_on': conf.get_bool('JAMB_REQUIRE_SUBSCRIPTION', True),
    })


@require_POST
@jamb_student_required
def subscribe_pay(request, plan_id):
    plan = get_object_or_404(JambPlan, pk=plan_id, is_active=True)
    link, error = billing.start_checkout(request, plan)
    if link:
        return redirect(link)
    messages.error(request, error)
    return redirect('jamb_tutor:subscribe')


@jamb_student_required
def subscribe_verify(request):
    """Flutterwave sends the student back here after paying."""
    tx_ref = request.GET.get('tx_ref', '')
    sub = billing.subscription_for_ref(tx_ref)
    if sub is None or sub.user_id != request.user.id:
        messages.error(request, "We couldn't match that payment to your account.")
        return redirect('jamb_tutor:subscribe')
    if request.GET.get('status') == 'cancelled':
        messages.info(request, "Payment cancelled. You haven't been charged.")
        return redirect('jamb_tutor:subscribe')

    transaction_id = request.GET.get('transaction_id')
    data = billing.fetch_transaction(transaction_id=transaction_id) if transaction_id \
        else billing.fetch_transaction(tx_ref=tx_ref)
    if billing.activate_if_paid(sub, data):
        messages.success(request, "Payment confirmed. Your subscription is active.")
        return redirect('jamb_tutor:dashboard')
    messages.warning(
        request,
        "We couldn't confirm your payment yet. If you were charged, don't pay again: it will be "
        f"confirmed automatically, or contact support with reference {tx_ref}.",
    )
    return redirect('jamb_tutor:subscribe')
