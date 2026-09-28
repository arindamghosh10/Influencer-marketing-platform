"""LLM access with automatic fallback to the free rule-based implementation."""

import logging

from apps.integrations.registry import get_provider

from .rules import RulesLLM
from .schema import LLMError

log = logging.getLogger(__name__)


def extract_brief(page, notes=""):
    """Returns (BriefData, source_name). Never raises because of the AI provider."""
    try:
        provider = get_provider("llm")
    except LLMError as exc:
        log.warning("LLM provider unavailable, using rules: %s", exc)
        provider = RulesLLM()
    if provider.name != "rules":
        try:
            return provider.extract_brief(page, notes), provider.name
        except LLMError as exc:
            log.warning("LLM extraction failed, using rules: %s", exc)
    return RulesLLM().extract_brief(page, notes), "rules"
