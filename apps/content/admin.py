from django.contrib import admin, messages

from apps.core.events import record

from .models import Asset, MetricSnapshot, Post, Review


class ReviewInline(admin.TabularInline):
    model = Review
    extra = 0
    readonly_fields = ("reviewer", "decision", "comment", "created_at")


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ("slot", "version", "status", "content_type", "size", "created_at")
    list_filter = ("status",)
    readonly_fields = [f.name for f in Asset._meta.fields]
    inlines = [ReviewInline]


@admin.action(description="Check selected posts now")
def check_now(modeladmin, request, queryset):
    from django.utils import timezone

    from .services import check_post

    for post in queryset.exclude(ig_media_id=""):
        check_post(post, timezone.now())
        record(
            "post.manual_check", "Ops ran a manual post check", actor=request.user, target=post.slot.campaign
        )
    modeladmin.message_user(request, "Checked.", messages.SUCCESS)


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("slot", "method", "status", "published_at", "next_check_at", "verified_at")
    list_filter = ("status", "method")
    readonly_fields = [f.name for f in Post._meta.fields]
    actions = [check_now]


@admin.register(MetricSnapshot)
class MetricSnapshotAdmin(admin.ModelAdmin):
    list_display = ("post", "captured_at", "reach", "views", "likes", "comments")
