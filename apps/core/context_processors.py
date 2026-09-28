from django.conf import settings


def platform(request):
    unread = 0
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        unread = user.notifications.filter(read_at__isnull=True).count()
    return {"PLATFORM_NAME": settings.PLATFORM_NAME, "unread_notifications": unread}
