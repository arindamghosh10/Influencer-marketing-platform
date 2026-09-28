from django.contrib import admin, messages
from django.urls import reverse
from django.utils import timezone

from apps.core.events import notify, record

from .models import Campaign, ProductBrief


class BriefInline(admin.StackedInline):
    model = ProductBrief
    extra = 0
    readonly_fields = ("version", "source", "data", "fetch_error", "confirmed_at", "confirmed_by")


@admin.action(description="Approve sensitive-category campaign (allows offers)")
def approve_campaign(modeladmin, request, queryset):
    for campaign in queryset.filter(ops_approved_at__isnull=True):
        campaign.ops_approved_at = timezone.now()
        campaign.ops_approved_by = request.user
        campaign.save(update_fields=["ops_approved_at", "ops_approved_by", "updated_at"])
        record("campaign.ops_approved", "Campaign approved by ops", actor=request.user, target=campaign)
        notify(
            campaign.brand.user,
            f"'{campaign.title}' is approved",
            "You can now send offers to your selected creators.",
            url=reverse("campaigns:detail", args=[campaign.pk]),
        )
    modeladmin.message_user(request, "Approved.", messages.SUCCESS)


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ("title", "brand", "status", "budget", "deliverable", "ops_approved_at", "created_at")
    list_filter = ("status", "deliverable")
    search_fields = ("title", "brand__company_name")
    inlines = [BriefInline]
    actions = [approve_campaign]
    readonly_fields = ("margin_bps", "ops_approved_at", "ops_approved_by")
