"""Instagram API with Instagram Login (official Meta API, free).

Requires a Meta app with Instagram permissions approved through App Review. Until approved,
only accounts added as testers on the app can connect. Endpoints follow Meta's documentation for
the "Instagram API with Instagram Login" product; verify against the current docs when the app
is set up, since Meta changes metric names between API versions.
"""

from datetime import timedelta
from urllib.parse import urlencode

import httpx
from django.conf import settings
from django.utils import timezone

from .base import InstagramError, InstagramProfile, InstagramProvider, InstagramToken

AUTH_URL = "https://www.instagram.com/oauth/authorize"
TOKEN_URL = "https://api.instagram.com/oauth/access_token"
GRAPH = "https://graph.instagram.com"
SCOPES = [
    "instagram_business_basic",
    "instagram_business_manage_insights",
    "instagram_business_content_publish",
]


class GraphInstagram(InstagramProvider):
    uses_oauth = True

    def __init__(self):
        self.client_id = settings.INSTAGRAM_APP_ID
        self.client_secret = settings.INSTAGRAM_APP_SECRET
        if not (self.client_id and self.client_secret):
            raise InstagramError("INSTAGRAM_APP_ID / INSTAGRAM_APP_SECRET are not configured")

    def authorize_url(self, state, redirect_uri):
        query = urlencode(
            {
                "client_id": self.client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": ",".join(SCOPES),
                "state": state,
            }
        )
        return f"{AUTH_URL}?{query}"

    def exchange_code(self, code, redirect_uri):
        with httpx.Client(timeout=15) as client:
            short = client.post(
                TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri,
                    "code": code,
                },
            )
            self._check(short)
            short_data = short.json()
            long = client.get(
                f"{GRAPH}/access_token",
                params={
                    "grant_type": "ig_exchange_token",
                    "client_secret": self.client_secret,
                    "access_token": short_data["access_token"],
                },
            )
            self._check(long)
            long_data = long.json()
        return InstagramToken(
            access_token=long_data["access_token"],
            user_id=str(short_data["user_id"]),
            expires_at=timezone.now() + timedelta(seconds=int(long_data.get("expires_in", 0))),
        )

    def fetch_profile(self, token):
        with httpx.Client(base_url=GRAPH, timeout=20) as client:
            me = client.get(
                "/me",
                params={
                    "fields": "user_id,username,followers_count,media_count",
                    "access_token": token.access_token,
                },
            )
            self._check(me)
            me = me.json()
            media = client.get(
                "/me/media",
                params={
                    "fields": "id,caption,like_count,comments_count,timestamp",
                    "limit": 25,
                    "access_token": token.access_token,
                },
            )
            self._check(media)
            items = media.json().get("data", [])
            demographics = self._demographics(client, token)

        followers = int(me.get("followers_count") or 0)
        engagements = [int(m.get("like_count") or 0) + int(m.get("comments_count") or 0) for m in items]
        avg_eng = sum(engagements) / len(engagements) if engagements else 0
        # Reach per post needs per-media insights calls; approximate until the sync job adds them.
        est_reach = int(followers * 0.3)
        return InstagramProfile(
            user_id=str(me.get("user_id") or token.user_id),
            username=me.get("username", ""),
            followers=followers,
            media_count=int(me.get("media_count") or 0),
            avg_reach=est_reach,
            avg_views=est_reach,
            engagement_rate=round(avg_eng / est_reach * 100, 2) if est_reach else 0.0,
            audience_female_pct=demographics.get("female_pct", 50.0),
            audience_india_pct=demographics.get("india_pct", 0.0),
            audience_top_cities=demographics.get("cities", []),
            audience_age=demographics.get("age", {}),
            recent_captions=[m.get("caption") or "" for m in items],
        )

    def _demographics(self, client, token):
        """Follower demographics (only available above Meta's follower threshold)."""
        out = {}
        for breakdown in ("gender", "country", "city", "age"):
            resp = client.get(
                "/me/insights",
                params={
                    "metric": "follower_demographics",
                    "period": "lifetime",
                    "metric_type": "total_value",
                    "breakdown": breakdown,
                    "access_token": token.access_token,
                },
            )
            if resp.status_code != 200:
                continue
            try:
                results = resp.json()["data"][0]["total_value"]["breakdowns"][0]["results"]
            except (KeyError, IndexError):
                continue
            counts = {r["dimension_values"][0]: r["value"] for r in results}
            total = sum(counts.values()) or 1
            if breakdown == "gender":
                out["female_pct"] = round(counts.get("F", 0) / total * 100, 1)
            elif breakdown == "country":
                out["india_pct"] = round(counts.get("IN", 0) / total * 100, 1)
            elif breakdown == "city":
                top = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:5]
                out["cities"] = [name.split(",")[0] for name, _ in top]
            else:
                out["age"] = {k: round(v / total * 100, 1) for k, v in counts.items()}
        return out

    @staticmethod
    def _check(resp):
        if resp.status_code >= 400:
            raise InstagramError(f"Instagram API error {resp.status_code}: {resp.text[:300]}")
