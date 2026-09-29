import json

import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.core.models import DataRequest
from apps.core.ops_health import stuck


@pytest.mark.django_db
def test_login_locks_an_email_after_repeated_failures(client, brand_user):
    url = reverse("accounts:login")
    for _ in range(5):
        r = client.post(url, {"username": "brand@test.local", "password": "wrong"})
        assert r.status_code == 200
    # Even the right password is refused while locked, with a clear message.
    r = client.post(url, {"username": "brand@test.local", "password": "pw-Strong-123"})
    assert r.status_code == 429 and "Too many attempts" in r.content.decode()
    # Other accounts are unaffected.
    User.objects.create_user("other@test.local", "pw-Strong-123", role=User.Role.BRAND)
    r = client.post(url, {"username": "other@test.local", "password": "pw-Strong-123"})
    assert r.status_code == 302


@pytest.mark.django_db
def test_successful_login_resets_failures(client, brand_user):
    url = reverse("accounts:login")
    for _ in range(4):
        client.post(url, {"username": "brand@test.local", "password": "wrong"})
    assert client.post(url, {"username": "brand@test.local", "password": "pw-Strong-123"}).status_code == 302
    client.logout()
    for _ in range(4):
        client.post(url, {"username": "brand@test.local", "password": "wrong"})
    assert client.post(url, {"username": "brand@test.local", "password": "pw-Strong-123"}).status_code == 302


@pytest.mark.django_db
def test_signup_limited_per_ip(client, db):
    url = reverse("accounts:signup")
    for i in range(10):
        client.post(
            url, {"role": "brand", "name": "A B", "email": f"x{i}@t.local", "password": "pw-Strong-123"}
        )
        client.logout()
    r = client.post(
        url, {"role": "brand", "name": "A B", "email": "late@t.local", "password": "pw-Strong-123"}
    )
    assert r.status_code == 429
    assert not User.objects.filter(email="late@t.local").exists()


@pytest.mark.django_db
def test_legal_pages_are_public_and_linked(client, db):
    for name in ("core:terms", "core:privacy"):
        assert client.get(reverse(name)).status_code == 200
    page = client.get(reverse("accounts:signup")).content.decode()
    assert reverse("core:terms") in page and reverse("core:privacy") in page


@pytest.mark.django_db
def test_creator_export_has_own_fee_only_and_no_secrets(client, paid_slot):
    creator = paid_slot.creator
    client.force_login(creator.user)
    r = client.post(reverse("core:my_data"), {"action": "export"})
    assert r["Content-Disposition"].startswith("attachment")
    data = json.loads(r.content)
    text = r.content.decode()
    assert data["creator"]["campaigns"][0]["your_fee_inr"] == paid_slot.creator_fee / 100
    assert "brand_price" not in text and "price_inr" not in text
    assert creator.pan not in text and creator.ig_access_token not in text
    assert data["agreements"] and data["consents"]


@pytest.mark.django_db
def test_brand_export_has_brand_prices_only(client, paid_slot, brand_user):
    client.force_login(brand_user)
    data = json.loads(client.post(reverse("core:my_data"), {"action": "export"}).content)
    slot = data["brand"]["campaigns"][0]["creators"][0]
    assert slot["price_inr"] == paid_slot.brand_price / 100
    assert "fee" not in json.dumps(data["brand"])
    assert data["brand"]["invoices"][0]["number"] == paid_slot.order.invoice_number


@pytest.mark.django_db
def test_erasure_request_reaches_ops(client, seeded, brand_user):
    client.force_login(brand_user)
    client.post(reverse("core:my_data"), {"action": "erase", "reason": "Closing the business"})
    client.post(reverse("core:my_data"), {"action": "erase"})  # a second click doesn't duplicate
    req = DataRequest.objects.get(user=brand_user)
    assert req.reason == "Closing the business"
    ops = User.objects.get(email="ops@demo.local")
    assert ops.notifications.filter(title__contains=brand_user.email).count() == 1
    assert any(g["title"].startswith("Data deletion requests") for g in stuck())
    assert "will reply within 30 days" in client.get(reverse("core:my_data")).content.decode()


@pytest.mark.django_db
def test_otp_sending_is_limited(client, creator_user):
    client.force_login(creator_user)
    url = reverse("contracts:sign")
    codes = [client.post(url, {"signed_name": "Asha Rao"}).status_code for _ in range(7)]
    assert codes[-1] == 429 and 429 not in codes[:5]
