from pydantic import BaseModel, Field


class BriefData(BaseModel):
    """What we understood about the product. Brands review and confirm this before matching."""

    product_name: str = Field(description="Product name")
    brand_name: str = Field(default="", description="Brand name")
    category: str = Field(default="", description="Short product category, e.g. 'sunscreen'")
    summary: str = Field(default="", description="2-3 sentence plain-language summary")
    price_inr: float | None = Field(default=None, description="Price in INR if known")
    key_features: list[str] = Field(default_factory=list, description="Up to 6 features")
    benefits: list[str] = Field(default_factory=list, description="Up to 6 customer benefits")
    claims: list[str] = Field(
        default_factory=list, description="Factual claims made by the brand (e.g. 'SPF 50')"
    )
    target_audience: str = Field(default="", description="Who the product is for")
    niche_slugs: list[str] = Field(
        default_factory=list, description="1-3 slugs from the provided niche list, best first"
    )
    keywords: list[str] = Field(default_factory=list, description="10-20 lowercase topic keywords")
    restricted_category: str = Field(
        default="", description="One of the provided sensitive category codes, or empty"
    )
    risky_claims: list[str] = Field(
        default_factory=list,
        description="Claims that need proof or are not allowed in ads (cures, guarantees, "
        "'clinically proven', 'no side effects', etc.)",
    )


class LLMError(Exception):
    pass
