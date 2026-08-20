from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Exam(models.Model):

    """ for payment  """
    ...
    semester = models.ForeignKey(
        'payments.Semester', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='exams', help_text="Leave blank for a free exam."
    )

    def can_be_attempted_by(self, student):
        if not self.is_available_for_students():
            return False
        if self.semester_id and not self.semester.subscriptions.filter(
            student=student, status='PAID'
        ).exists():
            return False
        return self.attempts_used_by(student) < self.max_attempts


    """A multiple-choice exam created by a Teacher."""

    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='created_exams',
        limit_choices_to={'role': 'TEACHER'},
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    subject = models.CharField(max_length=100, blank=True)

    duration_minutes = models.PositiveIntegerField(
        default=30, help_text="Time allowed to complete the exam, in minutes."
    )
    start_time = models.DateTimeField(help_text="When the exam becomes available to students.")
    end_time = models.DateTimeField(help_text="When the exam closes; no new attempts after this.")

    pass_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('40.00'),
        help_text="Minimum percentage required to pass."
    )
    max_attempts = models.PositiveIntegerField(default=1)
    shuffle_questions = models.BooleanField(default=True)
    is_published = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    def clean(self):
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError("End time must be after start time.")

    @property
    def total_marks(self):
        return self.questions.aggregate(total=models.Sum('marks'))['total'] or 0

    @property
    def question_count(self):
        return self.questions.count()

    def is_within_window(self, moment=None):
        moment = moment or timezone.now()
        return self.start_time <= moment <= self.end_time

    def is_available_for_students(self):
        return self.is_published and self.is_within_window() and self.question_count > 0

    def attempts_used_by(self, student):
        return self.attempts.filter(student=student).count()

    def can_be_attempted_by(self, student):
        if not self.is_available_for_students():
            return False
        return self.attempts_used_by(student) < self.max_attempts


class Question(models.Model):
    """A single multiple-choice question belonging to an Exam."""

    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='questions')
    text = models.TextField()
    marks = models.PositiveIntegerField(default=1)
    order = models.PositiveIntegerField(default=0)
    explanation = models.TextField(
        blank=True, help_text="Optional explanation shown to students after grading."
    )

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f"{self.exam.title} — Q{self.order}: {self.text[:50]}"

    @property
    def correct_choice(self):
        return self.choices.filter(is_correct=True).first()


class Choice(models.Model):
    """One answer option for a Question."""

    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='choices')
    text = models.CharField(max_length=500)
    is_correct = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.text} ({'correct' if self.is_correct else 'incorrect'})"


class ExamAttempt(models.Model):
    """A single student's attempt at an exam."""

    class Status(models.TextChoices):
        IN_PROGRESS = 'IN_PROGRESS', 'In progress'
        COMPLETED = 'COMPLETED', 'Completed'
        TIMED_OUT = 'TIMED_OUT', 'Timed out'

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='exam_attempts',
        limit_choices_to={'role': 'STUDENT'},
    )
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='attempts')
    attempt_number = models.PositiveIntegerField(default=1)

    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.IN_PROGRESS)

    score = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('0.00'))

    class Meta:
        ordering = ['-started_at']
        unique_together = ('student', 'exam', 'attempt_number')

    def __str__(self):
        return f"{self.student.username} — {self.exam.title} (#{self.attempt_number})"

    @property
    def deadline(self):
        from datetime import timedelta
        return min(self.started_at + timedelta(minutes=self.exam.duration_minutes), self.exam.end_time)

    @property
    def is_time_expired(self):
        return timezone.now() >= self.deadline

    @property
    def seconds_remaining(self):
        remaining = (self.deadline - timezone.now()).total_seconds()
        return max(0, int(remaining))

    @property
    def percentage(self):
        total = self.exam.total_marks
        if not total:
            return Decimal('0.00')
        pct = (self.score / Decimal(total)) * Decimal('100')
        return pct.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    @property
    def passed(self):
        return self.status == self.Status.COMPLETED and self.percentage >= self.exam.pass_percentage

    def grade(self):
        """Auto-grade the attempt from saved StudentAnswers and store the score."""
        total_score = 0
        for answer in self.answers.select_related('question', 'selected_choice'):
            is_correct = bool(answer.selected_choice and answer.selected_choice.is_correct)
            if answer.is_correct != is_correct:
                answer.is_correct = is_correct
                answer.save(update_fields=['is_correct'])
            if is_correct:
                total_score += answer.question.marks
        self.score = Decimal(total_score)
        self.submitted_at = timezone.now()
        self.status = self.Status.COMPLETED
        self.save(update_fields=['score', 'submitted_at', 'status'])
        return self.score


class StudentAnswer(models.Model):
    """A student's selected choice for one question within a specific attempt."""

    attempt = models.ForeignKey(ExamAttempt, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='student_answers')
    selected_choice = models.ForeignKey(
        Choice, on_delete=models.SET_NULL, null=True, blank=True, related_name='selected_by'
    )
    is_correct = models.BooleanField(default=False)
    answered_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('attempt', 'question')

    def __str__(self):
        return f"{self.attempt.student.username} → Q{self.question_id}"
