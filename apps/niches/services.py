from .models import Niche
from .taxonomy import TAXONOMY


def load_taxonomy():
    top_count = sub_count = 0
    for i, (slug, name, keywords, children) in enumerate(TAXONOMY):
        parent, _ = Niche.objects.update_or_create(
            slug=slug, defaults={"name": name, "keywords": keywords, "parent": None, "sort_order": i}
        )
        top_count += 1
        for j, (child_slug, child_name, child_keywords) in enumerate(children):
            Niche.objects.update_or_create(
                slug=child_slug,
                defaults={
                    "name": child_name,
                    "keywords": child_keywords,
                    "parent": parent,
                    "sort_order": j,
                },
            )
            sub_count += 1
    return top_count, sub_count


def grouped_niches():
    """[(top_level_niche, [children...]), ...] for pickers."""
    tops = Niche.objects.filter(parent__isnull=True).prefetch_related("children")
    return [(top, list(top.children.all())) for top in tops]


def phrase_count(text, phrase):
    """Whole-word, case-insensitive occurrences of `phrase` in already-lowercased `text`."""
    import re

    return len(re.findall(rf"\b{re.escape(phrase.lower())}\b", text))
