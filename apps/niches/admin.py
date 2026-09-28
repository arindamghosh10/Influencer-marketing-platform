from django.contrib import admin

from .models import Niche


@admin.register(Niche)
class NicheAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "parent", "sort_order")
    list_filter = ("parent",)
    search_fields = ("name", "slug")
