"""Payment provider adapters.

- MockPayments: test mode. The checkout page shows a "Pay (test)" button; no money moves.
- RazorpayPayments: Razorpay Orders API + Standard Checkout. No setup fee, per-transaction
  pricing only. Webhooks confirm payment even if the browser closes before the callback.
"""

import hashlib
import hmac
import secrets

import httpx
from django.conf import settings


class PaymentError(Exception):
    pass


class MockPayments:
    name = "mock"
    template = "payments/checkout_mock.html"

    def create_order(self, order):
        return f"mock_order_{order.pk}_{secrets.token_hex(4)}"

    def checkout_context(self, order):
        return {}

    def verify_checkout(self, order, data):
        """Returns the provider payment id."""
        if data.get("mock_confirm") != order.provider_order_id:
            raise PaymentError("Test payment wasn't confirmed.")
        return f"mock_pay_{secrets.token_hex(6)}"


class RazorpayPayments:
    name = "razorpay"
    template = "payments/checkout_razorpay.html"
    api = "https://api.razorpay.com/v1"

    def __init__(self):
        self.key_id = settings.RAZORPAY_KEY_ID
        self.key_secret = settings.RAZORPAY_KEY_SECRET
        if not (self.key_id and self.key_secret):
            raise PaymentError("RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET are not configured")

    def create_order(self, order):
        try:
            resp = httpx.post(
                f"{self.api}/orders",
                auth=(self.key_id, self.key_secret),
                json={
                    "amount": order.total,  # paise
                    "currency": "INR",
                    "receipt": f"order-{order.pk}",
                    "notes": {"order_id": str(order.pk), "campaign_id": str(order.campaign_id)},
                },
                timeout=15,
            )
        except httpx.HTTPError as exc:
            raise PaymentError(f"Couldn't reach Razorpay: {exc.__class__.__name__}") from exc
        if resp.status_code >= 400:
            raise PaymentError(f"Razorpay error {resp.status_code}: {resp.text[:200]}")
        return resp.json()["id"]

    def checkout_context(self, order):
        return {"razorpay_key_id": self.key_id}

    def verify_checkout(self, order, data):
        """Razorpay signs `order_id|payment_id` with the key secret."""
        payment_id = data.get("razorpay_payment_id", "")
        signature = data.get("razorpay_signature", "")
        if data.get("razorpay_order_id") != order.provider_order_id or not payment_id:
            raise PaymentError("Payment details don't match this order.")
        message = f"{order.provider_order_id}|{payment_id}".encode()
        expected = hmac.new(self.key_secret.encode(), message, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise PaymentError("Payment signature is invalid.")
        return payment_id

    @staticmethod
    def verify_webhook(body, signature):
        secret = settings.RAZORPAY_WEBHOOK_SECRET
        if not secret:
            return False
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature or "")
