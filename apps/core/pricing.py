"""Pricing. All amounts in integer paise.

The platform is the principal: the brand pays a campaign price and the platform pays each
creator their fee. Brand price = creator fee ÷ (1 − margin), rounded up to the next ₹10.
The margin is never exposed to either side; see apps.matching.views_models.
"""

import math

ROUND_TO = 1_000  # ₹10 in paise


def brand_price(creator_fee, margin_bps):
    if not 0 <= margin_bps < 10_000:
        raise ValueError("margin_bps must be in [0, 10000)")
    raw = math.ceil(creator_fee * 10_000 / (10_000 - margin_bps))
    return math.ceil(raw / ROUND_TO) * ROUND_TO


def gst(amount, rate_bps):
    return round(amount * rate_bps / 10_000)


def tds(fee, rate_bps):
    return round(fee * rate_bps / 10_000)
