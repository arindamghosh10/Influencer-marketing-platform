import re
from collections import Counter

from django.utils import timezone

from apps.niches.models import Niche
from apps.niches.services import phrase_count

MIN_FOLLOWERS = 1_000
MAX_FOLLOWERS = 100_000  # v1 serves nano and micro creators only

_WORD_RE = re.compile(r"[#@]?[a-z][a-z'\-]+")


def text_keywords(texts, limit=40):
    """Lower-cased hashtags and words (stop-words removed), most frequent first."""
    counts = Counter()
    for text in texts:
        for token in _WORD_RE.findall((text or "").lower()):
            token = token.lstrip("#@")
            if len(token) > 2 and token not in STOPWORDS:
                counts[token] += 1
    return [w for w, _ in counts.most_common(limit)]


def niche_scores(texts):
    """How strongly a set of texts matches each niche, by keyword hits. {niche: hits}."""
    blob = " ".join(t.lower() for t in texts if t)
    scores = {}
    for niche in Niche.objects.all():
        hits = sum(phrase_count(blob, k) for k in niche.keywords)
        if hits:
            scores[niche] = hits
    return scores


def suggest_niches(texts, limit=3):
    scores = niche_scores(texts)
    # Prefer specific sub-niches; a parent only wins if no child matched.
    ranked = sorted(scores.items(), key=lambda kv: (kv[1], kv[0].parent_id is not None), reverse=True)
    return [n for n, _ in ranked[:limit]]


def authenticity_score(profile):
    """0-100 heuristic until a paid authenticity provider is added.

    Signals: engagement far below/above normal for the size, reach far below followers
    (bought followers don't see posts), and very few posts for the follower count.
    """
    score = 100.0
    followers = max(profile.followers, 1)
    er = profile.engagement_rate
    if er < 0.8:
        score -= 35
    elif er < 1.5:
        score -= 15
    if er > 15:
        score -= 25  # engagement pods / bought likes
    reach_ratio = profile.avg_reach / followers
    if reach_ratio < 0.05:
        score -= 30
    elif reach_ratio < 0.12:
        score -= 10
    if profile.media_count and followers / profile.media_count > 2_000:
        score -= 15
    return int(max(0, min(100, score)))


def apply_instagram_profile(creator, token, profile, *, refresh_keywords=True):
    creator.ig_username = profile.username
    creator.ig_user_id = profile.user_id
    creator.ig_access_token = token.access_token
    creator.ig_token_expires_at = token.expires_at
    creator.ig_connected_at = creator.ig_connected_at or timezone.now()
    creator.ig_synced_at = timezone.now()
    creator.ig_sync_failures = 0
    creator.ig_sync_error = ""
    creator.ig_needs_reconnect = False
    creator.followers = profile.followers
    creator.avg_reach = profile.avg_reach
    creator.avg_views = profile.avg_views
    creator.engagement_rate = profile.engagement_rate
    creator.audience_female_pct = profile.audience_female_pct
    creator.audience_india_pct = profile.audience_india_pct
    creator.audience_top_cities = profile.audience_top_cities
    creator.audience_age = profile.audience_age
    if refresh_keywords:
        creator.content_keywords = text_keywords(profile.recent_captions)
    creator.sponsored_posts_30d = profile.sponsored_posts_30d
    creator.authenticity_score = authenticity_score(profile)
    creator.save()
    return suggest_niches(profile.recent_captions)


def suggested_rate_band(creator):
    """Suggested Reel fee range in paise, from audience size and engagement.

    Rough v1 heuristic for Indian nano/micro creators (about ₹0.2-0.6 per follower, scaled by
    engagement). Replaced by real accepted-offer data once campaigns run.
    """
    if not creator.followers:
        return None
    multiplier = min(max(creator.engagement_rate / 3.0, 0.6), 1.8)
    low = max(500, creator.followers * 0.2 * multiplier)
    high = max(1500, creator.followers * 0.6 * multiplier)
    return int(round(low, -2)) * 100, int(round(high, -2)) * 100


def onboarding_steps(creator):
    """[(key, label, done)] for the progress bar."""
    from apps.contracts.models import AgreementKind
    from apps.contracts.services import has_current_agreement

    return [
        ("profile", "Profile & niches", bool(creator.display_name and creator.primary_niche_id)),
        ("instagram", "Connect Instagram", creator.ig_connected),
        ("rates", "Rates & preferences", bool(creator.rate_reel)),
        ("kyc", "KYC & payouts", creator.kyc_status != creator.KycStatus.NOT_SUBMITTED),
        ("agreement", "Agreement", has_current_agreement(creator.user, AgreementKind.CREATOR_PLATFORM)),
    ]


STOPWORDS = frozenset(
    "the and for with this that you your are was were have has had not but all any can our out "
    "from they them their what when where which who will would there here into just like more "
    "most some than then very about over also its it's i'm im my me we us is am be been being to "
    "of in on at by as or an a so if do does did get got how new one two use using day today".split()
)
