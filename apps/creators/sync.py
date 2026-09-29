"""Daily Instagram sync: keeps creator stats fresh and tokens alive.

Stats drive matching and pricing, so stale numbers mean bad matches. Each creator is synced at
most once a day. Long-lived tokens last 60 days and are refreshed when they're within
TOKEN_REFRESH_DAYS of expiry. When access breaks (revoked, expired, or failing repeatedly) the
creator is asked to reconnect and is left out of new matches until they do.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from apps.core.events import notify, record
from apps.integrations.instagram.base import InstagramError, InstagramToken
from apps.integrations.registry import get_provider

from .models import CreatorProfile
from .services import apply_instagram_profile

log = logging.getLogger(__name__)

SYNC_EVERY = timedelta(hours=24)
TOKEN_REFRESH_DAYS = 10
MAX_FAILURES = 3
BATCH = 200


def _needs_reconnect(creator, error):
    creator.ig_needs_reconnect = True
    creator.save(update_fields=["ig_sync_failures", "ig_sync_error", "ig_needs_reconnect", "updated_at"])
    record("creator.ig_disconnected", f"{creator} needs to reconnect Instagram: {error}", target=creator)
    notify(
        creator.user,
        "Please reconnect your Instagram",
        "We can't read your Instagram stats any more, so you won't get new offers until you "
        "reconnect. It takes a minute.",
        url=reverse("creators:onboarding_step", args=["instagram"]),
    )


def sync_creator(creator, now=None):
    """Refresh one creator. Returns True on success."""
    now = now or timezone.now()
    provider = get_provider("instagram")
    token = InstagramToken(creator.ig_access_token or "", creator.ig_user_id, creator.ig_token_expires_at)
    if token.expires_at and token.expires_at <= now:
        creator.ig_sync_error = "Access token expired"
        _needs_reconnect(creator, creator.ig_sync_error)
        return False
    try:
        if token.expires_at and token.expires_at - now < timedelta(days=TOKEN_REFRESH_DAYS):
            token = provider.refresh_token(token)
        profile = provider.fetch_profile(token)
    except InstagramError as exc:
        creator.ig_sync_failures += 1
        creator.ig_sync_error = str(exc)[:300]
        if creator.ig_sync_failures >= MAX_FAILURES or "authoriz" in str(exc).lower():
            _needs_reconnect(creator, creator.ig_sync_error)
        else:
            creator.save(update_fields=["ig_sync_failures", "ig_sync_error", "updated_at"])
        return False
    if profile.user_id != creator.ig_user_id:  # token now belongs to another account: don't mix data
        creator.ig_sync_error = "Instagram account changed"
        _needs_reconnect(creator, creator.ig_sync_error)
        return False
    # The mock's captions are random, so re-reading them would wipe the demo creators' topics.
    apply_instagram_profile(creator, token, profile, refresh_keywords=settings.INSTAGRAM_PROVIDER != "mock")
    return True


def sync_due(now=None, limit=BATCH):
    now = now or timezone.now()
    due = (
        CreatorProfile.objects.filter(ig_connected_at__isnull=False, ig_needs_reconnect=False)
        .exclude(status=CreatorProfile.Status.REJECTED)
        .filter(Q(ig_synced_at__isnull=True) | Q(ig_synced_at__lte=now - SYNC_EVERY))
        .select_related("user")
        .order_by("ig_synced_at")[:limit]
    )
    ok = failed = 0
    for creator in due:
        try:
            if sync_creator(creator, now):
                ok += 1
            else:
                failed += 1
        except Exception:  # one bad profile must not stop the batch
            log.exception("Instagram sync failed for creator %s", creator.pk)
            failed += 1
    return {"creators_synced": ok, "sync_failures": failed}
