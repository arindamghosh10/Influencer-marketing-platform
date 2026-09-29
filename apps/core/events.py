"""Helpers to record audit events and notify users."""

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.mail import send_mail

from .models import Event, Notification


def record(verb, message, *, actor=None, target=None, data=None, request=None):
    event = Event(verb=verb, message=message[:500], data=data or {}, actor=actor)
    if target is not None:
        event.target_type = ContentType.objects.get_for_model(target)
        event.target_id = str(target.pk)
    if request is not None:
        event.ip_address = client_ip(request)
    event.save()
    return event


def events_for(target):
    return Event.objects.filter(
        target_type=ContentType.objects.get_for_model(target), target_id=str(target.pk)
    ).select_related("actor")


def notify(user, title, body="", url="", email=True):
    Notification.objects.create(user=user, title=title, body=body, url=url)
    if email and user.email:
        link = f"{settings.SITE_URL.rstrip('/')}{url}" if url.startswith("/") else url
        send_mail(title, f"{body}\n\n{link}".strip(), None, [user.email], fail_silently=True)


def client_ip(request):
    # Behind Caddy/Cloudflare the real client IP is the first X-Forwarded-For entry.
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")
