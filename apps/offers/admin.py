from django import forms
from django.contrib import admin, messages
from django.contrib.admin.helpers import ActionForm

from .models import Offer, Slot


class ReasonForm(ActionForm):
    reason = forms.CharField(required=False, label="Reason (shown to brand and creator)")


@admin.action(description="Cancel paid slot and refund the brand (before content approval)")
def cancel_and_refund(modeladmin, request, queryset):
    from apps.payments.refunds import RefundError, cancel_paid_slot

    reason = request.POST.get("reason", "").strip()
    if not reason:
        modeladmin.message_user(request, "Enter a reason first.", messages.ERROR)
        return
    for slot in queryset:
        try:
            refund = cancel_paid_slot(slot, reason, actor=request.user)
            modeladmin.message_user(
                request, f"{slot}: refunded ({refund.credit_note_number}).", messages.SUCCESS
            )
        except RefundError as exc:
            modeladmin.message_user(request, f"{slot}: {exc}", messages.ERROR)


class OfferInline(admin.TabularInline):
    model = Offer
    extra = 0
    fields = (
        "creator",
        "status",
        "creator_fee",
        "brand_price",
        "expires_at",
        "responded_at",
        "decline_reason",
    )
    readonly_fields = fields


@admin.register(Slot)
class SlotAdmin(admin.ModelAdmin):
    list_display = (
        "campaign",
        "position",
        "status",
        "creator",
        "creator_fee",
        "brand_price",
        "payment_due_at",
    )
    list_filter = ("status",)
    search_fields = ("campaign__title", "creator__display_name")
    inlines = [OfferInline]
    action_form = ReasonForm
    actions = [cancel_and_refund]
    readonly_fields = ("campaign", "position", "creator", "creator_fee", "brand_price", "order")


@admin.register(Offer)
class OfferAdmin(admin.ModelAdmin):
    list_display = ("slot", "creator", "status", "creator_fee", "brand_price", "expires_at", "decline_reason")
    list_filter = ("status", "decline_reason")
    search_fields = ("creator__display_name", "slot__campaign__title")
    readonly_fields = [f.name for f in Offer._meta.fields]
