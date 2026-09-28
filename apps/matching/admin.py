from django.contrib import admin

from .models import MatchCandidate, MatchRun


class MatchCandidateInline(admin.TabularInline):
    model = MatchCandidate
    extra = 0
    fields = ("rank", "role", "creator", "score", "creator_fee", "brand_price", "selected")
    readonly_fields = fields


@admin.register(MatchRun)
class MatchRunAdmin(admin.ModelAdmin):
    list_display = ("campaign", "created_at", "eligible_count", "shortage")
    inlines = [MatchCandidateInline]
    readonly_fields = ("campaign", "brief", "eligible_count", "excluded_counts", "shortage")
