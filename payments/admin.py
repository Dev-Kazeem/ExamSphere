from django.contrib import admin, messages

from .models import Semester, SemesterSubscription
from .services import reconcile

# Register your models here.
admin.site.register(Semester)

@admin.register(SemesterSubscription)
class SemesterSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("student", "semester", "status", "amount", "tx_ref", "paid_at")
    list_filter = ("status", "semester")
    search_fields = ("student__username", "student__email", "tx_ref", "flutterwave_tx_id")
    actions = ["recheck_with_flutterwave"]

    @admin.action(description="Re-check selected payments with Flutterwave")
    def recheck_with_flutterwave(self, request, queryset):
        pending = queryset.exclude(status=SemesterSubscription.Status.PAID).select_related("semester")
        fixed = sum(1 for sub in pending if reconcile(sub))
        self.message_user(
            request,
            f"{fixed} payment(s) confirmed. The rest have no successful payment on Flutterwave.",
            messages.SUCCESS if fixed else messages.WARNING,
        )