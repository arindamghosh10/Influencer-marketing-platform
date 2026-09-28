"""GST and TDS rules (India). Confirm rates and sections with your CA before going live."""

from dataclasses import dataclass

from django.conf import settings

from apps.core.pricing import gst, tds


@dataclass
class GstSplit:
    cgst: int
    sgst: int
    igst: int

    @property
    def total(self):
        return self.cgst + self.sgst + self.igst


def gst_split(amount, buyer_gstin):
    """Intra-state supply → CGST + SGST (half each); inter-state → IGST.

    The buyer's state is the first two digits of their GSTIN. Without a GSTIN, the supply is
    treated as intra-state (place of supply = our state).
    """
    total = gst(amount, settings.GST_RATE_BPS)
    buyer_state = (buyer_gstin or "")[:2] or settings.PLATFORM_STATE_CODE
    if buyer_state == settings.PLATFORM_STATE_CODE:
        cgst = total // 2
        return GstSplit(cgst=cgst, sgst=total - cgst, igst=0)
    return GstSplit(cgst=0, sgst=0, igst=total)


def tds_rate_bps(creator):
    """Individuals/HUFs (4th PAN character P or H) get the lower rate."""
    pan = (creator.pan or "").upper()
    if len(pan) == 10 and pan[3] in "PH":
        return settings.TDS_RATE_BPS_INDIVIDUAL
    return settings.TDS_RATE_BPS_COMPANY


@dataclass
class PayoutBreakdown:
    gross: int
    gst: int
    tds: int
    tds_rate_bps: int

    @property
    def net(self):
        return self.gross + self.gst - self.tds


def payout_breakdown(creator, fee):
    """What the creator receives for `fee`. TDS is deducted on the fee excluding GST."""
    rate = tds_rate_bps(creator)
    creator_gst = gst(fee, settings.GST_RATE_BPS) if creator.gstin else 0
    return PayoutBreakdown(gross=fee, gst=creator_gst, tds=tds(fee, rate), tds_rate_bps=rate)
