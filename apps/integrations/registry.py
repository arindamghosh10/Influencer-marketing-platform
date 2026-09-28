"""Adapter registry: each external service has several implementations, chosen by a setting.

Swapping a free implementation for a paid one later is a settings change, not a code change.
"""

from django.conf import settings
from django.utils.module_loading import import_string

PROVIDERS = {
    "instagram": {
        "setting": "INSTAGRAM_PROVIDER",
        "choices": {
            "mock": "apps.integrations.instagram.mock.MockInstagram",
            "graph": "apps.integrations.instagram.graph.GraphInstagram",
        },
    },
    "llm": {
        "setting": "LLM_PROVIDER",
        "choices": {
            "rules": "apps.integrations.llm.rules.RulesLLM",
            "gemini": "apps.integrations.llm.gemini.GeminiLLM",
        },
    },
}


def get_provider(service):
    spec = PROVIDERS[service]
    name = getattr(settings, spec["setting"])
    try:
        path = spec["choices"][name]
    except KeyError as exc:
        raise ValueError(f"Unknown {service} provider {name!r}") from exc
    return import_string(path)()
