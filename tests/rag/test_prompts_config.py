"""
Unit tests for rag/prompts/config.py (SCRUM-254).

Guards the shared temperature constant so future LLM call sites
(classifier.py, verifier.py) cannot drift away from temperature=0.
"""

from rag.prompts.config import LLM_TEMPERATURE


def test_llm_temperature_is_zero():
    assert LLM_TEMPERATURE == 0


def test_llm_temperature_is_numeric():
    assert isinstance(LLM_TEMPERATURE, (int, float))
