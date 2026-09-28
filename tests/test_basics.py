import pytest
from django.core.exceptions import ValidationError
from django.db import connection

from apps.core.money import format_inr
from apps.core.pricing import brand_price, gst, tds
from apps.core.validators import validate_gstin, validate_ifsc, validate_pan


def test_inr_formatting_uses_indian_grouping():
    assert format_inr(12345600) == "₹1,23,456"
    assert format_inr(100) == "₹1"
    assert format_inr(99999999) == "₹9,99,999"


@pytest.mark.parametrize("value", ["27AAPFU0939F1ZV", "29AAGCB7383J1Z4"])
def test_valid_gstin(value):
    validate_gstin(value)


@pytest.mark.parametrize("value", ["27AAPFU0939F1ZX", "27AAPFU0939F1Z", "hello"])
def test_invalid_gstin(value):
    with pytest.raises(ValidationError):
        validate_gstin(value)


def test_pan_and_ifsc():
    validate_pan("ABCDE1234F")
    validate_ifsc("HDFC0001234")
    with pytest.raises(ValidationError):
        validate_pan("ABCD1234F")
    with pytest.raises(ValidationError):
        validate_ifsc("HDFC1001234")


def test_brand_price_applies_margin_and_rounds_up_to_ten_rupees():
    assert brand_price(500_000, 5000) == 1_000_000  # ₹5,000 fee -> ₹10,000 at 50%
    assert brand_price(333_300, 5000) == 667_000  # ₹6,666 -> rounded up to ₹6,670
    assert brand_price(500_000, 0) == 500_000
    with pytest.raises(ValueError):
        brand_price(100, 10_000)


def test_gst_and_tds():
    assert gst(1_000_000, 1800) == 180_000
    assert tds(500_000, 100) == 5_000


@pytest.mark.django_db
def test_sensitive_fields_are_encrypted_at_rest(creator_user):
    from apps.creators.models import CreatorProfile

    creator = CreatorProfile.objects.create(
        user=creator_user, display_name="A", pan="ABCDE1234F", bank_account_number="123456789012"
    )
    with connection.cursor() as cur:
        cur.execute("SELECT pan, bank_account_number FROM creators_creatorprofile WHERE id=%s", [creator.pk])
        raw_pan, raw_bank = cur.fetchone()
    assert "ABCDE1234F" not in raw_pan and "123456789012" not in raw_bank
    creator.refresh_from_db()
    assert creator.pan == "ABCDE1234F"


@pytest.mark.django_db
def test_niche_taxonomy_loaded():
    from apps.niches.models import Niche

    assert Niche.objects.filter(parent__isnull=True).count() >= 15
    assert Niche.objects.filter(slug="acne-care", parent__slug="skincare").exists()
