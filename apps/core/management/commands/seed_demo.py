"""Create demo users and ~80 approved creators so the full flow can be tried locally.

python manage.py seed_demo            # safe to re-run
python manage.py seed_demo --creators 150
"""

import random

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.brands.models import BrandProfile
from apps.contracts.models import Agreement, AgreementKind, ConsentEvent, ConsentScope
from apps.contracts.services import render_agreement
from apps.creators.models import CreatorProfile
from apps.creators.services import authenticity_score, suggested_rate_band, text_keywords
from apps.integrations.instagram.mock import MockInstagram
from apps.niches.models import Niche, SensitiveCategory

PASSWORD = "demo-pass-123"
DEMO_CREATOR_CONSENTS = [
    ConsentScope.TERMS,
    ConsentScope.DATA_PROCESSING,
    ConsentScope.INSTAGRAM_READ,
    ConsentScope.INSTAGRAM_PUBLISH,
    ConsentScope.AI_SCRIPT_HELP,
]
FIRST = [
    "Aarav",
    "Diya",
    "Ishaan",
    "Ananya",
    "Kabir",
    "Meera",
    "Rohan",
    "Saanvi",
    "Vihaan",
    "Priya",
    "Arjun",
    "Kavya",
    "Aditya",
    "Riya",
    "Kunal",
    "Neha",
    "Siddharth",
    "Pooja",
    "Yash",
    "Tanvi",
]
LAST = ["Sharma", "Iyer", "Reddy", "Patel", "Nair", "Gupta", "Singh", "Das", "Menon", "Joshi"]
LANGS = [
    ["Hindi", "English"],
    ["English"],
    ["Tamil", "English"],
    ["Telugu", "English"],
    ["Marathi", "Hindi"],
    ["Bengali", "English"],
    ["Kannada", "English"],
    ["Hindi"],
]


class Command(BaseCommand):
    help = "Seed demo users and creators (development only)."

    def add_arguments(self, parser):
        parser.add_argument("--creators", type=int, default=80)

    @transaction.atomic
    def handle(self, *args, **opts):
        rng = random.Random(42)
        ops, _ = User.objects.get_or_create(
            email="ops@demo.local",
            defaults={"role": User.Role.OPS, "is_staff": True, "is_superuser": True, "first_name": "Ops"},
        )
        ops.set_password(PASSWORD)
        ops.save()

        brand_user, _ = User.objects.get_or_create(
            email="brand@demo.local", defaults={"role": User.Role.BRAND, "first_name": "Demo"}
        )
        brand_user.set_password(PASSWORD)
        brand_user.save()
        brand, _ = BrandProfile.objects.update_or_create(
            user=brand_user,
            defaults={
                "company_name": "GlowLeaf Naturals",
                "website": "https://glowleaf.example",
                "description": "Ayurvedic skincare for Indian skin: sunscreens, face washes, serums.",
                "gstin": "27AAPFU0939F1ZV",
                "pan": "AAPFU0939F",
                "status": BrandProfile.Status.APPROVED,
            },
        )
        brand.niches.set(Niche.objects.filter(slug__in=["skincare", "beauty"]))

        subs = list(Niche.objects.filter(parent__isnull=False).select_related("parent"))
        # Weight popular launch niches so demo campaigns have healthy pools.
        popular = [n for n in subs if n.parent.slug in {"skincare", "beauty", "fashion", "fitness", "food"}]
        mock = MockInstagram()
        created = 0
        for i in range(opts["creators"]):
            email = f"creator{i:03d}@demo.local"
            user, is_new = User.objects.get_or_create(email=email, defaults={"role": User.Role.CREATOR})
            if is_new:
                user.set_password(PASSWORD)
                user.first_name, user.last_name = rng.choice(FIRST), rng.choice(LAST)
                user.save()
            primary = rng.choice(popular if rng.random() < 0.6 else subs)
            siblings = [n for n in subs if n.parent_id == primary.parent_id and n != primary]
            handle = f"{user.first_name.lower()}.{primary.slug.replace('-', '')}{i}"
            token = mock.connect_handle(handle)
            profile = mock.fetch_profile(token)
            captions = [f"{kw} tips and honest review" for kw in primary.keywords + primary.parent.keywords]
            creator, _ = CreatorProfile.objects.update_or_create(
                user=user,
                defaults={
                    "display_name": f"{user.first_name} {user.last_name}",
                    "gender": rng.choice(["female", "male", "female"]),
                    "city": profile.audience_top_cities[0],
                    "languages": rng.choice(LANGS),
                    "primary_niche": primary,
                    "ig_username": handle,
                    "ig_user_id": token.user_id,
                    "ig_access_token": token.access_token,
                    "ig_connected_at": timezone.now(),
                    "ig_synced_at": timezone.now(),
                    "followers": profile.followers,
                    "avg_reach": profile.avg_reach,
                    "avg_views": profile.avg_views,
                    "engagement_rate": profile.engagement_rate,
                    "audience_female_pct": profile.audience_female_pct,
                    "audience_india_pct": profile.audience_india_pct,
                    "audience_top_cities": profile.audience_top_cities,
                    "audience_age": profile.audience_age,
                    "content_keywords": text_keywords(captions),
                    "sponsored_posts_30d": profile.sponsored_posts_30d,
                    "authenticity_score": authenticity_score(profile),
                    "reliability_score": round(rng.uniform(0.55, 0.98), 2),
                    "red_lines": rng.sample(SensitiveCategory.values, rng.randint(0, 3)),
                    "legal_name": f"{user.first_name} {user.last_name}",
                    # Individual PAN (4th letter P) so demo payouts use the individual TDS rate.
                    "pan": f"ABCP{user.last_name[0]}{1000 + i}K",
                    "pan_last4": f"{1000 + i}K"[-4:],
                    "kyc_status": CreatorProfile.KycStatus.VERIFIED,
                    "status": CreatorProfile.Status.APPROVED,
                },
            )
            creator.niches.set(rng.sample(siblings, min(len(siblings), rng.randint(0, 2))))
            # Demo creators skip onboarding, so record the agreement and consents it would create.
            if not Agreement.objects.filter(user=user, kind=AgreementKind.CREATOR_PLATFORM).exists():
                version, body, sha = render_agreement(
                    AgreementKind.CREATOR_PLATFORM,
                    {
                        "platform_name": settings.PLATFORM_NAME,
                        "legal_name": creator.legal_name,
                        "email": user.email,
                        "ig_username": handle,
                        "today": "demo data",
                        "verification_days": settings.VERIFICATION_DAYS,
                        "min_live_days": settings.MIN_LIVE_DAYS,
                    },
                )
                Agreement.objects.create(
                    user=user,
                    kind=AgreementKind.CREATOR_PLATFORM,
                    version=version,
                    body=body,
                    sha256=sha,
                    signed_name=creator.legal_name,
                    signed_at=timezone.now(),
                    otp_verified=False,
                )
            if not ConsentEvent.objects.filter(user=user, campaign__isnull=True).exists():
                ConsentEvent.objects.bulk_create(
                    ConsentEvent(user=user, scope=scope, action=ConsentEvent.Action.GRANTED)
                    for scope in DEMO_CREATOR_CONSENTS
                )
            low, high = suggested_rate_band(creator)
            creator.rate_reel = int(round(rng.uniform(low, high), -4))
            creator.rate_story = int(round(creator.rate_reel * 0.4, -4))
            creator.rate_post = int(round(creator.rate_reel * 0.7, -4))
            creator.save()
            created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {created} creators. Log in with ops@demo.local / brand@demo.local / "
                f"creator000@demo.local, password: {PASSWORD}"
            )
        )
