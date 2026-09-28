from django.db import transaction
from django.utils import timezone

from apps.core.events import record
from apps.integrations import llm
from apps.integrations.fetch import FetchError
from apps.integrations.product_page import ProductPage, fetch_product_page
from apps.niches.models import BLOCKED_CATEGORIES, SensitiveCategory

from .models import Campaign, ProductBrief


def _next_version(campaign):
    last = campaign.briefs.order_by("-version").first()
    return (last.version + 1) if last else 1


def generate_brief(campaign, actor=None):
    """Read the product page (if any) and create a new unconfirmed brief version."""
    page, error = None, ""
    if campaign.product_url:
        try:
            page = fetch_product_page(campaign.product_url)
        except FetchError as exc:
            error = str(exc)
    if page is None:
        page = ProductPage(
            url=campaign.product_url,
            title=campaign.title,
            description=campaign.product_notes,
            text=campaign.product_notes,
        )
    data, source = llm.extract_brief(page, notes=campaign.product_notes)
    with transaction.atomic():
        brief = ProductBrief.objects.create(
            campaign=campaign,
            version=_next_version(campaign),
            source=source,
            data=data.model_dump(),
            fetch_error=error[:300],
        )
        campaign.status = Campaign.Status.BRIEF_READY
        campaign.save(update_fields=["status", "updated_at"])
    record(
        "campaign.brief_generated",
        f"Brief v{brief.version} generated ({brief.get_source_display()})",
        actor=actor,
        target=campaign,
        data={"fetch_error": error},
    )
    return brief


def save_edited_brief(campaign, data, actor):
    with transaction.atomic():
        brief = ProductBrief.objects.create(
            campaign=campaign,
            version=_next_version(campaign),
            source=ProductBrief.Source.EDITED,
            data=data,
        )
        campaign.status = Campaign.Status.BRIEF_READY
        campaign.save(update_fields=["status", "updated_at"])
    record("campaign.brief_edited", f"Brief v{brief.version} edited by brand", actor=actor, target=campaign)
    return brief


def brief_blockers(brief):
    """Reasons the brand can't confirm this brief."""
    problems = []
    category = brief.data.get("restricted_category")
    if category in {c.value for c in BLOCKED_CATEGORIES}:
        problems.append(f"{SensitiveCategory(category).label} products can't be promoted on the platform.")
    if not brief.data.get("niche_slugs"):
        problems.append("Pick at least one niche so we can match creators.")
    return problems


def confirm_brief(campaign, brief, actor):
    brief.confirmed_at = timezone.now()
    brief.confirmed_by = actor
    brief.save(update_fields=["confirmed_at", "confirmed_by"])
    campaign.status = Campaign.Status.BRIEF_CONFIRMED
    campaign.save(update_fields=["status", "updated_at"])
    record("campaign.brief_confirmed", f"Brief v{brief.version} confirmed", actor=actor, target=campaign)


def needs_review(brief):
    category = brief.data.get("restricted_category")
    return bool(category) and category not in {c.value for c in BLOCKED_CATEGORIES}


COPIED_FIELDS = [
    "brand",
    "objective",
    "product_url",
    "product_notes",
    "product_image",
    "budget",
    "creators_wanted",
    "deliverable",
    "target_gender",
    "target_cities",
    "languages",
    "content_mode",
    "usage_rights_days",
    "paid_ads_allowed",
    "must_say",
    "must_not_say",
]


def can_repeat(campaign):
    return campaign.confirmed_brief is not None and campaign.status != Campaign.Status.CANCELLED


@transaction.atomic
def repeat_campaign(campaign, actor):
    """Start a new campaign with the same settings and confirmed brief.

    The new campaign goes straight to creator selection; creators who delivered last time are
    matched first when they're still available. Pricing, ops sign-off and the content deadline
    are not copied: they're decided fresh for the new campaign.
    """
    from apps.matching.services import run_matching

    brief = campaign.confirmed_brief
    if not can_repeat(campaign):
        raise ValueError("Only campaigns with a confirmed brief can be run again.")
    new = Campaign(
        title=f"{campaign.title} (repeat)"[:200],
        status=Campaign.Status.BRIEF_CONFIRMED,
        repeat_of=campaign,
        **{f: getattr(campaign, f) for f in COPIED_FIELDS},
    )
    new.save()
    ProductBrief.objects.create(
        campaign=new,
        version=1,
        source=brief.source,
        data=brief.data,
        confirmed_at=timezone.now(),
        confirmed_by=actor,
    )
    record(
        "campaign.repeated",
        f"Campaign '{new}' created from '{campaign}'",
        actor=actor,
        target=new,
        data={"repeat_of": campaign.pk},
    )
    run_matching(new)
    return new
