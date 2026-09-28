from dataclasses import replace

from apps.matching import engine


def spec(**kw):
    base = dict(
        niche_slugs=["sun-care"],
        niche_parents={"sun-care": "skincare", "acne-care": "skincare", "gym": "fitness"},
        keywords=["sunscreen", "spf", "skincare"],
        budget=10_000_000,
        margin_bps=5000,
        target_gender="female",
        target_cities=["Mumbai", "Pune"],
    )
    base.update(kw)
    return engine.CampaignSpec(**base)


def cand(i, **kw):
    base = dict(
        id=i,
        name=f"c{i}",
        niche_slugs=["sun-care"],
        primary_niche="sun-care",
        followers=20_000,
        avg_reach=8_000,
        engagement_rate=4.0,
        female_pct=75,
        india_pct=90,
        top_cities=["Mumbai", "Delhi"],
        languages=["Hindi", "English"],
        keywords=["sunscreen", "makeup"],
        authenticity=85,
        reliability=0.8,
        sponsored_30d=1,
        fee=500_000,
    )
    base.update(kw)
    return engine.Candidate(**base)


def test_hard_filters_exclude_with_reasons():
    s = spec()
    assert engine.exclusion_reason(cand(1, approved=False), s) == "not approved"
    assert engine.exclusion_reason(cand(1, female_pct=20), s) == "audience gender doesn't fit"
    assert engine.exclusion_reason(cand(1, india_pct=30), s) == "audience mostly outside India"
    assert engine.exclusion_reason(cand(1, authenticity=40), s) == "low authenticity score"
    assert engine.exclusion_reason(cand(1, niche_slugs=["gym"], primary_niche="gym"), s) == "different niche"
    assert engine.exclusion_reason(cand(1, fee=6_000_000), s) == "over budget"
    assert engine.exclusion_reason(cand(1, on_break=True), s) == "not available"
    s2 = spec(restricted_category="supplements")
    assert engine.exclusion_reason(cand(1, red_lines=["supplements"]), s2) == "refuses this category"
    ai_spec = spec(needs_ai_likeness=True)
    assert engine.exclusion_reason(cand(1), ai_spec) == "doesn't allow AI likeness"
    assert engine.exclusion_reason(cand(1), s) is None


def test_sibling_niche_scores_lower_than_exact_match():
    s = spec()
    assert engine.niche_fit(cand(1), s) == 1.0
    assert engine.niche_fit(cand(2, niche_slugs=["acne-care"], primary_niche="acne-care"), s) == 0.6


def test_better_fit_ranks_higher():
    strong = cand(1)
    weak = cand(
        2,
        niche_slugs=["acne-care"],
        primary_niche="acne-care",
        top_cities=["Kochi"],
        keywords=["random"],
        engagement_rate=1.6,
    )
    result = engine.match([weak, strong], spec(creators_wanted=2))
    assert [s.candidate.id for s in result.recommended] == [1, 2]
    assert result.recommended[0].reasons


def test_selection_respects_budget_and_count():
    creators = [cand(i) for i in range(10)]  # brand price ₹10,000 each
    result = engine.match(creators, spec(budget=3_500_000))
    assert len(result.recommended) == 3
    assert result.budget_used == 3_000_000
    result = engine.match(creators, spec(creators_wanted=2))
    assert len(result.recommended) == 2
    assert len(result.backups) == 4


def test_shortage_when_pool_is_small():
    result = engine.match([cand(1), cand(2, female_pct=10)], spec(creators_wanted=3))
    assert result.shortage
    assert result.excluded == {"audience gender doesn't fit": 1}


def test_tier_mix_is_kept():
    nanos = [cand(i, followers=5_000, avg_reach=2_000) for i in range(8)]
    micros = [replace(cand(100 + i), followers=50_000, engagement_rate=1.0) for i in range(3)]
    result = engine.match(nanos + micros, spec(budget=100_000_000, creators_wanted=8))
    tiers = [s.candidate.tier for s in result.recommended]
    assert "micro" in tiers
