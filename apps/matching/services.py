from django.conf import settings
from django.db import transaction

from apps.creators.models import CreatorProfile
from apps.niches.models import Niche

from . import engine
from .models import MatchCandidate, MatchRun


def spec_for(campaign, brief):
    data = brief.data
    slugs = data.get("niche_slugs") or []
    # Parent of every niche (the taxonomy is small), so creators in sibling niches of the
    # brief's niches get partial credit.
    parents = dict(Niche.objects.values_list("slug", "parent__slug"))
    return engine.CampaignSpec(
        niche_slugs=slugs,
        niche_parents=parents,
        keywords=data.get("keywords") or [],
        budget=campaign.budget,
        margin_bps=campaign.margin_bps,
        creators_wanted=campaign.creators_wanted,
        target_gender=campaign.target_gender,
        target_cities=campaign.target_cities,
        languages=campaign.languages,
        restricted_category=data.get("restricted_category") or "",
        needs_ai_likeness=campaign.content_mode == campaign.ContentMode.AI_LIKENESS,
        competitors=campaign.brand.competitors,
        min_authenticity=settings.MIN_AUTHENTICITY_SCORE,
    )


def candidates_for(campaign):
    creators = (
        CreatorProfile.objects.filter(status=CreatorProfile.Status.APPROVED)
        .select_related("primary_niche__parent")
        .prefetch_related("niches")
    )
    out = []
    for c in creators:
        slugs = {n.slug for n in c.niches.all()}
        if c.primary_niche:
            slugs.add(c.primary_niche.slug)
        out.append(
            engine.Candidate(
                id=c.pk,
                name=c.display_name,
                niche_slugs=sorted(slugs),
                primary_niche=c.primary_niche.slug if c.primary_niche else None,
                followers=c.followers,
                avg_reach=c.avg_reach,
                engagement_rate=c.engagement_rate,
                female_pct=c.audience_female_pct,
                india_pct=c.audience_india_pct,
                top_cities=c.audience_top_cities,
                languages=c.languages,
                keywords=c.content_keywords,
                authenticity=c.authenticity_score,
                reliability=c.reliability_score,
                sponsored_30d=c.sponsored_posts_30d,
                fee=c.rate_for(campaign.deliverable),
                red_lines=c.red_lines,
                allows_ai_likeness=c.allows_ai_likeness,
                active_campaigns=0,  # filled from live slots once offers exist
                max_active=c.max_active_campaigns,
                on_break=c.on_break,
                approved=True,
                ig_connected=c.ig_connected,
            )
        )
    return out


@transaction.atomic
def run_matching(campaign):
    brief = campaign.confirmed_brief
    if brief is None:
        raise ValueError("Confirm the brief before matching.")
    result = engine.match(candidates_for(campaign), spec_for(campaign, brief))
    run = MatchRun.objects.create(
        campaign=campaign,
        brief=brief,
        eligible_count=result.eligible_count,
        excluded_counts=result.excluded,
        shortage=result.shortage,
    )
    rank = 0
    for role, items in (
        (MatchCandidate.Role.RECOMMENDED, result.recommended),
        (MatchCandidate.Role.BACKUP, result.backups),
    ):
        for s in items:
            rank += 1
            MatchCandidate.objects.create(
                run=run,
                creator_id=s.candidate.id,
                rank=rank,
                role=role,
                score=s.score,
                components=s.components,
                reasons=s.reasons,
                creator_fee=s.candidate.fee,
                brand_price=s.brand_price,
                selected=role == MatchCandidate.Role.RECOMMENDED,
            )
    return run
