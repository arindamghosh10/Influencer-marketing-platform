from django.contrib import admin

from .models import Event, Notification


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
