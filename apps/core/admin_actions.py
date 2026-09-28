"""Shared approve/reject actions for onboarding review in Django admin."""

from django.contrib import admin, messages

from .events import notify, record


def make_review_actions(label, dashboard_url):
    @admin.action(description=f"Approve selected {label}")
    def approve(modeladmin, request, queryset):
        count = 0
        for obj in queryset:
            obj.status = obj.Status.APPROVED
            obj.review_note = ""
            obj.save(update_fields=["status", "review_note", "updated_at"])
            record(f"{label}.approved", f"{obj} approved", actor=request.user, target=obj)
            notify(obj.user, "You're approved! 🎉", "Your profile has been approved.", url=dashboard_url)
            count += 1
        modeladmin.message_user(request, f"Approved {count}.", messages.SUCCESS)

    @admin.action(description=f"Reject selected {label} (uses the review note)")
    def reject(modeladmin, request, queryset):
        for obj in queryset:
            obj.status = obj.Status.REJECTED
            obj.save(update_fields=["status", "updated_at"])
            record(
                f"{label}.rejected",
                f"{obj} rejected",
                actor=request.user,
                target=obj,
                data={"note": obj.review_note},
            )
            notify(
                obj.user,
                "Changes needed on your profile",
                obj.review_note or "Please check your details and resubmit.",
                url=dashboard_url,
            )
        modeladmin.message_user(request, "Rejected. Users were notified.", messages.WARNING)

    return approve, reject
