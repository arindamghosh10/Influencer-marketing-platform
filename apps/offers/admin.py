from django.contrib import admin

from .models import Offer, Slot


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
    readonly_fields = ("campaign", "position", "creator", "creator_fee", "brand_price", "order")


@admin.register(Offer)
class OfferAdmin(admin.ModelAdmin):
    list_display = ("slot", "creator", "status", "creator_fee", "brand_price", "expires_at", "decline_reason")
    list_filter = ("status", "decline_reason")
    search_fields = ("creator__display_name", "slot__campaign__title")
    readonly_fields = [f.name for f in Offer._meta.fields]
