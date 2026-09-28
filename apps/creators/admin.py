from django.contrib import admin, messages

from apps.core.admin_actions import make_review_actions
from apps.core.events import record

from .models import CreatorProfile

approve, reject = make_review_actions("creator", "/creator/")


@admin.action(description="Mark KYC verified")
def verify_kyc(modeladmin, request, queryset):
    for creator in queryset:
        creator.kyc_status = CreatorProfile.KycStatus.VERIFIED
        creator.save(update_fields=["kyc_status", "updated_at"])
        record("creator.kyc_verified", f"{creator} KYC verified", actor=request.user, target=creator)
    modeladmin.message_user(request, "KYC marked verified.", messages.SUCCESS)


@admin.register(CreatorProfile)
class CreatorProfileAdmin(admin.ModelAdmin):
    list_display = (
        "display_name",
        "ig_username",
        "followers",
        "engagement_rate",
        "authenticity_score",
        "primary_niche",
        "kyc_status",
        "status",
    )
    list_filter = ("status", "kyc_status", "primary_niche__parent")
    search_fields = ("display_name", "ig_username", "user__email")
    filter_horizontal = ("niches",)
    actions = [approve, reject, verify_kyc]
    exclude = ("ig_access_token", "pan", "bank_account_number")
    readonly_fields = ("pan_last4", "bank_account_last4", "ig_user_id", "ig_connected_at", "ig_synced_at")
