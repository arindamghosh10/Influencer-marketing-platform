import re

import pytest
from django.core import mail
from django.urls import reverse

from apps.campaigns.models import Campaign
from apps.contracts.models import Agreement, ConsentEvent
from apps.creators.models import CreatorProfile
from apps.matching.models import MatchCandidate
from apps.niches.models import Niche


def _sign_with_emailed_code(client):
    """Complete the sign page and OTP step using the code from the outgoing email."""
    resp = client.post(reverse("contracts:sign"), {"signed_name": "Asha Rao", "accept": "on"})
    assert resp.status_code == 302
    code = re.search(r"\b(\d{6})\b", mail.outbox[-1].subject).group(1)
    return client.post(reverse("contracts:verify"), {"code": code})


@pytest.mark.django_db
def test_signup_redirects_by_role(client):
    resp = client.post(
        reverse("accounts:signup"),
        {
            "role": "creator",
            "name": "Asha Rao",
            "email": "Asha@Example.com",
            "password": "pw-Strong-123",
        },
    )
    assert resp.status_code == 302
    resp = client.get(reverse("core:home"))
    assert resp.url == reverse("creators:dashboard")


@pytest.mark.django_db
def test_roles_cannot_open_each_others_pages(client, creator_user, brand_user):
    client.force_login(creator_user)
    assert client.get(reverse("brands:dashboard")).status_code == 403
    client.force_login(brand_user)
    assert client.get(reverse("creators:dashboard")).status_code == 403
    assert client.get(reverse("core:ops")).status_code == 403


@pytest.mark.django_db
def test_creator_onboarding_end_to_end(client, creator_user):
    client.force_login(creator_user)
    niche = Niche.objects.get(slug="sun-care")
    resp = client.post(
        reverse("creators:onboarding_step", args=["profile"]),
        {
            "display_name": "Asha",
            "gender": "female",
            "city": "Pune",
            "bio": "Skincare",
            "languages_csv": "Hindi, English",
            "primary_niche": niche.pk,
        },
    )
    assert resp.status_code == 302
    resp = client.post(reverse("creators:onboarding_step", args=["instagram"]), {"handle": "@asha.skin"})
    assert resp.status_code == 302
    creator = CreatorProfile.objects.get(user=creator_user)
    assert creator.ig_connected and creator.followers > 0 and creator.authenticity_score > 0

    client.post(
        reverse("creators:onboarding_step", args=["rates"]),
        {
            "reel_rupees": 4000,
            "story_rupees": 1500,
            "post_rupees": 2500,
            "red_lines": ["alcohol"],
            "max_active_campaigns": 3,
        },
    )
    creator.refresh_from_db()
    assert creator.rate_reel == 400_000 and creator.red_lines == ["alcohol"]

    from django.core.files.uploadedfile import SimpleUploadedFile

    resp = client.post(
        reverse("creators:onboarding_step", args=["kyc"]),
        {
            "legal_name": "Asha Rao",
            "pan": "abcde1234f",
            "gstin": "",
            "bank_account_name": "Asha Rao",
            "bank_account_number": "123456789012",
            "bank_account_number_confirm": "123456789012",
            "bank_ifsc": "hdfc0001234",
            "kyc_document": SimpleUploadedFile("pan.pdf", b"%PDF-1.4 test", content_type="application/pdf"),
        },
    )
    assert resp.status_code == 302
    creator.refresh_from_db()
    assert creator.kyc_status == "pending" and creator.pan == "ABCDE1234F"
    assert creator.bank_account_last4 == "9012"

    client.post(reverse("creators:onboarding_step", args=["agreement"]))
    resp = _sign_with_emailed_code(client)
    assert resp.url == reverse("creators:submit")
    client.get(resp.url)
    creator.refresh_from_db()
    assert creator.status == CreatorProfile.Status.PENDING_REVIEW

    agreement = Agreement.objects.get(user=creator_user)
    assert agreement.otp_verified and len(agreement.sha256) == 64 and "Asha Rao" in agreement.body
    scopes = set(ConsentEvent.objects.filter(user=creator_user).values_list("scope", flat=True))
    assert {"terms", "data_processing", "instagram_publish"} <= scopes


@pytest.mark.django_db
def test_wrong_otp_is_rejected_and_limited(client, creator_user):
    from apps.contracts import services
    from apps.contracts.models import AgreementKind

    creator_user.creator_profile = CreatorProfile.objects.create(user=creator_user, display_name="A")
    client.force_login(creator_user)
    client.post(reverse("creators:onboarding_step", args=["agreement"]))
    client.post(reverse("contracts:sign"), {"signed_name": "A", "accept": "on"})
    for _ in range(services.OTP_MAX_ATTEMPTS):
        resp = client.post(reverse("contracts:verify"), {"code": "000000"})
        assert resp.status_code == 200
    assert not Agreement.objects.filter(user=creator_user, kind=AgreementKind.CREATOR_PLATFORM).exists()


@pytest.mark.django_db
def test_campaign_flow_and_price_separation(client, seeded, brand_user):
    client.force_login(brand_user)
    resp = client.post(
        reverse("campaigns:create"),
        {
            "title": "Sunscreen launch",
            "product_url": "",
            "product_notes": "SunShield SPF 50 gel sunscreen for oily skin. Clinically proven formula.",
            "objective": "awareness",
            "deliverable": "reel",
            "budget_rupees": 150000,
            "target_gender": "any",
            "content_mode": "creator_made",
            "usage_rights_days": 90,
            "paid_ads_allowed": "on",
        },
    )
    assert resp.status_code == 302
    campaign = Campaign.objects.get(title="Sunscreen launch")
    assert campaign.status == Campaign.Status.BRIEF_READY
    brief = campaign.current_brief
    assert "sun-care" in brief.data["niche_slugs"] and brief.data["risky_claims"]

    # Flagged claims must be acknowledged before confirming.
    client.post(reverse("campaigns:confirm_brief", args=[campaign.pk]))
    campaign.refresh_from_db()
    assert campaign.status == Campaign.Status.BRIEF_READY
    client.post(reverse("campaigns:confirm_brief", args=[campaign.pk]), {"claims_ack": "1"})
    campaign.refresh_from_db()
    assert campaign.status == Campaign.Status.BRIEF_CONFIRMED

    run = campaign.match_runs.first()
    recommended = list(run.candidates.filter(role=MatchCandidate.Role.RECOMMENDED))
    assert recommended
    assert sum(c.brand_price for c in recommended) <= campaign.budget
    for c in recommended:
        assert c.brand_price >= c.creator_fee * 2  # 50% margin

    # The brand page must never contain any creator fee amount.
    from apps.core.money import format_inr

    page = client.get(reverse("campaigns:detail", args=[campaign.pk])).content.decode()
    for c in run.candidates.all():
        assert format_inr(c.brand_price) in page
        if format_inr(c.creator_fee) != format_inr(c.brand_price):
            assert format_inr(c.creator_fee) + "</span>" not in page

    first = recommended[0]
    resp = client.post(
        reverse("campaigns:toggle_candidate", args=[campaign.pk, first.pk]), HTTP_HX_REQUEST="true"
    )
    assert resp.status_code == 200 and b"selection-summary" in resp.content
    first.refresh_from_db()
    assert not first.selected

    client.post(reverse("campaigns:confirm_selection", args=[campaign.pk]))
    campaign.refresh_from_db()
    assert campaign.status == Campaign.Status.SHORTLISTED


@pytest.mark.django_db
def test_brand_cannot_see_other_brands_campaigns(client, brand_user, seeded):
    from apps.accounts.models import User
    from apps.brands.models import BrandProfile

    other = BrandProfile.objects.get(user__email="brand@demo.local")
    campaign = Campaign.objects.create(brand=other, title="Secret", budget=1_000_000)
    client.force_login(brand_user)
    assert client.get(reverse("campaigns:detail", args=[campaign.pk])).status_code == 404
    assert User.objects.count() > 2


@pytest.mark.django_db
def test_blocked_category_cannot_be_confirmed(client, seeded, brand_user):
    client.force_login(brand_user)
    client.post(
        reverse("campaigns:create"),
        {
            "title": "Casino promo",
            "product_notes": "Online casino and poker betting app with jackpot",
            "objective": "awareness",
            "deliverable": "reel",
            "budget_rupees": 50000,
            "target_gender": "any",
            "content_mode": "creator_made",
            "usage_rights_days": 90,
        },
    )
    campaign = Campaign.objects.get(title="Casino promo")
    assert campaign.current_brief.data["restricted_category"] == "gambling"
    client.post(reverse("campaigns:confirm_brief", args=[campaign.pk]), {"claims_ack": "1"})
    campaign.refresh_from_db()
    assert campaign.status == Campaign.Status.BRIEF_READY


@pytest.mark.django_db
def test_spec_knows_parents_of_creator_niches(brand_user):
    from apps.campaigns.models import ProductBrief
    from apps.matching import engine
    from apps.matching.services import spec_for

    campaign = Campaign.objects.create(brand=brand_user.brand_profile, title="x", budget=1_000_000)
    brief = ProductBrief.objects.create(
        campaign=campaign, version=1, source="rules", data={"niche_slugs": ["sun-care"], "keywords": []}
    )
    spec = spec_for(campaign, brief)
    sibling = engine.Candidate(
        id=1,
        name="a",
        niche_slugs=["acne-care"],
        primary_niche="acne-care",
        followers=5000,
        avg_reach=1000,
        engagement_rate=4,
        female_pct=60,
        india_pct=90,
        top_cities=[],
        languages=[],
        keywords=[],
        authenticity=90,
        reliability=0.8,
        sponsored_30d=0,
        fee=100_000,
    )
    assert engine.niche_fit(sibling, spec) == 0.6
