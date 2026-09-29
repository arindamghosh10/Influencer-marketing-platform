from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.creators import sync
from apps.creators.models import CreatorProfile
from apps.integrations.instagram import mock
from apps.integrations.instagram.base import InstagramToken
from apps.matching.services import candidates_for


@pytest.fixture
def creator(seeded):
    c = CreatorProfile.objects.order_by("pk").first()
    CreatorProfile.objects.update(ig_synced_at=timezone.now())  # everyone fresh except `c`
    c.ig_synced_at = timezone.now() - timedelta(days=2)
    c.save()
    return c


@pytest.fixture(autouse=True)
def _clear_revoked():
    yield
    mock.REVOKED.clear()


@pytest.mark.django_db
def test_daily_sync_refreshes_stale_creators_only(creator):
    keywords = list(creator.content_keywords)
    creator.followers = 1
    creator.save()
    result = sync.sync_due()
    assert result == {"creators_synced": 1, "sync_failures": 0}
    creator.refresh_from_db()
    assert creator.followers > 1
    assert creator.ig_synced_at > timezone.now() - timedelta(minutes=1)
    assert creator.content_keywords == keywords  # mock captions don't overwrite topics
    assert sync.sync_due() == {"creators_synced": 0, "sync_failures": 0}


@pytest.mark.django_db
def test_revoked_access_asks_creator_to_reconnect_and_stops_matching(client, creator):
    mock.REVOKED.add(creator.ig_access_token)
    sync.sync_due()
    creator.refresh_from_db()
    assert creator.ig_needs_reconnect
    assert creator.user.notifications.filter(title__icontains="reconnect").exists()
    matched = {c.id: c for c in candidates_for(type("C", (), {"deliverable": "reel"})())}
    assert matched[creator.pk].ig_connected is False
    client.force_login(creator.user)
    assert "Reconnect your Instagram" in client.get(reverse("creators:dashboard")).content.decode()
    # Not retried every run while waiting for the creator.
    assert sync.sync_due()["sync_failures"] == 0
    # Reconnecting clears it.
    mock.REVOKED.clear()
    client.post(reverse("creators:onboarding_step", args=["instagram"]), {"handle": creator.ig_username})
    creator.refresh_from_db()
    assert not creator.ig_needs_reconnect and creator.ig_sync_failures == 0


@pytest.mark.django_db
def test_temporary_errors_retry_before_reconnect(creator, monkeypatch):
    from apps.integrations.instagram.base import InstagramError

    def boom(self, token):
        raise InstagramError("Instagram API error 500: try later")

    monkeypatch.setattr(mock.MockInstagram, "fetch_profile", boom)
    now = timezone.now()
    for day in range(sync.MAX_FAILURES):
        sync.sync_due(now + timedelta(days=day + 1))
        creator.refresh_from_db()
        assert creator.ig_needs_reconnect == (day + 1 >= sync.MAX_FAILURES)
    assert creator.ig_sync_failures == sync.MAX_FAILURES


@pytest.mark.django_db
def test_token_refreshed_near_expiry_and_expired_token_needs_reconnect(creator, monkeypatch):
    refreshed = []

    def refresh(self, token):
        refreshed.append(token)
        return InstagramToken(token.access_token, token.user_id, timezone.now() + timedelta(days=60))

    monkeypatch.setattr(mock.MockInstagram, "refresh_token", refresh)
    creator.ig_token_expires_at = timezone.now() + timedelta(days=3)
    creator.save()
    assert sync.sync_creator(creator)
    creator.refresh_from_db()
    assert refreshed and creator.ig_token_expires_at > timezone.now() + timedelta(days=50)

    creator.ig_token_expires_at = timezone.now() - timedelta(hours=1)
    creator.save()
    assert not sync.sync_creator(creator)
    creator.refresh_from_db()
    assert creator.ig_needs_reconnect and creator.ig_sync_error == "Access token expired"
