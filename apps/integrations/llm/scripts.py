"""Creator-facing brief: hooks, script outline, shot list and caption for one creator."""

from pydantic import BaseModel, Field


class CreatorBrief(BaseModel):
    hooks: list[str] = Field(default_factory=list, description="3 opening lines for the first 2 seconds")
    script_outline: list[str] = Field(default_factory=list, description="4-6 beats of the video")
    shot_list: list[str] = Field(default_factory=list, description="4-6 shots to film")
    caption: str = Field(default="", description="Instagram caption including disclosure")
    hashtags: list[str] = Field(default_factory=list)


def creator_brief_prompt(brief, campaign, creator):
    languages = ", ".join(creator.languages) or "English"
    return (
        "Write a UGC video brief for an Indian Instagram creator.\n"
        f"Creator style: niche {creator.primary_niche}, languages {languages}. Keep it natural, "
        "first-person, honest. Mix Hindi and English (Hinglish) if Hindi is one of the languages.\n"
        f"Product: {brief['product_name']} by {brief.get('brand_name', '')}. {brief.get('summary', '')}\n"
        f"Benefits: {', '.join(brief.get('benefits', []))}\n"
        f"Must say: {campaign.must_say or 'nothing specific'}\n"
        f"Must NOT say: {campaign.must_not_say or 'nothing specific'}; never use claims needing proof: "
        f"{', '.join(brief.get('risky_claims', [])) or 'none'}\n"
        "The caption must start with '#ad' or 'Paid partnership with' the brand."
    )


def template_creator_brief(brief, campaign, creator):
    name = brief.get("product_name", "the product")
    brand = brief.get("brand_name") or "the brand"
    benefits = brief.get("benefits") or brief.get("key_features") or []
    return CreatorBrief(
        hooks=[
            f"I tried {name} for a week, here's my honest take…",
            f"Things I wish I knew before buying {name}",
            f"Is {name} actually worth it? Let's see.",
        ],
        script_outline=[
            "Hook (first 2 seconds): show the product or the problem it solves",
            "Your context: why you needed something like this",
            "Show it in use, close-up",
            *[f"Point out: {b}" for b in benefits[:2]],
            "Your honest verdict + who it's for",
            "Call to action (link in bio / code)",
        ],
        shot_list=[
            "Product unboxing / packshot",
            "Using the product",
            "Close-up of texture/details",
            "Talking to camera for the verdict",
        ],
        caption=f"#ad Paid partnership with {brand}. My honest review of {name}.",
        hashtags=["ad", "sponsored"] + [k.replace(" ", "") for k in brief.get("keywords", [])[:5]],
    )
