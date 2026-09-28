from django.contrib import admin

from apps.core.admin_actions import make_review_actions

from .models import BrandProfile

approve, reject = make_review_actions("brand", "/brand/")


@admin.register(BrandProfile)
class BrandProfileAdmin(admin.ModelAdmin):
    list_display = ("company_name", "user", "gstin", "domain", "domain_verified_at", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("company_name", "user__email", "gstin")
    filter_horizontal = ("niches",)
    actions = [approve, reject]
    readonly_fields = ("domain_verification_token", "domain_verified_at")
