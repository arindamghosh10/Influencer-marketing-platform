"""Role-specific read models.

Brand pages receive BrandCandidateView objects, which have no creator fee field at all, so a
template can't accidentally show it. Creator pages will get an offer view with no brand price.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class BrandCandidateView:
    id: int
    creator_id: int
    display_name: str
    ig_username: str
    tier: str
    niche: str
    city: str
    followers: int
    avg_reach: int
    engagement_rate: float
    authenticity: int
    reasons: list
    score_pct: int
    price: int  # what the brand pays for this creator (paise, excl. GST)
    selected: bool
    role: str

    @classmethod
    def from_candidate(cls, mc):
        c = mc.creator
        return cls(
            id=mc.pk,
            creator_id=c.pk,
            display_name=c.display_name,
            ig_username=c.ig_username,
            tier=c.tier,
            niche=str(c.primary_niche) if c.primary_niche else "",
            city=c.city,
            followers=c.followers,
            avg_reach=c.avg_reach,
            engagement_rate=c.engagement_rate,
            authenticity=c.authenticity_score,
            reasons=mc.reasons,
            score_pct=round(mc.score * 100),
            price=mc.brand_price,
            selected=mc.selected,
            role=mc.role,
        )


def brand_candidates(run):
    qs = run.candidates.select_related("creator__primary_niche__parent")
    return [BrandCandidateView.from_candidate(mc) for mc in qs]
