"""Rule-based brief extraction: free, offline, always available as a fallback."""

import re

from apps.creators.services import text_keywords
from apps.niches.models import Niche, SensitiveCategory
from apps.niches.services import phrase_count

from .schema import BriefData

SENSITIVE_KEYWORDS = {
    SensitiveCategory.ALCOHOL: [
        "beer",
        "whisky",
        "whiskey",
        "vodka",
        "wine",
        "rum",
        "alcohol",
        "liquor",
        "gin",
    ],
    SensitiveCategory.TOBACCO: ["cigarette", "tobacco", "vape", "hookah", "nicotine"],
    SensitiveCategory.GAMBLING: ["casino", "betting", "bet", "rummy", "poker", "fantasy cricket", "jackpot"],
    SensitiveCategory.CRYPTO: ["crypto", "bitcoin", "trading app", "forex", "nft"],
    SensitiveCategory.FINANCIAL: ["loan", "credit line", "emi card", "insurance policy", "instant cash"],
    SensitiveCategory.PHARMA: ["tablet", "capsules", "prescription", "medicine", "ayurvedic medicine"],
    SensitiveCategory.SUPPLEMENTS: ["supplement", "weight loss", "fat burner", "testosterone", "gummies"],
    SensitiveCategory.ADULT: ["condom", "lubricant", "intimate", "sexual"],
    SensitiveCategory.WEAPONS: ["knife", "gun", "pepper spray"],
}

RISKY_CLAIM_PATTERNS = [
    r"\bcures?\b",
    r"\bguarantee[ds]?\b",
    r"\b100\s?%",
    r"clinically proven",
    r"dermatologist[- ]approved",
    r"no side[- ]effects?",
    r"\bpermanent(ly)?\b",
    r"\bmiracle\b",
    r"doctor[- ]recommended",
    r"fda[- ]approved",
    r"\binstant(ly)? results?\b",
    r"\bnumber ?1\b|\b#1\b",
    r"\bbest in (india|the world)\b",
    r"\bchemical[- ]free\b",
    r"lose \d+ ?kg",
]


def detect_sensitive_category(text):
    """Whole-word match, so e.g. 'serum' doesn't trigger 'rum'."""
    lowered = text.lower()
    for category, words in SENSITIVE_KEYWORDS.items():
        if any(re.search(rf"\b{re.escape(w.strip())}\b", lowered) for w in words):
            return category.value
    return ""


def _sentences_matching(text, patterns):
    out = []
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if any(re.search(p, sentence, re.I) for p in patterns):
            out.append(sentence.strip()[:200])
    return list(dict.fromkeys(out))[:6]


def _niche_hits(text):
    text = text.lower()
    hits = []
    for niche in Niche.objects.filter(parent__isnull=False).select_related("parent"):
        own = sum(phrase_count(text, k) for k in niche.keywords)
        if own:  # a sub-niche needs its own keyword; the parent's keywords only break ties
            hits.append((own + 0.5 * sum(phrase_count(text, k) for k in niche.parent.keywords), niche.slug))
    return [slug for _s, slug in sorted(hits, reverse=True)[:3]]


class RulesLLM:
    name = "rules"

    def extract_brief(self, page, notes=""):
        text = " ".join([page.title, page.description, page.text, notes])
        restricted = detect_sensitive_category(text)
        description = (page.description or page.text)[:400]
        return BriefData(
            product_name=page.title[:120] or "Your product",
            brand_name=page.brand,
            category=(page.product_data.get("category") or "") if page.product_data else "",
            summary=description,
            price_inr=page.price_inr,
            key_features=[],
            benefits=[],
            claims=[],
            target_audience="",
            niche_slugs=_niche_hits(text),
            keywords=text_keywords([page.title, page.description, notes, page.text[:1500]], limit=15),
            restricted_category=restricted,
            risky_claims=_sentences_matching(text, RISKY_CLAIM_PATTERNS),
        )

    def creator_brief(self, brief, campaign, creator):
        from .scripts import template_creator_brief

        return template_creator_brief(brief, campaign, creator)
