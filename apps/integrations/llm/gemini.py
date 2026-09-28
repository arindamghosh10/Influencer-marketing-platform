"""Google Gemini (free tier) implementation.

Free-tier note: Google's free tier is rate-limited and Google may use free-tier prompts to
improve its products. Don't send personal data here; product pages are public information.
Switch to a paid tier or another provider for confidential brand data.
"""

import json
import logging

from django.conf import settings
from google import genai
from google.genai import types

from apps.niches.models import Niche, SensitiveCategory

from .rules import RulesLLM
from .schema import BriefData, LLMError

log = logging.getLogger(__name__)

SYSTEM = (
    "You analyse a product page for an Indian influencer-marketing platform. Extract facts only "
    "from the page; never invent features, prices or claims. Choose niche slugs only from the "
    "list given. Flag any claim an Indian advertising regulator (ASCI) would require proof for "
    "as a risky claim. Use a sensitive category code only if the product clearly belongs to it."
)


def _niche_catalogue():
    rows = Niche.objects.filter(parent__isnull=False).select_related("parent")
    return "\n".join(f"{n.slug}: {n.parent.name} > {n.name}" for n in rows)


class GeminiLLM:
    name = "gemini"

    def __init__(self):
        if not settings.GEMINI_API_KEY:
            raise LLMError("GEMINI_API_KEY is not set")
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.model = settings.GEMINI_MODEL

    def _generate(self, prompt, schema):
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM,
                    response_mime_type="application/json",
                    response_schema=schema,
                    temperature=0.2,
                ),
            )
        except Exception as exc:  # SDK raises several error classes (quota, network, 5xx)
            raise LLMError(f"Gemini request failed: {exc}") from exc
        parsed = response.parsed
        if parsed is None:
            try:
                parsed = schema.model_validate(json.loads(response.text or ""))
            except (ValueError, TypeError) as exc:
                raise LLMError("Gemini returned an unreadable answer") from exc
        return parsed

    def extract_brief(self, page, notes=""):
        prompt = (
            f"Niche list (slug: path):\n{_niche_catalogue()}\n\n"
            f"Sensitive category codes: {', '.join(SensitiveCategory.values)}\n\n"
            f"Extra notes from the brand: {notes or 'none'}\n\n"
            f"Product page:\n{page.as_prompt_text()}"
        )
        brief = self._generate(prompt, BriefData)
        valid = set(Niche.objects.filter(slug__in=brief.niche_slugs).values_list("slug", flat=True))
        brief.niche_slugs = [s for s in brief.niche_slugs if s in valid][:3]
        if brief.restricted_category not in SensitiveCategory.values:
            brief.restricted_category = ""
        # Keep the deterministic safety checks even when the model misses something.
        fallback = RulesLLM().extract_brief(page, notes)
        brief.restricted_category = brief.restricted_category or fallback.restricted_category
        brief.risky_claims = list(dict.fromkeys(brief.risky_claims + fallback.risky_claims))[:8]
        if not brief.niche_slugs:
            brief.niche_slugs = fallback.niche_slugs
        if brief.price_inr is None:
            brief.price_inr = page.price_inr
        return brief

    def creator_brief(self, brief, campaign, creator):
        from .scripts import CreatorBrief, creator_brief_prompt

        return self._generate(creator_brief_prompt(brief, campaign, creator), CreatorBrief)
