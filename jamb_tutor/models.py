from datetime import timedelta

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.utils import timezone

from .logic import (
    current_streak, generate_tx_ref, lagos_today, next_streak, percentage,
    projected_score, question_hash,
)

AUTH_USER = settings.AUTH_USER_MODEL


# ==========================================================================
# Student profile
# ==========================================================================
class JambProfile(models.Model):
    class Language(models.TextChoices):
        PIDGIN = 'pidgin', 'Pidgin'
        ENGLISH = 'english', 'English'
        HAUSA = 'hausa', 'Hausa'

    class Combination(models.TextChoices):
        SCIENCE = 'science', 'Science'
        ART = 'art', 'Art'
        COMMERCIAL = 'commercial', 'Commercial'

    class WaState(models.TextChoices):
        IDLE = 'idle', 'Idle'
        AWAITING_SUBJECT = 'awaiting_subject', 'Choosing a subject'
        IN_MOCK = 'in_mock', 'In a mock'

    user = models.OneToOneField(AUTH_USER, on_delete=models.CASCADE, related_name='jamb_profile')
    preferred_language = models.CharField(max_length=10, choices=Language.choices, default=Language.ENGLISH)
    target_school = models.CharField(max_length=150)
    target_score = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(100), MaxValueValidator(400)], help_text="Out of 400."
    )
    combination = models.CharField(max_length=12, choices=Combination.choices)
    phone_e164 = models.CharField(
        max_length=15, unique=True,
        help_text="Digits only, e.g. 2348031234567. Used to match WhatsApp messages to this student.",
    )

    streak_count = models.PositiveIntegerField(default=0)
    last_activity_date = models.DateField(null=True, blank=True)

    # WhatsApp conversation state
    wa_state = models.CharField(max_length=20, choices=WaState.choices, default=WaState.IDLE)
    wa_attempt = models.ForeignKey(
        'MockAttempt', null=True, blank=True, on_delete=models.SET_NULL, related_name='+'
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} ({self.get_combination_display()})"

    @property
    def current_streak(self):
        return current_streak(self.last_activity_date, self.streak_count, lagos_today())

    def record_activity(self):
        """Call whenever the student studies (mock finished, question asked)."""
        today = lagos_today()
        if self.last_activity_date == today:
            return
        self.streak_count, self.last_activity_date = next_streak(
            self.last_activity_date, self.streak_count, today
        )
        self.save(update_fields=['streak_count', 'last_activity_date'])


# ==========================================================================
# Question bank
# ==========================================================================
class Subject(models.Model):
    name = models.CharField(max_length=60, unique=True)
    slug = models.SlugField(unique=True)
    full_name = models.CharField(max_length=100)
    icon = models.CharField(max_length=40, default='bi-book')
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name


class Topic(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='topics')
    name = models.CharField(max_length=150)

    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(fields=['subject', 'name'], name='uniq_topic_per_subject'),
        ]

    def __str__(self):
        return f"{self.subject.name}: {self.name}"


class Question(models.Model):
    class Option(models.TextChoices):
        A = 'A', 'A'
        B = 'B', 'B'
        C = 'C', 'C'
        D = 'D', 'D'

    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='questions')
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name='questions')
    question_text = models.TextField()
    option_a = models.CharField(max_length=500)
    option_b = models.CharField(max_length=500)
    option_c = models.CharField(max_length=500)
    option_d = models.CharField(max_length=500)
    correct_option = models.CharField(max_length=1, choices=Option.choices)
    explanation = models.TextField(blank=True)
    year = models.PositiveSmallIntegerField(null=True, blank=True)

    text_hash = models.CharField(max_length=64, editable=False, db_index=True)
    created_by = models.ForeignKey(AUTH_USER, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['subject', 'text_hash'], name='uniq_question_per_subject'),
        ]

    def __str__(self):
        return f"[{self.subject.name}] {self.question_text[:60]}"

    def save(self, *args, **kwargs):
        self.text_hash = question_hash(self.subject_id, self.question_text)
        super().save(*args, **kwargs)

    @property
    def options(self):
        return [('A', self.option_a), ('B', self.option_b), ('C', self.option_c), ('D', self.option_d)]


# ==========================================================================
# Mock exams
# ==========================================================================
class MockAttempt(models.Model):
    class Status(models.TextChoices):
        IN_PROGRESS = 'IN_PROGRESS', 'In progress'
        COMPLETED = 'COMPLETED', 'Completed'
        TIMED_OUT = 'TIMED_OUT', 'Timed out'
        ABANDONED = 'ABANDONED', 'Abandoned'

    class Source(models.TextChoices):
        WEB = 'WEB', 'Web'
        WHATSAPP = 'WHATSAPP', 'WhatsApp'

    FINISHED = ('COMPLETED', 'TIMED_OUT')

    user = models.ForeignKey(AUTH_USER, on_delete=models.CASCADE, related_name='mock_attempts')
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name='attempts')
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.WEB)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.IN_PROGRESS)
    total_questions = models.PositiveSmallIntegerField()
    score = models.PositiveSmallIntegerField(default=0)
    duration_seconds = models.PositiveIntegerField(default=1800, help_text="0 means no time limit.")
    wa_index = models.PositiveSmallIntegerField(default=0)
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-started_at']
        indexes = [models.Index(fields=['user', 'status'])]

    def __str__(self):
        return f"{self.user} - {self.subject} ({self.score}/{self.total_questions})"

    # ---- timing ----
    @property
    def deadline(self):
        return self.started_at + timedelta(seconds=self.duration_seconds)

    def is_expired(self):
        return bool(self.duration_seconds) and timezone.now() >= self.deadline

    @property
    def seconds_remaining(self):
        if not self.duration_seconds:
            return 0
        return max(0, int((self.deadline - timezone.now()).total_seconds()))

    # ---- results ----
    @property
    def is_finished(self):
        return self.status in self.FINISHED

    @property
    def percentage(self):
        return percentage(self.score, self.total_questions)

    @property
    def projected_score(self):
        return projected_score(self.score, self.total_questions)

    def passed_for(self, target_score):
        return self.projected_score >= target_score

    @transaction.atomic
    def finalize(self, status=Status.COMPLETED):
        """Grade the saved answers and close the attempt. Safe to call twice."""
        locked = MockAttempt.objects.select_for_update().get(pk=self.pk)
        if locked.status != self.Status.IN_PROGRESS:
            self.status, self.score, self.submitted_at = locked.status, locked.score, locked.submitted_at
            return False
        answers = list(locked.answers.select_related('question'))
        correct = 0
        for answer in answers:
            answer.is_correct = bool(answer.selected_option) and answer.selected_option == answer.question.correct_option
            correct += answer.is_correct
        MockAnswer.objects.bulk_update(answers, ['is_correct'])
        locked.status = status
        locked.score = correct
        locked.submitted_at = timezone.now()
        locked.save(update_fields=['status', 'score', 'submitted_at'])
        self.status, self.score, self.submitted_at = locked.status, locked.score, locked.submitted_at
        return True


class MockAnswer(models.Model):
    attempt = models.ForeignKey(MockAttempt, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='+')
    position = models.PositiveSmallIntegerField()
    selected_option = models.CharField(max_length=1, blank=True)
    is_correct = models.BooleanField(default=False)
    answered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['position']
        constraints = [
            models.UniqueConstraint(fields=['attempt', 'question'], name='uniq_answer_per_question'),
        ]


# ==========================================================================
# AI Teacher chat (web and WhatsApp share one history)
# ==========================================================================
class ChatMessage(models.Model):
    class Role(models.TextChoices):
        USER = 'user', 'Student'
        ASSISTANT = 'assistant', 'Teacher'

    class Channel(models.TextChoices):
        WEB = 'web', 'App'
        WHATSAPP = 'whatsapp', 'WhatsApp'

    class Kind(models.TextChoices):
        AI = 'ai', 'AI teacher'      # used as conversation context for Gemini
        BOT = 'bot', 'Menu / mock'   # WhatsApp menu and mock messages, not sent to Gemini

    user = models.ForeignKey(AUTH_USER, on_delete=models.CASCADE, related_name='jamb_chat_messages')
    role = models.CharField(max_length=10, choices=Role.choices)
    content = models.TextField()
    channel = models.CharField(max_length=10, choices=Channel.choices, default=Channel.WEB)
    kind = models.CharField(max_length=4, choices=Kind.choices, default=Kind.AI)
    wa_message_id = models.CharField(max_length=120, null=True, blank=True, unique=True)
    reply_sent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']
        indexes = [models.Index(fields=['user', 'id'])]

    def __str__(self):
        return f"{self.user} {self.role}: {self.content[:40]}"


# ==========================================================================
# Subscriptions
# ==========================================================================
class JambPlan(models.Model):
    name = models.CharField(max_length=80)
    description = models.CharField(max_length=200, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='NGN')
    duration_days = models.PositiveIntegerField(default=30)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['price']

    def __str__(self):
        return f"{self.name} ({self.currency} {self.price})"


class JambSubscription(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        PAID = 'PAID', 'Paid'
        FAILED = 'FAILED', 'Failed'

    user = models.ForeignKey(AUTH_USER, on_delete=models.CASCADE, related_name='jamb_subscriptions')
    plan = models.ForeignKey(JambPlan, on_delete=models.PROTECT, related_name='subscriptions')
    tx_ref = models.CharField(max_length=100, unique=True, default=generate_tx_ref)
    flutterwave_tx_id = models.CharField(max_length=100, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='NGN')
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user} - {self.plan.name} ({self.status})"


# ==========================================================================
# Admin: document import jobs (PDF / DOCX -> Gemini -> review -> save)
# ==========================================================================
class ImportJob(models.Model):
    class Status(models.TextChoices):
        PROCESSING = 'PROCESSING', 'Extracting'
        READY = 'READY', 'Ready for review'
        SAVED = 'SAVED', 'Saved'

    created_by = models.ForeignKey(AUTH_USER, null=True, on_delete=models.SET_NULL, related_name='+')
    filename = models.CharField(max_length=255)
    kind = models.CharField(max_length=4)  # 'pdf' or 'docx'
    default_subject = models.ForeignKey(Subject, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    default_year = models.PositiveSmallIntegerField(null=True, blank=True)

    source_pdf = models.BinaryField(null=True, blank=True, editable=False)
    chunks = models.JSONField(default=list, blank=True)       # text chunks for DOCX
    total_chunks = models.PositiveSmallIntegerField(default=0)
    next_chunk = models.PositiveSmallIntegerField(default=0)

    extracted = models.JSONField(default=list, blank=True)    # draft question rows
    errors = models.JSONField(default=list, blank=True)
    result = models.JSONField(default=dict, blank=True)

    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PROCESSING)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.filename} ({self.status})"


# 404 = wrong/retired model name; 408/429/5xx = timeouts, quota or capacity.
FALLBACK_STATUS = {404, 408, 429, 500, 502, 503, 504}


def model_chain(primary, fallbacks):
    """Primary model first, then each fallback, without repeats or blanks."""
    chain = []
    for name in [primary, *(fallbacks or [])]:
        name = (name or '').strip()
        if name and name not in chain:
            chain.append(name)
    return chain


def should_try_next_model(status_code):
    return status_code in FALLBACK_STATUS