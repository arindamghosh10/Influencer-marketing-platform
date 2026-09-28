"""Turn a product URL into structured facts, preferring machine-readable data over guesses."""

import json
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit

import extruct
from bs4 import BeautifulSoup

from .fetch import FetchError, safe_get


@dataclass
class ProductPage:
    url: str
    title: str = ""
    description: str = ""
    brand: str = ""
    price_inr: float | None = None
    images: list[str] = field(default_factory=list)
    product_data: dict = field(default_factory=dict)
    text: str = ""  # visible text excerpt for the LLM

    def as_prompt_text(self, limit=6000):
        parts = [
            f"URL: {self.url}",
            f"Title: {self.title}",
            f"Brand: {self.brand}",
            f"Price (INR): {self.price_inr}",
            f"Description: {self.description}",
        ]
        if self.product_data:
            parts.append("Structured data: " + json.dumps(self.product_data, ensure_ascii=False)[:2500])
        parts.append("Page text: " + self.text)
        return "\n".join(parts)[:limit]


def _first(value):
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _find_product(items):
    for item in items:
        types = item.get("@type")
        types = types if isinstance(types, list) else [types]
        if "Product" in types:
            return item
        for key in ("@graph", "mainEntity"):
            nested = item.get(key)
            if isinstance(nested, list | dict):
                found = _find_product(nested if isinstance(nested, list) else [nested])
                if found:
                    return found
    return None


def parse_html(url, html):
    page = ProductPage(url=url)
    try:
        data = extruct.extract(
            html, base_url=url, syntaxes=["json-ld", "opengraph", "microdata"], uniform=True, errors="ignore"
        )
    except Exception:  # extruct raises many parser-specific errors on broken HTML
        data = {}
    product = _find_product(data.get("json-ld", []) + data.get("microdata", [])) or {}
    og = {}
    for item in data.get("opengraph", []):
        og.update({k: v for k, v in item.items() if isinstance(v, str)})

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "header"]):
        tag.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" ")).strip()

    html_title = soup.title.string.strip() if soup.title and soup.title.string else ""
    page.title = product.get("name") or og.get("og:title") or html_title
    page.description = product.get("description") or og.get("og:description") or ""
    brand = product.get("brand")
    brand_name = brand.get("name") if isinstance(brand, dict) else _first(brand)
    page.brand = brand_name or og.get("og:site_name", "")
    offers = _first(product.get("offers"))
    if isinstance(offers, dict):
        price = offers.get("price") or offers.get("lowPrice")
        try:
            page.price_inr = float(price) if price is not None else None
        except (TypeError, ValueError):
            page.price_inr = None
    images = product.get("image") or og.get("og:image")
    images = images if isinstance(images, list) else [images]
    page.images = [i if isinstance(i, str) else i.get("url", "") for i in images if i][:5]
    page.product_data = {k: v for k, v in product.items() if not k.startswith("@")}
    page.text = text[:4000]
    return page


def shopify_json_url(url):
    """Shopify serves /products/<handle>.json with clean product data."""
    parts = urlsplit(url)
    if "/products/" in parts.path and not parts.path.endswith(".json"):
        return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/") + ".json", "", ""))
    return None


def fetch_product_page(url):
    result = safe_get(url)
    if result.status >= 400:
        raise FetchError(f"The page returned an error ({result.status}).")
    page = parse_html(result.url, result.text)
    shop_url = shopify_json_url(result.url)
    if shop_url and not page.product_data:
        try:
            shop = safe_get(shop_url)
            if shop.status == 200 and "json" in shop.content_type:
                product = json.loads(shop.text).get("product", {})
                page.title = page.title or product.get("title", "")
                page.brand = page.brand or product.get("vendor", "")
                body = BeautifulSoup(product.get("body_html") or "", "html.parser").get_text(" ")
                page.description = page.description or body[:1000]
                page.product_data = {
                    "title": product.get("title"),
                    "type": product.get("product_type"),
                    "tags": product.get("tags"),
                }
        except (FetchError, ValueError):
            pass
    return page
