import dns.exception
import dns.resolver
from django.utils import timezone


def check_domain_txt(brand):
    """True if the brand's domain has our TXT verification record."""
    if not brand.domain or not brand.domain_verification_token:
        return False
    try:
        answers = dns.resolver.resolve(brand.domain, "TXT", lifetime=5)
    except (dns.exception.DNSException, OSError):
        return False
    expected = brand.dns_txt_record
    for rdata in answers:
        value = b"".join(rdata.strings).decode(errors="ignore")
        if value.strip() == expected:
            brand.domain_verified_at = timezone.now()
            brand.save(update_fields=["domain_verified_at", "updated_at"])
            return True
    return False


def onboarding_steps(brand):
    from apps.contracts.models import AgreementKind
    from apps.contracts.services import has_current_agreement

    return [
        ("profile", "Company profile", bool(brand.pk and brand.gstin)),
        ("agreement", "Brand agreement", has_current_agreement(brand.user, AgreementKind.BRAND_PLATFORM)),
    ]
