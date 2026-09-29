import pytest
from django.core.management import call_command

from apps.accounts.models import User
from apps.brands.models import BrandProfile


@pytest.fixture(autouse=True)
def _settings(settings):
    settings.LLM_PROVIDER = "rules"
    settings.INSTAGRAM_PROVIDER = "mock"
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }


@pytest.fixture
def seeded(db):
    call_command("seed_demo", creators=60, verbosity=0)


@pytest.fixture
def brand_user(db):
    user = User.objects.create_user("brand@test.local", "pw-Strong-123", role=User.Role.BRAND)
    BrandProfile.objects.create(
        user=user,
        company_name="TestCo",
        gstin="27AAPFU0939F1ZV",
        pan="AAPFU0939F",
        status=BrandProfile.Status.APPROVED,
    )
    return user


@pytest.fixture
def creator_user(db):
    return User.objects.create_user(
        "creator@test.local", "pw-Strong-123", role=User.Role.CREATOR, first_name="Asha", last_name="Rao"
    )


@pytest.fixture(autouse=True)
def _fast_passwords(settings):
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture
def paid_slot(client, seeded, brand_user):
    """A campaign with one paid slot, ready for content (via the real flows)."""
    from django.urls import reverse

    from apps.campaigns.models import Campaign
    from apps.offers import services as offers
    from apps.offers.models import Offer, Slot
    from apps.payments.services import mark_paid, start_order

    client.force_login(brand_user)
    client.post(
        reverse("campaigns:create"),
        {
            "title": "Sun launch",
            "product_notes": "SunShield SPF 50 gel sunscreen for oily skin.",
            "objective": "awareness",
            "deliverable": "reel",
            "budget_rupees": 200000,
            "creators_wanted": 1,
            "target_gender": "any",
            "content_mode": "creator_made",
            "usage_rights_days": 90,
            "paid_ads_allowed": "on",
            "must_not_say": "cures acne",
        },
    )
    campaign = Campaign.objects.get(title="Sun launch")
    client.post(reverse("campaigns:confirm_brief", args=[campaign.pk]), {"claims_ack": "1"})
    client.post(reverse("campaigns:confirm_selection", args=[campaign.pk]))
    client.post(reverse("campaigns:send_offers", args=[campaign.pk]))
    offer = Offer.objects.get(slot__campaign=campaign, status=Offer.Status.PENDING)
    offers.accept(offer, agreement=None)
    order = start_order(campaign)
    mark_paid(order.pk, "pay_test")
    slot = Slot.objects.get(pk=offer.slot_id)
    assert slot.status == Slot.Status.CONFIRMED
    return slot


@pytest.fixture(autouse=True)
def _clear_cache():
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()
