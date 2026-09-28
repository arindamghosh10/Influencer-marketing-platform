from django.contrib import admin

from .models import Agreement, ConsentEvent


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Agreement)
class AgreementAdmin(ReadOnlyAdmin):
    list_display = ("signed_at", "user", "kind", "version", "campaign", "otp_verified")
    list_filter = ("kind", "version")
    search_fields = ("user__email", "sha256")


@admin.register(ConsentEvent)
class ConsentEventAdmin(ReadOnlyAdmin):
    list_display = ("created_at", "user", "scope", "action", "campaign")
    list_filter = ("scope", "action")
    search_fields = ("user__email",)
