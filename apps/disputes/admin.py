from django.contrib import admin

from .models import Dispute


@admin.register(Dispute)
class DisputeAdmin(admin.ModelAdmin):
    list_display = ("pk", "slot", "party", "category", "status", "resolution", "created_at")
    list_filter = ("status", "party", "category")
    readonly_fields = [f.name for f in Dispute._meta.fields]
