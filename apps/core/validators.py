"""Indian identifier validation (free, offline). Real verification against government
records comes later via a KYC provider; these catch typos and fake-looking values."""

import re

from django.core.exceptions import ValidationError

PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
_GST_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def gstin_checksum(first14):
    total = 0
    for i, ch in enumerate(first14):
        product = _GST_CHARS.index(ch) * (2 if i % 2 else 1)
        total += product // 36 + product % 36
    return _GST_CHARS[(36 - total % 36) % 36]


def validate_pan(value):
    if not PAN_RE.match(value or ""):
        raise ValidationError("Enter a valid PAN (format: ABCDE1234F).")


def validate_gstin(value):
    value = value or ""
    if not GSTIN_RE.match(value) or gstin_checksum(value[:14]) != value[14]:
        raise ValidationError("Enter a valid 15-character GSTIN.")


def validate_ifsc(value):
    if not IFSC_RE.match(value or ""):
        raise ValidationError("Enter a valid IFSC code (e.g. HDFC0001234).")


def pan_from_gstin(gstin):
    return gstin[2:12]
