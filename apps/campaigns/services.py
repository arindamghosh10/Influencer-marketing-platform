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
