"""Personal data export (right to access) for brands and creators.

Keeps the price separation: a creator's export has creator fees only, a brand's export has
brand prices only. Secrets (full PAN, bank account, Instagram token) are never exported.
"""

from django.utils import timezone


def _dt(value):
    return value.isoformat() if value else None


def export_for(user):
    data = {
        "exported_at": _dt(timezone.now()),
        "account": {
            "email": user.email,
            "name": user.get_full_name(),
            "role": user.role,
            "joined": _dt(user.date_joined),
        },
        "agreements": [
            {
                "kind": a.get_kind_display(),
                "version": a.version,
                "campaign": a.campaign.title if a.campaign_id else None,
                "signed_name": a.signed_name,
                "signed_at": _dt(a.signed_at),
                "sha256": a.sha256,
                "text": a.body,
            }
            for a in user.agreements.select_related("campaign")
        ],
        "consents": [
            {
                "scope": e.get_scope_display(),
                "action": e.action,
                "campaign": e.campaign.title if e.campaign_id else None,
                "file_sha256": e.asset_sha256 or None,
                "at": _dt(e.created_at),
            }
            for e in user.consent_events.select_related("campaign").order_by("created_at")
        ],
        "notifications": [
            {"title": n.title, "body": n.body, "at": _dt(n.created_at)}
            for n in user.notifications.all()[:500]
        ],
    }
    if user.is_creator and hasattr(user, "creator_profile"):
        data["creator"] = _creator(user.creator_profile)
    if user.is_brand and hasattr(user, "brand_profile"):
        data["brand"] = _brand(user.brand_profile)
    return data


def _creator(c):
    return {
        "profile": {
            "display_name": c.display_name,
            "legal_name": c.legal_name,
            "city": c.city,
            "languages": c.languages,
            "primary_niche": str(c.primary_niche) if c.primary_niche_id else None,
            "niches": [str(n) for n in c.niches.all()],
            "red_lines": c.red_line_labels(),
            "allows_ai_likeness": c.allows_ai_likeness,
            "rates_inr": {
                "reel": c.rate_reel / 100,
                "story": c.rate_story / 100,
                "post": c.rate_post / 100,
            },
            "pan_last4": c.pan_last4,
            "bank_account_last4": c.bank_account_last4,
        },
        "instagram": {
            "username": c.ig_username,
            "followers": c.followers,
            "avg_reach": c.avg_reach,
            "engagement_rate": c.engagement_rate,
            "audience_female_pct": c.audience_female_pct,
            "audience_india_pct": c.audience_india_pct,
            "audience_top_cities": c.audience_top_cities,
            "last_synced": _dt(c.ig_synced_at),
        },
        "campaigns": [
            {
                "campaign": s.campaign.title,
                "brand": s.campaign.brand.company_name,
                "status": s.get_status_display(),
                "your_fee_inr": s.creator_fee / 100,
                "accepted_at": _dt(s.accepted_at),
            }
            for s in c.slots.select_related("campaign__brand")
        ],
        "payouts": [
            {
                "campaign": p.slot.campaign.title,
                "status": p.get_status_display(),
                "gross_inr": p.gross / 100,
                "gst_inr": p.gst / 100,
                "tds_inr": p.tds / 100,
                "net_inr": p.net / 100,
                "utr": p.utr or None,
                "paid_at": _dt(p.paid_at),
            }
            for p in c.payouts.select_related("slot__campaign")
        ],
    }


def _brand(b):
    return {
        "profile": {
            "company_name": b.company_name,
            "domain": b.domain,
            "gstin": b.gstin,
            "pan": b.pan,
        },
        "campaigns": [
            {
                "title": camp.title,
                "status": camp.get_status_display(),
                "budget_inr": camp.budget / 100,
                "created_at": _dt(camp.created_at),
                "creators": [
                    {
                        "creator": s.creator.display_name if s.creator_id else None,
                        "status": s.get_status_display(),
                        "price_inr": s.brand_price / 100,
                    }
                    for s in camp.slots.select_related("creator")
                ],
            }
            for camp in b.campaigns.all()
        ],
        "invoices": [
            {
                "number": o.invoice_number,
                "status": o.get_status_display(),
                "subtotal_inr": o.subtotal / 100,
                "total_inr": o.total / 100,
                "paid_at": _dt(o.paid_at),
            }
            for o in b.orders.all()
        ],
    }
