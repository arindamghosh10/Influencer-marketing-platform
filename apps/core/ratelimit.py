"""Small fixed-window rate limiter on Django's cache.

Local development uses the in-memory cache; production should set CACHE_URL to Redis so limits
are shared across workers. Only POST requests count, so pages still load for someone who is
throttled and they see a clear message instead of an error.
"""

from functools import wraps

from django.core.cache import cache
from django.shortcuts import render

from .events import client_ip


def hit(key, limit, window):
    """Count one attempt; True while the key is within its limit."""
    cache_key = f"rl:{key}"
    cache.add(cache_key, 0, window)
    try:
        count = cache.incr(cache_key)
    except ValueError:  # expired between add and incr
        cache.set(cache_key, 1, window)
        count = 1
    return count <= limit


def is_blocked(key, limit):
    return (cache.get(f"rl:{key}") or 0) >= limit


def reset(key):
    cache.delete(f"rl:{key}")


def too_many(request, minutes):
    return render(request, "core/rate_limited.html", {"minutes": minutes}, status=429)


def ratelimit(scope, limit, window, by="ip"):
    """Limit POSTs to a view per client IP ("ip") or per logged-in user ("user")."""

    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if request.method == "POST":
                who = (
                    request.user.pk if by == "user" and request.user.is_authenticated else client_ip(request)
                )
                if not hit(f"{scope}:{who}", limit, window):
                    return too_many(request, max(1, window // 60))
            return view(request, *args, **kwargs)

        return wrapped

    return decorator
