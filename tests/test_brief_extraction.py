import pytest

from apps.integrations import llm
from apps.integrations.product_page import ProductPage


@pytest.mark.django_db
def test_rules_extraction_maps_niche_and_flags_claims():
    page = ProductPage(
        url="https://x.example",
        title="SunShield SPF 50 sunscreen",
        brand="GlowLeaf",
        description="Gel sunscreen that is clinically proven to cure tanning. 100% safe, no side effects.",
        text="Sunscreen with SPF 50 for daily skincare.",
    )
    brief, source = llm.extract_brief(page)
    assert source == "rules"
    assert brief.niche_slugs[0] == "sun-care"
    assert brief.risky_claims
    assert brief.restricted_category == ""


@pytest.mark.django_db
def test_rules_detect_restricted_category():
    page = ProductPage(url="", title="Premium Whisky Gift Box", text="Aged single malt whisky")
    brief, _ = llm.extract_brief(page)
    assert brief.restricted_category == "alcohol"


@pytest.mark.django_db
def test_gemini_without_key_falls_back_to_rules(settings):
    settings.LLM_PROVIDER = "gemini"
    settings.GEMINI_API_KEY = ""
    brief, source = llm.extract_brief(ProductPage(url="", title="Yoga mat", text="yoga asana mat"))
    assert source == "rules"
    assert "yoga" in brief.niche_slugs


@pytest.mark.django_db
def test_gemini_errors_fall_back_to_rules(settings, monkeypatch):
    from apps.integrations.llm import gemini
    from apps.integrations.llm.schema import LLMError

    settings.LLM_PROVIDER = "gemini"
    settings.GEMINI_API_KEY = "test-key"

    def boom(self, prompt, schema):
        raise LLMError("quota exceeded")

    monkeypatch.setattr(gemini.GeminiLLM, "_generate", boom)
    _brief, source = llm.extract_brief(ProductPage(url="", title="Gym protein", text="gym protein"))
    assert source == "rules"


@pytest.mark.django_db
def test_gemini_result_is_sanitised(settings, monkeypatch):
    from apps.integrations.llm import gemini
    from apps.integrations.llm.schema import BriefData

    settings.LLM_PROVIDER = "gemini"
    settings.GEMINI_API_KEY = "test-key"

    def fake(self, prompt, schema):
        return BriefData(
            product_name="Serum",
            niche_slugs=["made-up", "anti-ageing"],
            restricted_category="nonsense",
            risky_claims=[],
        )

    monkeypatch.setattr(gemini.GeminiLLM, "_generate", fake)
    page = ProductPage(url="", title="Retinol serum", text="Guaranteed results in 3 days")
    brief, source = llm.extract_brief(page)
    assert source == "gemini"
    assert brief.niche_slugs == ["anti-ageing"]
    assert brief.restricted_category == ""
    assert brief.risky_claims  # deterministic check added what the model missed


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Hydrating face serum with vitamin C", ""),
        ("Dark rum gift pack", "alcohol"),
        ("Place a bet on the match", "gambling"),
        ("Alphabet learning cards for kids", ""),
    ],
)
def test_sensitive_category_uses_whole_words(text, expected):
    from apps.integrations.llm.rules import detect_sensitive_category

    assert detect_sensitive_category(text) == expected


@pytest.mark.django_db
def test_niche_keywords_match_whole_words_only():
    page = ProductPage(url="", title="Skin care kit", text="skincare category for daily care")
    brief, _ = llm.extract_brief(page)
    assert "cars" not in brief.niche_slugs and "cats" not in brief.niche_slugs


@pytest.mark.django_db
def test_parent_keywords_alone_do_not_add_sub_niches():
    page = ProductPage(url="", title="SPF 50 gel sunscreen", text="sunscreen for oily skin")
    brief, _ = llm.extract_brief(page)
    assert brief.niche_slugs == ["sun-care"]
