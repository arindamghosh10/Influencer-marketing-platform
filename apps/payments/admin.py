from django import forms
from django.contrib import admin, messages
from django.contrib.admin.helpers import ActionForm
from django.utils import timezone

from apps.core.events import notify, record

from .models import Order, Payout, WebhookEvent


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("pk", "campaign", "brand", "status", "total", "invoice_number", "paid_at")
    list_filter = ("status", "provider")
    search_fields = ("invoice_number", "provider_order_id", "provider_payment_id", "brand__company_name")
    readonly_fields = [f.name for f in Order._meta.fields]


class MarkPaidForm(ActionForm):
    utr = forms.CharField(required=False, label="UTR (bank reference)")


@admin.action(description="Mark as paid (enter the UTR above)")
def mark_paid(modeladmin, request, queryset):
    utr = request.POST.get("utr", "").strip()
    if not utr:
        modeladmin.message_user(request, "Enter the bank UTR reference first.", messages.ERROR)
        return
    done = 0
    for payout in queryset.filter(status=Payout.Status.RELEASABLE):
        payout.status = Payout.Status.PAID
        payout.utr = utr
        payout.paid_at = timezone.now()
        payout.save(update_fields=["status", "utr", "paid_at", "updated_at"])
        record("payout.paid", f"Paid {payout.creator} (UTR {utr})", actor=request.user, target=payout)
        notify(payout.creator.user, "You've been paid 🎉", f"Transfer reference (UTR): {utr}")
        done += 1
    modeladmin.message_user(request, f"Marked {done} payout(s) paid. Only 'ready to pay' payouts change.")


@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    list_display = ("creator", "slot", "status", "gross", "gst", "tds", "net", "utr", "paid_at")
    list_filter = ("status",)
    search_fields = ("creator__display_name", "utr")
    readonly_fields = ("slot", "creator", "gross", "gst", "tds", "tds_rate_bps", "net", "paid_at")
    action_form = MarkPaidForm
    actions = [mark_paid]


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ("received_at", "provider", "event_type", "event_id")
    readonly_fields = [f.name for f in WebhookEvent._meta.fields]
