import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.core import ops_health
from apps.core.models import JobHeartbeat
from apps.creators.models import CreatorProfile
from apps.offers.models import Slot
from apps.offers.services import process_deadlines


@pytest.mark.django_db
def test_funnel_counts_and_margin(paid_slot):
    f = ops_health.funnel()
    steps = {s["label"]: s["count"] for s in f["steps"]}
    assert steps["Campaigns created"] == 1 and steps["Paid"] == 1 and steps["Completed"] == 0
    assert f["gmv"] == paid_slot.brand_price
    assert f["margin"] == paid_slot.brand_price - paid_slot.creator_fee
    assert f["offers"]["acceptance_pct"] == 100


@pytest.mark.django_db
def test_stuck_items_and_integration_health(paid_slot):
    assert not ops_health.stuck()
    health = {i["name"]: i for i in ops_health.integrations()}
    assert not health["Scheduler"]["ok"] and health["Scheduler"]["detail"] == "never ran"
    process_deadlines()
    assert JobHeartbeat.objects.get(name="process_deadlines")
    assert {i["name"]: i for i in ops_health.integrations()}["Scheduler"]["ok"]

    paid_slot.status = Slot.Status.ON_HOLD
    paid_slot.save()
    CreatorProfile.objects.filter(pk=paid_slot.creator_id).update(ig_needs_reconnect=True)
    titles = [g["title"] for g in ops_health.stuck()]
    assert "Posts on hold (missing or edited)" in titles
    assert "Creators in active campaigns who must reconnect Instagram" in titles
    assert not {i["name"]: i for i in ops_health.integrations()}["Instagram"]["ok"]


@pytest.mark.django_db
def test_ops_page_renders_new_sections(client, paid_slot):
    client.force_login(User.objects.get(email="ops@demo.local"))
    page = client.get(reverse("core:ops")).content.decode()
    for text in ("Campaign funnel", "Integrations", "Needs attention", "Margin"):
        assert text in page
    # Brands and creators can't open the ops page.
    client.force_login(paid_slot.campaign.brand.user)
    assert client.get(reverse("core:ops")).status_code in (302, 403)
