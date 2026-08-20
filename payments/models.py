import uuid
from django.conf import settings
from django.db import models


class Semester(models.Model):
    name = models.CharField(max_length=100)  # e.g. "Fall 2026"
    start_date = models.DateField()
    end_date = models.DateField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='NGN')
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-start_date']

    def __str__(self):
        return self.name


class SemesterSubscription(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        PAID = 'PAID', 'Paid'
        FAILED = 'FAILED', 'Failed'

    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='subscriptions')
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE, related_name='subscriptions')
    tx_ref = models.CharField(max_length=100, unique=True, default=uuid.uuid4)
    flutterwave_tx_id = models.CharField(max_length=100, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('student', 'semester')

    def __str__(self):
        return f"{self.student} — {self.semester} ({self.status})"