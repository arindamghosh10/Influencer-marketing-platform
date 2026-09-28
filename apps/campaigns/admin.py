from django.contrib import admin

from .models import Campaign, ProductBrief


class BriefInline(admin.StackedInline):
    model = ProductBrief
    extra = 0
    readonly_fields = ("version", "source", "data", "fetch_error", "confirmed_at", "confirmed_by")


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ("title", "brand", "status", "budget", "deliverable", "created_at")
    list_filter = ("status", "deliverable")
    search_fields = ("title", "brand__company_name")
    inlines = [BriefInline]
