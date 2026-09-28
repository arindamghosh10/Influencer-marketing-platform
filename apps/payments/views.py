import json
import logging

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.brands.views import get_brand
from apps.contracts import services as contracts
from apps.contracts.models import AgreementKind, ConsentScope
from apps.core.money import format_inr
from apps.core.permissions import brand_required
from apps.integrations.registry import get_provider

from . import services
from .models import Order, WebhookEvent
from .providers import PaymentError, RazorpayPayments

log = logging.getLogger(__name__)


def _brand_order(request, pk):
    return get_object_or_404(
        Order.objects.select_related("campaign", "brand"), pk=pk, brand=get_brand(request)
    )


@brand_required
@require_POST
def start(request, campaign_id):
    """Brand clicked "Pay": build the order and send them to sign it."""
    from apps.campaigns.models import Campaign

    campaign = get_object_or_404(Campaign, pk=campaign_id, brand=get_brand(request))
    try:
        order = services.start_order(campaign)
    except services.OrderError as exc:
        messages.error(request, str(exc))
        return redirect("campaigns:detail", pk=campaign.pk)
    brand = campaign.brand
    contracts.prepare_signature(
        request,
        AgreementKind.BRAND_ORDER,
        {
            "platform_name": settings.PLATFORM_NAME,
            "order_id": order.pk,
            "company_name": brand.company_name,
            "gstin": brand.gstin,
            "today": timezone.localdate().strftime("%d %B %Y"),
            "campaign_title": campaign.title,
            "deliverable": campaign.get_deliverable_display(),
            "lines": [{**line, "amount_display": format_inr(line["amount"])} for line in order.lines],
            "subtotal": format_inr(order.subtotal),
            "gst": format_inr(order.gst_total),
            "total": format_inr(order.total),
            "brand_review_hours": settings.BRAND_REVIEW_HOURS,
            "usage_rights_days": campaign.usage_rights_days,
            "paid_ads": campaign.paid_ads_allowed,
        },
        [ConsentScope.TERMS],
        next_url=reverse("payments:checkout", args=[order.pk]),
        campaign=campaign,
    )
    return redirect("contracts:sign")


@brand_required
def checkout(request, pk):
    order = _brand_order(request, pk)
    if order.status == Order.Status.PAID:
        return redirect("payments:invoice", pk=order.pk)
    if order.status == Order.Status.AWAITING_SIGNATURE:
        agreement = contracts.latest_campaign_agreement(
            request.user, AgreementKind.BRAND_ORDER, order.campaign, since=order.created_at
        )
        if agreement is None:
            messages.error(request, "Please sign the order first.")
            return redirect("campaigns:detail", pk=order.campaign_id)
        try:
            order = services.attach_agreement(order, agreement)
        except PaymentError as exc:
            messages.error(request, f"Payment couldn't start: {exc}")
            return redirect("campaigns:detail", pk=order.campaign_id)
    if order.status != Order.Status.CREATED:
        messages.error(request, "This order can't be paid any more. Start a new payment from the campaign.")
        return redirect("campaigns:detail", pk=order.campaign_id)
    provider = get_provider("payments")
    context = {"order": order, **provider.checkout_context(order)}
    return render(request, provider.template, context)


@brand_required
@require_POST
def confirm(request, pk):
    """Browser callback after checkout (mock button or Razorpay handler)."""
    order = _brand_order(request, pk)
    if order.status == Order.Status.PAID:
        return redirect("payments:invoice", pk=order.pk)
    if order.status != Order.Status.CREATED:
        return HttpResponseBadRequest("Order isn't awaiting payment")
    provider = get_provider("payments")
    try:
        payment_id = provider.verify_checkout(order, request.POST)
        services.mark_paid(order.pk, payment_id)
    except (PaymentError, services.OrderError) as exc:
        log.warning("Checkout verification failed for order %s: %s", order.pk, exc)
        messages.error(request, f"We couldn't confirm the payment: {exc}")
        return redirect("payments:checkout", pk=order.pk)
    messages.success(request, "Payment received. Your creators have been told to start.")
    return redirect("campaigns:detail", pk=order.campaign_id)


def invoice(request, pk):
    if not request.user.is_authenticated:
        return redirect(f"{reverse('accounts:login')}?next={request.path}")
    order = get_object_or_404(Order.objects.select_related("campaign", "brand"), pk=pk)
    if not (request.user.is_ops or order.brand.user_id == request.user.pk):
        raise PermissionDenied
    if order.status != Order.Status.PAID:
        raise PermissionDenied
    return render(request, "payments/invoice.html", {"order": order, "platform": settings})


@csrf_exempt
@require_POST
def razorpay_webhook(request):
    """Razorpay calls this for payment events; the signature proves it came from Razorpay."""
    signature = request.headers.get("X-Razorpay-Signature", "")
    if not RazorpayPayments.verify_webhook(request.body, signature):
        return HttpResponse(status=400)
    try:
        event = json.loads(request.body)
    except ValueError:
        return HttpResponse(status=400)
    event_id = request.headers.get("X-Razorpay-Event-Id") or f"{event.get('event')}:{event.get('created_at')}"
    try:
        with transaction.atomic():
            WebhookEvent.objects.create(
                provider="razorpay", event_id=event_id, event_type=event.get("event", ""), payload=event
            )
    except IntegrityError:
        return HttpResponse("duplicate")  # already processed
    if event.get("event") in ("payment.captured", "order.paid"):
        payment = event.get("payload", {}).get("payment", {}).get("entity", {})
        order = Order.objects.filter(provider="razorpay", provider_order_id=payment.get("order_id")).first()
        if order is None:
            log.warning("Webhook for unknown Razorpay order %s", payment.get("order_id"))
        else:
            try:
                services.mark_paid(order.pk, payment.get("id", ""), amount=payment.get("amount"))
            except services.OrderError as exc:
                log.error("Webhook payment mismatch for order %s: %s", order.pk, exc)
                return HttpResponse(status=400)
    return HttpResponse("ok")
