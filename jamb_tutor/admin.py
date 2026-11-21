from datetime import timedelta

from django.contrib import admin, messages
from django.utils import timezone

from .models import (
    ChatMessage, ImportJob, JambPlan, JambProfile, JambSubscription, MockAttempt, Question, Subject, Topic,
)


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'full_name', 'sort_order')


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ('name', 'subject')
    list_filter = ('subject',)
    search_fields = ('name',)


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('short_text', 'subject', 'topic', 'correct_option', 'year')
    list_filter = ('subject', 'year')
    search_fields = ('question_text', 'topic__name')
    raw_id_fields = ('topic', 'created_by')

    @admin.display(description='Question')
    def short_text(self, obj):
        return obj.question_text[:80]


@admin.register(JambProfile)
class JambProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'combination', 'target_school', 'target_score', 'preferred_language', 'phone_e164', 'streak_count')
    list_filter = ('combination', 'preferred_language')
    search_fields = ('user__username', 'user__email', 'phone_e164', 'target_school')
    raw_id_fields = ('user', 'wa_attempt')


@admin.register(MockAttempt)
class MockAttemptAdmin(admin.ModelAdmin):
    list_display = ('user', 'subject', 'source', 'status', 'score', 'total_questions', 'started_at')
    list_filter = ('status', 'source', 'subject')
    search_fields = ('user__username',)
    raw_id_fields = ('user',)


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'channel', 'kind', 'short', 'created_at')
    list_filter = ('channel', 'role', 'kind')
    search_fields = ('user__username', 'content')
    raw_id_fields = ('user',)

    @admin.display(description='Message')
    def short(self, obj):
        return obj.content[:70]


@admin.register(JambPlan)
class JambPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'price', 'currency', 'duration_days', 'is_active')


@admin.register(JambSubscription)
class JambSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'plan', 'status', 'amount', 'paid_at', 'expires_at', 'tx_ref')
    list_filter = ('status', 'plan')
    search_fields = ('user__username', 'user__email', 'tx_ref', 'flutterwave_tx_id')
    raw_id_fields = ('user',)
    actions = ['grant_access']

    @admin.action(description="Grant access (mark paid and start the plan now)")
    def grant_access(self, request, queryset):
        """For bank transfers, scholarships and testing: no Flutterwave payment needed."""
        now = timezone.now()
        count = 0
        for sub in queryset.select_related('plan'):
            sub.status = JambSubscription.Status.PAID
            sub.paid_at = sub.paid_at or now
            sub.starts_at = now
            sub.expires_at = now + timedelta(days=sub.plan.duration_days)
            sub.save(update_fields=['status', 'paid_at', 'starts_at', 'expires_at'])
            count += 1
        self.message_user(request, f"Granted access on {count} subscription(s).", messages.SUCCESS)


@admin.register(ImportJob)
class ImportJobAdmin(admin.ModelAdmin):
    list_display = ('filename', 'kind', 'status', 'next_chunk', 'total_chunks', 'created_by', 'created_at')
    exclude = ('source_pdf',)
    readonly_fields = ('chunks', 'extracted', 'errors', 'result')
