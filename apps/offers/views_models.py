"""Creator-facing offer view. Deliberately has no brand price field."""

from dataclasses import dataclass
from datetime import datetime

from django.conf import settings

from apps.payments.tax import payout_breakdown


@dataclass(frozen=True)
class CreatorOfferView:
    id: int
    status: str
    status_label: str
    brand_name: str
    brand_verified: bool
    campaign_title: str
    deliverable: str
    product_name: str
    product_summary: str
    benefits: list
    must_say: str
    must_not_say: str
    risky_claims: list
    content_deadline: object
    usage_rights_days: int
    paid_ads: bool
    ai_likeness: bool
    min_live_days: int
    verification_days: int
    expires_at: datetime
    fee: int
    gst: int
    tds: int
    tds_rate_pct: float
    net: int

    @classmethod
    def build(cls, offer):
        campaign = offer.slot.campaign
        brief = campaign.confirmed_brief
        data = brief.data if brief else {}
        b = payout_breakdown(offer.creator, offer.creator_fee)
        return cls(
            id=offer.pk,
            status=offer.status,
            status_label=offer.get_status_display(),
            brand_name=campaign.brand.company_name,
            brand_verified=bool(campaign.brand.domain_verified_at),
            campaign_title=campaign.title,
            deliverable=campaign.get_deliverable_display(),
            product_name=data.get("product_name", ""),
            product_summary=data.get("summary", ""),
            benefits=data.get("benefits", []) or data.get("key_features", []),
            must_say=campaign.must_say,
            must_not_say=campaign.must_not_say,
            risky_claims=data.get("risky_claims", []),
            content_deadline=campaign.content_deadline,
            usage_rights_days=campaign.usage_rights_days,
            paid_ads=campaign.paid_ads_allowed,
            ai_likeness=campaign.content_mode == campaign.ContentMode.AI_LIKENESS,
            min_live_days=settings.MIN_LIVE_DAYS,
            verification_days=settings.VERIFICATION_DAYS,
            expires_at=offer.expires_at,
            fee=b.gross,
            gst=b.gst,
            tds=b.tds,
            tds_rate_pct=b.tds_rate_bps / 100,
            net=b.net,
        )
