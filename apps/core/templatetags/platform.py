from django import template

from apps.core.money import format_inr

register = template.Library()


@register.filter
def inr(paise):
    return format_inr(paise)


@register.filter
def pct(value, digits=1):
    if value is None:
        return "—"
    return f"{float(value):.{int(digits)}f}%"


@register.filter
def compact(n):
    """1234 -> 1.2k, 1234567 -> 12.3L (Indian lakh), for follower/reach counts."""
    if n is None:
        return "—"
    n = int(n)
    if n >= 10_000_000:
        return f"{n / 10_000_000:.1f}Cr"
    if n >= 100_000:
        return f"{n / 100_000:.1f}L"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)
