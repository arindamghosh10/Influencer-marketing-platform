"""Creator matching engine: pure Python, no database access, fully unit-testable.

Pipeline: hard filters → weighted score → budget-constrained selection → explanations.
"""

from dataclasses import dataclass, field

from apps.core.money import format_inr
from apps.core.pricing import brand_price

WEIGHTS = {
    "niche": 0.20,
    "audience": 0.20,
    "content": 0.15,
    "performance": 0.15,
    "price": 0.10,
    "reliability": 0.10,
    "authenticity": 0.05,
    "freshness": 0.05,
}
# Typical engagement rate by tier; creators at twice the benchmark score full marks.
ER_BENCHMARK = {"nano": 4.0, "micro": 2.5, "mid": 1.8}
MIN_INDIA_AUDIENCE = 60.0
MIN_TARGET_GENDER_SHARE = 40.0
BACKUPS_PER_SLOT = 2
MIN_HEALTHY_POOL = 3


@dataclass
class CampaignSpec:
    niche_slugs: list[str]
    niche_parents: dict[str, str | None]  # slug -> parent slug (None for top level)
    keywords: list[str]
    budget: int
    margin_bps: int
    creators_wanted: int | None = None
    target_gender: str = "any"  # any | female | male
    target_cities: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    restricted_category: str = ""
    needs_ai_likeness: bool = False
    competitors: list[str] = field(default_factory=list)
    min_authenticity: int = 60


@dataclass
class Candidate:
    id: int
    name: str
    niche_slugs: list[str]
    primary_niche: str | None
    followers: int
    avg_reach: int
    engagement_rate: float
    female_pct: float
    india_pct: float
    top_cities: list[str]
    languages: list[str]
    keywords: list[str]
    authenticity: int
    reliability: float
    sponsored_30d: int
    fee: int  # creator fee for the campaign's deliverable, paise
    red_lines: list[str] = field(default_factory=list)
    allows_ai_likeness: bool = False
    active_campaigns: int = 0
    max_active: int = 3
    on_break: bool = False
    approved: bool = True
    ig_connected: bool = True

    @property
    def tier(self):
        if self.followers < 10_000:
            return "nano"
        return "micro" if self.followers <= 100_000 else "mid"


@dataclass
class Scored:
    candidate: Candidate
    score: float
    components: dict[str, float]
    brand_price: int
    reasons: list[str]


@dataclass
class MatchResult:
    recommended: list[Scored]
    backups: list[Scored]
    eligible_count: int
    excluded: dict[str, int]
    shortage: bool
    budget_used: int


def _norm(items):
    return {i.strip().lower() for i in items if i and i.strip()}


def niche_fit(candidate, spec):
    """1.0 same sub-niche, 0.6 same parent category, 0 otherwise."""
    wanted = set(spec.niche_slugs)
    mine = set(candidate.niche_slugs)
    if wanted & mine:
        # Main-niche match counts fully; secondary-niche match slightly less.
        return 1.0 if candidate.primary_niche in wanted else 0.85
    wanted_parents = {spec.niche_parents.get(s) or s for s in wanted}
    my_parents = {spec.niche_parents.get(s) or s for s in mine}
    return 0.6 if wanted_parents & my_parents else 0.0


def target_gender_share(candidate, spec):
    if spec.target_gender == "female":
        return candidate.female_pct
    if spec.target_gender == "male":
        return 100 - candidate.female_pct
    return 100.0


def exclusion_reason(candidate, spec):
    """First reason this creator can't be offered the campaign, or None if eligible."""
    if not candidate.approved:
        return "not approved"
    if not candidate.ig_connected:
        return "Instagram not connected"
    if candidate.on_break or candidate.active_campaigns >= candidate.max_active:
        return "not available"
    if candidate.fee <= 0:
        return "no rate for this deliverable"
    if spec.restricted_category and spec.restricted_category in candidate.red_lines:
        return "refuses this category"
    if spec.needs_ai_likeness and not candidate.allows_ai_likeness:
        return "doesn't allow AI likeness"
    if candidate.authenticity < spec.min_authenticity:
        return "low authenticity score"
    if candidate.india_pct < MIN_INDIA_AUDIENCE:
        return "audience mostly outside India"
    if target_gender_share(candidate, spec) < MIN_TARGET_GENDER_SHARE:
        return "audience gender doesn't fit"
    if spec.languages and not (_norm(spec.languages) & _norm(candidate.languages)):
        return "language doesn't fit"
    if niche_fit(candidate, spec) == 0:
        return "different niche"
    if brand_price(candidate.fee, spec.margin_bps) > spec.budget:
        return "over budget"
    if spec.competitors and (_norm(spec.competitors) & _norm(candidate.keywords)):
        return "mentions a competitor in recent posts"
    return None


def score(candidate, spec, best_value):
    gender = target_gender_share(candidate, spec) / 100
    if spec.target_cities:
        overlap = _norm(spec.target_cities) & _norm(candidate.top_cities)
        city = len(overlap) / min(len(spec.target_cities), 3)
    else:
        city = 1.0
    audience = 0.6 * gender + 0.4 * min(city, 1.0)

    wanted_kw, my_kw = _norm(spec.keywords), _norm(candidate.keywords)
    content = len(wanted_kw & my_kw) / min(len(wanted_kw), len(my_kw)) if wanted_kw and my_kw else 0.0
    content = min(1.0, content * 2)  # a handful of shared topics is already a strong signal

    benchmark = ER_BENCHMARK[candidate.tier]
    performance = min(1.0, candidate.engagement_rate / (2 * benchmark))
    price = brand_price(candidate.fee, spec.margin_bps)
    value = candidate.avg_reach / price if price else 0
    components = {
        "niche": niche_fit(candidate, spec),
        "audience": audience,
        "content": content,
        "performance": performance,
        "price": value / best_value if best_value else 0.0,
        "reliability": max(0.0, min(1.0, candidate.reliability)),
        "authenticity": candidate.authenticity / 100,
        "freshness": 1 - min(1.0, candidate.sponsored_30d / 8),
    }
    total = sum(WEIGHTS[k] * v for k, v in components.items())
    return round(total, 4), {k: round(v, 3) for k, v in components.items()}, price


def explain(candidate, components, spec, price):
    reasons = []
    if spec.target_gender != "any":
        share = target_gender_share(candidate, spec)
        who = "women" if spec.target_gender == "female" else "men"
        reasons.append((components["audience"], f"{share:.0f}% of their audience are {who}"))
    overlap = [c for c in candidate.top_cities if c.lower() in _norm(spec.target_cities)]
    if overlap:
        reasons.append((components["audience"] + 0.1, f"Audience in {', '.join(overlap[:3])}"))
    if components["niche"] >= 0.85:
        reasons.append((components["niche"], "Creates content in exactly your niche"))
    elif components["niche"] >= 0.6:
        reasons.append((components["niche"] - 0.2, "Creates content in your category"))
    shared = [k for k in candidate.keywords if k.lower() in _norm(spec.keywords)]
    if shared:
        reasons.append((components["content"], f"Already talks about {', '.join(shared[:3])}"))
    benchmark = ER_BENCHMARK[candidate.tier]
    if candidate.engagement_rate >= benchmark:
        reasons.append(
            (
                components["performance"],
                f"Engagement {candidate.engagement_rate:.1f}%, above average for {candidate.tier} creators",
            )
        )
    if price:
        per_1000 = candidate.avg_reach * 1000 * 100 / price  # reach per ₹1,000
        reasons.append((components["price"], f"≈{per_1000:,.0f} people reached per {format_inr(100_000)}"))
    if candidate.sponsored_30d <= 1:
        reasons.append((0.5, "Few recent sponsored posts, so the audience isn't ad-fatigued"))
    return [text for _w, text in sorted(reasons, key=lambda r: r[0], reverse=True)[:3]]


def match(candidates, spec):
    excluded = {}
    eligible = []
    for c in candidates:
        reason = exclusion_reason(c, spec)
        if reason:
            excluded[reason] = excluded.get(reason, 0) + 1
        else:
            eligible.append(c)

    values = [c.avg_reach / brand_price(c.fee, spec.margin_bps) for c in eligible]
    best_value = max(values, default=0)
    scored = []
    for c in eligible:
        total, components, price = score(c, spec, best_value)
        scored.append(Scored(c, total, components, price, explain(c, components, spec, price)))
    scored.sort(key=lambda s: s.score, reverse=True)

    # Greedy selection by score within budget. If the brand didn't say how many creators,
    # spend the budget on the best creators we can fit.
    wanted = spec.creators_wanted
    recommended, remaining = [], spec.budget
    tier_counts = {}
    for s in scored:
        if wanted and len(recommended) >= wanted:
            break
        if s.brand_price > remaining:
            continue
        # Keep a mix: no single tier takes more than 70% of slots once we have 4+ picks.
        tier = s.candidate.tier
        if len(recommended) >= 4 and (tier_counts.get(tier, 0) + 1) / (len(recommended) + 1) > 0.7:
            others_left = any(o.candidate.tier != tier and o not in recommended for o in scored)
            if others_left:
                continue
        recommended.append(s)
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
        remaining -= s.brand_price

    picked = {s.candidate.id for s in recommended}
    backup_count = max(1, len(recommended)) * BACKUPS_PER_SLOT
    backups = [s for s in scored if s.candidate.id not in picked][:backup_count]
    shortage = (bool(wanted) and len(recommended) < wanted) or len(eligible) < MIN_HEALTHY_POOL
    return MatchResult(
        recommended=recommended,
        backups=backups,
        eligible_count=len(eligible),
        excluded=excluded,
        shortage=shortage,
        budget_used=spec.budget - remaining,
    )
