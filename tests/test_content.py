from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from apps.campaigns.models import Campaign
from apps.content import services
from apps.content.models import Asset, Post
from apps.contracts.models import ConsentEvent
from apps.integrations.instagram import mock as ig_mock
from apps.integrations.instagram.base import InstagramError
from apps.offers.models import Slot
from apps.payments.models import Payout

CAPTION = "Loving this sunscreen! #ad Paid partnership with GlowLeaf"


def video(name="draft.mp4", content=b"\x00\x00\x00\x18ftypmp42 fake video bytes"):
    return SimpleUploadedFile(name, content, content_type="video/mp4")


def _submit(client, slot, caption=CAPTION, file=None):
    client.force_login(slot.creator.user)
    return client.post(
        reverse("content:submit_draft", args=[slot.pk]), {"caption": caption, "file": file or video()}
    )


def _grant_publish(slot):
    ConsentEvent.objects.create(
        user=slot.creator.user, scope="instagram_publish", action=ConsentEvent.Action.GRANTED
    )


@pytest.mark.django_db
def test_workspace_shows_brief_and_script_helper(client, paid_slot):
    client.force_login(paid_slot.creator.user)
    page = client.get(reverse("content:workspace", args=[paid_slot.pk])).content.decode()
    assert "Upload your draft" in page and "Hook ideas" in page
    paid_slot.refresh_from_db()
    assert paid_slot.creator_brief["hooks"]


@pytest.mark.django_db
def test_caption_without_disclosure_is_blocked(client, paid_slot):
    _submit(client, paid_slot, caption="Loving this sunscreen!")
    paid_slot.refresh_from_db()
    assert paid_slot.status == Slot.Status.CONFIRMED and not Asset.objects.exists()


@pytest.mark.django_db
def test_forbidden_phrase_and_wrong_file_type_are_blocked(client, paid_slot):
    _submit(client, paid_slot, caption=CAPTION + " it cures acne")
    _submit(client, paid_slot, file=SimpleUploadedFile("a.pdf", b"%PDF", content_type="application/pdf"))
    assert not Asset.objects.exists()


@pytest.mark.django_db
def test_review_revisions_and_final_approval_publish_verify(client, paid_slot, brand_user, settings):
    slot = paid_slot
    campaign = slot.campaign
    _submit(client, slot)
    slot.refresh_from_db()
    asset = Asset.objects.get(slot=slot)
    assert slot.status == Slot.Status.IN_REVIEW and asset.version == 1 and len(asset.sha256) == 64

    # Brand requests changes twice, then can't a third time.
    client.force_login(brand_user)
    review_url = reverse("content:review_action", args=[campaign.pk, slot.pk])
    for round_ in (1, 2):
        client.post(review_url, {"decision": "changes", "comment": f"Please show the texture ({round_})"})
        slot.refresh_from_db()
        assert slot.status == Slot.Status.CHANGES_REQUESTED and slot.revisions_used == round_
        _submit(client, slot)
        client.force_login(brand_user)
    client.post(review_url, {"decision": "changes", "comment": "One more"})
    slot.refresh_from_db()
    assert slot.status == Slot.Status.IN_REVIEW and slot.revisions_used == 2
    assert Asset.objects.filter(slot=slot, status=Asset.Status.SUPERSEDED).count() == 2

    client.post(review_url, {"decision": "approved"})
    slot.refresh_from_db()
    assert slot.status == Slot.Status.APPROVED

    # Creator's final OK with auto-publish records consent bound to the exact file.
    _grant_publish(slot)
    client.force_login(slot.creator.user)
    when = (timezone.localtime() + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M")
    client.post(
        reverse("content:final_approve", args=[slot.pk]),
        {"publish_at": when, "auto_publish": "on", "confirm": "on"},
    )
    slot.refresh_from_db()
    final = Asset.objects.get(slot=slot, status=Asset.Status.FINAL)
    assert slot.status == Slot.Status.SCHEDULED
    assert ConsentEvent.objects.filter(
        user=slot.creator.user, scope="instagram_publish", campaign=campaign, asset_sha256=final.sha256
    ).exists()

    # Nothing publishes before its time; then the scheduled job publishes it.
    services.run_due(timezone.now())
    assert Post.objects.get(slot=slot).status == Post.Status.SCHEDULED
    services.run_due(timezone.now() + timedelta(minutes=10))
    post = Post.objects.get(slot=slot)
    slot.refresh_from_db()
    assert post.status == Post.Status.LIVE and post.ig_media_id and slot.status == Slot.Status.LIVE
    assert post.snapshots.exists()

    # Daily checks: payout stays held until the verification period passes.
    payout = Payout.objects.get(slot=slot)
    services.run_due(post.published_at + timedelta(days=1, minutes=1))
    payout.refresh_from_db()
    assert payout.status == Payout.Status.HELD
    for day in range(2, settings.VERIFICATION_DAYS + 2):
        services.run_due(post.published_at + timedelta(days=day, minutes=1))
    post.refresh_from_db()
    payout.refresh_from_db()
    slot.refresh_from_db()
    campaign.refresh_from_db()
    assert post.status == Post.Status.VERIFIED and slot.status == Slot.Status.VERIFIED
    assert payout.status == Payout.Status.RELEASABLE
    assert campaign.status == Campaign.Status.COMPLETED

    # Brand sees results on the campaign page.
    client.force_login(brand_user)
    page = client.get(reverse("campaigns:detail", args=[campaign.pk])).content.decode()
    assert "Posts live" in page and "View post" in page


@pytest.mark.django_db
def test_brand_review_times_out_to_auto_approval(client, paid_slot):
    _submit(client, paid_slot)
    result = services.run_due(timezone.now() + timedelta(hours=73))
    paid_slot.refresh_from_db()
    assert result["auto_approved"] == 1 and paid_slot.status == Slot.Status.APPROVED
    assert Asset.objects.get(slot=paid_slot).reviews.get().decision == "auto_approved"


@pytest.mark.django_db
def test_self_post_when_publish_consent_revoked(client, paid_slot):
    slot = paid_slot
    # The creator switched off "publish on my behalf" in the consent centre.
    client.force_login(slot.creator.user)
    client.post(reverse("contracts:toggle_consent", args=["instagram_publish"]), {"grant": "0"})
    _submit(client, slot)
    services.brand_review(slot, Asset.objects.get(slot=slot), None, "approved")
    client.force_login(slot.creator.user)
    when = timezone.localtime().strftime("%Y-%m-%dT%H:%M")
    client.post(
        reverse("content:final_approve", args=[slot.pk]),
        {"publish_at": when, "auto_publish": "on", "confirm": "on"},
    )
    slot.refresh_from_db()
    assert slot.status == Slot.Status.SELF_POST  # consent withdrawn → creator posts
    client.post(reverse("content:self_post", args=[slot.pk]), {"permalink": "https://example.com/x"})
    slot.refresh_from_db()
    assert slot.status == Slot.Status.SELF_POST
    client.post(
        reverse("content:self_post", args=[slot.pk]),
        {"permalink": "https://www.instagram.com/reel/mock1700000000xabc/"},
    )
    slot.refresh_from_db()
    assert slot.status == Slot.Status.LIVE and slot.post.method == Post.Method.SELF


@pytest.mark.django_db
def test_publish_failures_fall_back_to_self_post(client, paid_slot, monkeypatch):
    slot = paid_slot
    _submit(client, slot)
    services.brand_review(slot, Asset.objects.get(slot=slot), None, "approved")
    _grant_publish(slot)

    def fail(*args, **kwargs):
        raise InstagramError("rate limited")

    monkeypatch.setattr(ig_mock.MockInstagram, "publish", fail)
    client.force_login(slot.creator.user)
    client.post(
        reverse("content:final_approve", args=[slot.pk]),
        {
            "publish_at": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
            "auto_publish": "on",
            "confirm": "on",
        },
    )
    now = timezone.now()
    for i in range(services.PUBLISH_MAX_ATTEMPTS):
        services.run_due(now + timedelta(hours=i + 1))
    post = Post.objects.get(slot=slot)
    slot.refresh_from_db()
    assert post.status == Post.Status.AWAITING_SELF_POST and "rate limited" in post.last_error
    assert slot.status == Slot.Status.SELF_POST


@pytest.mark.django_db
def test_removed_post_puts_payout_on_hold_and_restoring_resumes(client, paid_slot):
    slot = paid_slot
    _submit(client, slot)
    services.brand_review(slot, Asset.objects.get(slot=slot), None, "approved")
    _grant_publish(slot)
    client.force_login(slot.creator.user)
    client.post(
        reverse("content:final_approve", args=[slot.pk]),
        {
            "publish_at": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
            "auto_publish": "on",
            "confirm": "on",
        },
    )
    services.run_due(timezone.now() + timedelta(minutes=1))
    post = Post.objects.get(slot=slot)
    ig_mock.REMOVED.add(post.ig_media_id)
    try:
        services.run_due(post.published_at + timedelta(days=1, minutes=1))
        post.refresh_from_db()
        slot.refresh_from_db()
        assert post.status == Post.Status.MISSING and slot.status == Slot.Status.ON_HOLD
        # Still missing after the verification period: payout must not be released.
        services.run_due(post.published_at + timedelta(days=8))
        assert Payout.objects.get(slot=slot).status == Payout.Status.HELD
    finally:
        ig_mock.REMOVED.discard(post.ig_media_id)
    services.run_due(post.published_at + timedelta(days=9))
    post.refresh_from_db()
    assert post.status == Post.Status.VERIFIED
    assert Payout.objects.get(slot=slot).status == Payout.Status.RELEASABLE


@pytest.mark.django_db
def test_file_access_is_restricted(client, paid_slot, creator_user, brand_user):
    _submit(client, paid_slot)
    asset = Asset.objects.get(slot=paid_slot)
    url = reverse("content:asset_file", args=[asset.pk])
    assert client.get(url).status_code == 200  # the creator
    client.force_login(brand_user)
    assert client.get(url).status_code == 200  # the campaign's brand
    client.force_login(creator_user)
    assert client.get(url).status_code == 403  # another creator
    client.logout()
    assert client.get(url).status_code == 404
    # Public link only works for final assets and valid signatures.
    token_url = services.public_asset_url(asset).split("://", 1)[1].split("/", 1)[1]
    assert client.get("/" + token_url).status_code == 404  # not final yet
    asset.status = Asset.Status.FINAL
    asset.save()
    assert client.get("/" + token_url).status_code == 200
    assert client.get(reverse("content:public_asset", args=["forged"])).status_code == 404


@pytest.mark.django_db
def test_other_brand_cannot_review(client, paid_slot):
    from apps.accounts.models import User
    from apps.brands.models import BrandProfile

    other = User.objects.create_user("other@brand.local", "pw-Strong-123", role=User.Role.BRAND)
    BrandProfile.objects.create(user=other, company_name="Other")
    client.force_login(other)
    url = reverse("content:review", args=[paid_slot.campaign_id, paid_slot.pk])
    assert client.get(url).status_code == 404
