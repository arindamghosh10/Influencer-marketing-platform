from dataclasses import dataclass, field
from datetime import datetime


class InstagramError(Exception):
    pass


@dataclass
class InstagramProfile:
    user_id: str
    username: str
    followers: int
    media_count: int
    avg_reach: int
    avg_views: int
    engagement_rate: float  # engagements / reach * 100
    audience_female_pct: float
    audience_india_pct: float
    audience_top_cities: list[str]
    audience_age: dict[str, float]
    recent_captions: list[str] = field(default_factory=list)
    sponsored_posts_30d: int = 0


@dataclass
class InstagramToken:
    access_token: str
    user_id: str
    expires_at: datetime | None


@dataclass
class PublishedMedia:
    media_id: str
    permalink: str


@dataclass
class MediaStatus:
    exists: bool
    caption: str | None = None  # None = provider can't tell
    permalink: str = ""
    reach: int = 0
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    saves: int = 0


class InstagramProvider:
    """Interface. `uses_oauth` False means the connect screen asks for a handle (mock/dev)."""

    uses_oauth = True

    def authorize_url(self, state: str, redirect_uri: str) -> str:
        raise NotImplementedError

    def exchange_code(self, code: str, redirect_uri: str) -> InstagramToken:
        raise NotImplementedError

    def connect_handle(self, handle: str) -> InstagramToken:
        raise NotImplementedError

    def fetch_profile(self, token: InstagramToken) -> InstagramProfile:
        raise NotImplementedError

    def refresh_token(self, token: InstagramToken) -> InstagramToken:
        """Extend a long-lived token (valid 60 days; must be refreshed before it expires)."""
        return token

    def publish(self, token: InstagramToken, media_url: str, caption: str, kind: str) -> PublishedMedia:
        """kind: "reel" | "post" | "story". media_url must be publicly reachable by Meta."""
        raise NotImplementedError

    def find_media_by_permalink(self, token: InstagramToken, permalink: str) -> PublishedMedia | None:
        raise NotImplementedError

    def media_status(self, token: InstagramToken, media_id: str) -> MediaStatus:
        raise NotImplementedError
