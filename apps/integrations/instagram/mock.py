"""Development stand-in for the Instagram API.

Produces stable, realistic-looking stats from the handle so the whole product can be used and
tested before Meta App Review is complete.
"""

import hashlib
import random
import re
import secrets
import time

from .base import InstagramProfile, InstagramProvider, InstagramToken, MediaStatus, PublishedMedia

# Media ids of posts to treat as deleted (tests and ops "simulate removal" use this).
REMOVED: set[str] = set()

CITIES = [
    "Mumbai",
    "Delhi",
    "Bengaluru",
    "Hyderabad",
    "Chennai",
    "Kolkata",
    "Pune",
    "Ahmedabad",
    "Jaipur",
    "Lucknow",
    "Chandigarh",
    "Kochi",
    "Indore",
    "Surat",
]

CAPTION_TOPICS = [
    "skincare routine",
    "sunscreen",
    "acne",
    "makeup look",
    "hair oil",
    "saree styling",
    "streetwear",
    "gym workout",
    "yoga flow",
    "protein",
    "home cooking recipe",
    "street food",
    "coffee",
    "budget travel",
    "trek",
    "smartphone review",
    "earbuds",
    "bgmi",
    "baby care",
    "saving money",
    "mutual fund",
    "exam tips",
    "day in my life vlog",
    "room decor",
    "plants",
    "dog",
    "cat",
    "bike ride",
    "comedy skit",
    "dance",
    "cricket",
    "painting",
    "diy craft",
]


class MockInstagram(InstagramProvider):
    uses_oauth = False

    def connect_handle(self, handle):
        handle = handle.strip().lstrip("@").lower()
        return InstagramToken(access_token=f"mock:{handle}", user_id=f"mock-{handle}", expires_at=None)

    def fetch_profile(self, token):
        handle = token.access_token.removeprefix("mock:")
        rng = random.Random(int(hashlib.sha256(handle.encode()).hexdigest(), 16))
        followers = int(rng.choice([rng.randint(1_500, 9_900), rng.randint(10_000, 95_000)]))
        reach = int(followers * rng.uniform(0.18, 0.6))
        er = round(rng.uniform(1.2, 8.5), 2)
        topics = rng.sample(CAPTION_TOPICS, 3)
        captions = [f"My honest {t} update #{t.replace(' ', '')}" for t in topics for _ in range(3)]
        return InstagramProfile(
            user_id=token.user_id,
            username=handle,
            followers=followers,
            media_count=rng.randint(40, 900),
            avg_reach=reach,
            avg_views=int(reach * rng.uniform(1.1, 2.4)),
            engagement_rate=er,
            audience_female_pct=round(rng.uniform(15, 85), 1),
            audience_india_pct=round(rng.uniform(70, 97), 1),
            audience_top_cities=rng.sample(CITIES, 4),
            audience_age={"13-17": 4, "18-24": 38, "25-34": 41, "35-44": 12, "45+": 5},
            recent_captions=captions,
            sponsored_posts_30d=rng.randint(0, 6),
        )

    # Publishing. Media ids embed the publish time so metrics can grow with the post's age
    # without any shared state between web and worker processes.

    def publish(self, token, media_url, caption, kind):
        media_id = f"mock{int(time.time())}x{secrets.token_hex(4)}"
        return PublishedMedia(media_id=media_id, permalink=f"https://www.instagram.com/reel/{media_id}/")

    def find_media_by_permalink(self, token, permalink):
        match = re.search(r"instagram\.com/(?:reel|reels|p)/([\w-]+)", permalink or "")
        if not match:
            return None
        return PublishedMedia(media_id=match.group(1), permalink=permalink)

    def media_status(self, token, media_id):
        if media_id in REMOVED:
            return MediaStatus(exists=False)
        stamp = re.match(r"mock(\d+)x", media_id)
        age_hours = (time.time() - int(stamp.group(1))) / 3600 if stamp else 72
        rng = random.Random(media_id)
        growth = min(1.0, 0.35 + max(age_hours, 0) / 168)  # most reach arrives in week one
        reach = int(rng.randint(1_500, 25_000) * growth)
        likes = int(reach * rng.uniform(0.03, 0.09))
        return MediaStatus(
            exists=True,
            caption=None,  # the mock can't know the caption; verification skips that check
            permalink=f"https://www.instagram.com/reel/{media_id}/",
            reach=reach,
            views=int(reach * rng.uniform(1.2, 2.2)),
            likes=likes,
            comments=int(likes * rng.uniform(0.03, 0.12)),
            shares=int(likes * rng.uniform(0.05, 0.2)),
            saves=int(likes * rng.uniform(0.08, 0.3)),
        )
