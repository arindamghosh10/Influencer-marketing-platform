from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from apps.campaigns.models import Campaign
from apps.content import services as content
from apps.content.models import Asset
from apps.matching import engine
from apps.matching.models import MatchRun
from apps.offers import services as offers
from apps.offers.models import Offer, Slot
from apps.payments.models import Order
from apps.payments.services import mark_paid, start_order
from tests.test_matching_engine import cand, spec


def _go_live(slot, brand_user):
    upload = SimpleUploadedFile("d.mp4", b"\x00\x00\x00\x18ftypmp42 x", content_type="video/mp4")
    content.submit_draft(slot, slot.creator.user, upload, "#ad Paid partnership. Great gel!")
    content.brand_review(slot, Asset.objects.get(slot=slot), brand_user, "approved")

    class Req:
        user = slot.creator.user
        META = {"REMOTE_ADDR": "127.0.0.1"}

    content.final_approve(slot, Req(), timezone.now(), auto_publish=True)
    content.run_due(timezone.now() + timedelta(minutes=1))
    slot.refresh_from_db()
    assert slot.status == Slot.Status.LIVE


def test_engine_picks_preferred_creators_first():
    strong = cand(1, engagement_rate=9.0)
    weaker = cand(2, engagement_rate=1.0)
    s = spec(creators_wanted=1)
    assert engine.match([strong, weaker], s).recommended[0].candidate.id == 1
    s.preferred_ids = {2}
    result = engine.match([strong, weaker], s)
    assert result.recommended[0].candidate.id == 2
    assert result.recommended[0].reasons[0] == "Delivered your last campaign"


@pytest.mark.django_db
def test_run_again_copies_brief_and_prefers_previous_creator(client, paid_slot, brand_user):
    old = paid_slot.campaign
    _go_live(paid_slot, brand_user)
    client.force_login(brand_user)
    page = client.get(reverse("campaigns:detail", args=[old.pk])).content.decode()
    assert "Run again" in page
    response = client.post(reverse("campaigns:repeat", args=[old.pk]))
    new = Campaign.objects.get(repeat_of=old)
    assert response.url == reverse("campaigns:detail", args=[new.pk])
    assert new.status == Campaign.Status.BRIEF_CONFIRMED
    assert new.title == "Sun launch (repeat)"
    assert (new.budget, new.deliverable, new.must_not_say) == (old.budget, old.deliverable, old.must_not_say)
    assert new.confirmed_brief.data == old.confirmed_brief.data
    assert new.ops_approved_at is None and new.content_deadline is None
    picked = new.match_runs.first().candidates.get(selected=True)
    assert picked.creator_id == paid_slot.creator_id
    assert "Delivered your last campaign" in picked.reasons
    page = client.get(reverse("campaigns:detail", args=[new.pk])).content.decode()
    assert "Delivered your last campaign" in page and "Repeat of" in page
    # The new campaign continues through the normal flow.
    client.post(reverse("campaigns:confirm_selection", args=[new.pk]))
    client.post(reverse("campaigns:send_offers", args=[new.pk]))
    assert Offer.objects.get(slot__campaign=new).creator_id == paid_slot.creator_id


@pytest.mark.django_db
def test_run_again_needs_confirmed_brief(client, seeded, brand_user):
    campaign = Campaign.objects.create(brand=brand_user.brand_profile, title="Draft", budget=1_000_000)
    client.force_login(brand_user)
    client.post(reverse("campaigns:repeat", args=[campaign.pk]))
    assert not Campaign.objects.filter(repeat_of=campaign).exists()


@pytest.mark.django_db
def test_add_creators_to_running_campaign(client, paid_slot, brand_user):
    campaign = paid_slot.campaign
    budget_before = campaign.budget
    client.force_login(brand_user)
    url = reverse("campaigns:add_creators", args=[campaign.pk])
    assert client.get(url).status_code == 200
    client.post(url, {"count": 2, "budget_rupees": 100000})
    run = campaign.match_runs.first()
    assert run.is_pending_top_up and run.budget == 100000 * 100
    chosen = list(run.candidates.filter(selected=True))
    assert 1 <= len(chosen) <= 2
    all_ids = set(run.candidates.values_list("creator_id", flat=True))
    assert paid_slot.creator_id not in all_ids  # already in the campaign
    page = client.get(url).content.decode()
    for c in chosen:
        assert c.creator.display_name in page
    detail = client.get(reverse("campaigns:detail", args=[campaign.pk])).content.decode()
    assert "haven't sent their offers yet" in detail

    # Toggling works on the pending top-up (plain post falls back to the add page).
    toggled = client.post(reverse("campaigns:toggle_candidate", args=[campaign.pk, chosen[0].pk]))
    assert toggled.url == url
    chosen[0].refresh_from_db()
    assert not chosen[0].selected
    client.post(reverse("campaigns:toggle_candidate", args=[campaign.pk, chosen[0].pk]))

    client.post(reverse("campaigns:send_top_up", args=[campaign.pk]))
    run.refresh_from_db()
    campaign.refresh_from_db()
    assert run.sent_at is not None
    assert campaign.budget == budget_before + run.budget
    new_slots = list(campaign.slots.exclude(pk=paid_slot.pk).order_by("position"))
    assert [s.position for s in new_slots] == list(range(2, 2 + len(chosen)))
    assert all(s.status == Slot.Status.OFFERING for s in new_slots)

    # Accepting and paying bills only the new creator, on a second invoice.
    offer = Offer.objects.get(slot=new_slots[0], status=Offer.Status.PENDING)
    offers.accept(offer, agreement=None)
    order = start_order(campaign)
    assert list(order.slots.values_list("pk", flat=True)) == [new_slots[0].pk]
    mark_paid(order.pk, "pay_topup")
    new_slots[0].refresh_from_db()
    assert new_slots[0].status == Slot.Status.CONFIRMED
    assert campaign.orders.filter(status=Order.Status.PAID).count() == 2
    # Sending again does nothing.
    client.post(reverse("campaigns:send_top_up", args=[campaign.pk]))
    assert campaign.slots.count() == 1 + len(chosen)


@pytest.mark.django_db
def test_top_up_over_budget_and_discard(client, paid_slot, brand_user):
    campaign = paid_slot.campaign
    client.force_login(brand_user)
    client.post(reverse("campaigns:add_creators", args=[campaign.pk]), {"count": 1, "budget_rupees": 100000})
    run = campaign.match_runs.first()
    run.budget = 1  # pretend the brand lowered it
    run.save()
    with pytest.raises(offers.OfferError):
        offers.send_top_up(campaign, brand_user)
    client.post(reverse("campaigns:discard_top_up", args=[campaign.pk]))
    assert not MatchRun.objects.filter(pk=run.pk).exists()
    assert campaign.slots.count() == 1


@pytest.mark.django_db
def test_unsent_top_up_is_not_used_for_backups(client, paid_slot, brand_user):
    campaign = paid_slot.campaign
    initial = campaign.match_runs.first()
    client.force_login(brand_user)
    client.post(reverse("campaigns:add_creators", args=[campaign.pk]), {"count": 1, "budget_rupees": 100000})
    assert campaign.match_runs.first().is_pending_top_up
    assert offers.backup_run(campaign) == initial


@pytest.mark.django_db
def test_add_creators_only_while_running_and_only_own(client, paid_slot, brand_user, django_user_model):
    campaign = paid_slot.campaign
    other = django_user_model.objects.create_user("other@test.local", "pw-Strong-123", role="brand")
    from apps.brands.models import BrandProfile

    BrandProfile.objects.create(user=other, company_name="Other", status=BrandProfile.Status.APPROVED)
    client.force_login(other)
    assert client.get(reverse("campaigns:add_creators", args=[campaign.pk])).status_code == 404
    assert client.post(reverse("campaigns:repeat", args=[campaign.pk])).status_code == 404
    campaign.status = Campaign.Status.COMPLETED
    campaign.save()
    client.force_login(brand_user)
    response = client.post(
        reverse("campaigns:add_creators", args=[campaign.pk]), {"count": 1, "budget_rupees": 100000}
    )
    assert response.status_code == 302
    assert not campaign.match_runs.filter(purpose=MatchRun.Purpose.TOP_UP).exists()
