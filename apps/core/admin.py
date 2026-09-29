from django.contrib import admin
from django.utils import timezone

from .models import DataRequest, Event, Notification


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "verb", "message", "actor")
    list_filter = ("verb",)
    search_fields = ("message", "verb")
    readonly_fields = [f.name for f in Event._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "title", "read_at")


@admin.register(DataRequest)
class DataRequestAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "status", "completed_at")
    list_filter = ("status",)
    search_fields = ("user__email",)
    readonly_fields = ("user", "reason", "created_at", "completed_at")

    def save_model(self, request, obj, form, change):
        if obj.status != DataRequest.Status.OPEN and obj.completed_at is None:
            obj.completed_at = timezone.now()
        super().save_model(request, obj, form, change)
