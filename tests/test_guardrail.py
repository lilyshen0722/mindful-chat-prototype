"""Unit tests for the rule-based crisis-language detector.

Each risk level has positive and negative cases. Phrasings here are
deliberately benign descriptions of categories — not real-world slurs or
specific instructions — and aim to verify the *category* is detected, not to
catalogue every variant.
"""
from app.guardrail import RiskLevel, assess, assess_pattern, merge_risk


def test_empty_message_is_none():
    assert assess("").risk == RiskLevel.NONE
    assert assess("   ").risk == RiskLevel.NONE


def test_neutral_message_is_none():
    r = assess("Hello, can you help me plan a study schedule for finals?")
    assert r.risk == RiskLevel.NONE
    assert r.matched == []


def test_low_distress_signals():
    r = assess("I'm so tired and nothing matters anymore.")
    assert r.risk == RiskLevel.LOW
    assert any(s.startswith("low:") for s in r.matched)


def test_medium_ideation_signals():
    r = assess("Sometimes I want to die.")
    assert r.risk == RiskLevel.MEDIUM
    assert r.is_escalation
    assert r.block_llm


def test_medium_explicit_keyword():
    r = assess("I keep thinking about suicide.")
    assert r.risk == RiskLevel.MEDIUM
    assert r.block_llm


def test_high_plan_plus_means():
    r = assess("I have the pills and I'm going to use them.")
    assert r.risk == RiskLevel.HIGH
    assert r.is_escalation
    assert r.block_llm


def test_high_final_message_signal():
    r = assess("This is my last goodbye.")
    assert r.risk == RiskLevel.HIGH
    assert r.block_llm


def test_high_overrides_lower_signals_when_both_present():
    r = assess(
        "I'm so tired and worthless. Tonight I am going to end my life."
    )
    assert r.risk == RiskLevel.HIGH


def test_low_does_not_block_llm():
    r = assess("I'm exhausted and lost.")
    assert r.risk == RiskLevel.LOW
    assert not r.block_llm
    assert not r.is_escalation


def test_pattern_requires_threshold_messages():
    # Two LOW messages aren't enough to trip a pattern (default threshold=3).
    r = assess_pattern(["I'm exhausted", "nothing matters"])
    assert r.risk == RiskLevel.NONE


def test_pattern_three_consecutive_low_elevates_to_medium():
    r = assess_pattern([
        "I'm exhausted",
        "nothing matters anymore",
        "I'm so tired",
    ])
    assert r.risk == RiskLevel.MEDIUM
    assert any("pattern:" in m for m in r.matched)


def test_pattern_breaks_on_neutral_message():
    r = assess_pattern([
        "I'm exhausted",
        "what's a good study schedule?",  # neutral message resets the pattern
        "I'm so tired",
    ])
    assert r.risk == RiskLevel.NONE


def test_merge_risk_returns_higher():
    assert merge_risk(RiskLevel.LOW, RiskLevel.MEDIUM) == RiskLevel.MEDIUM
    assert merge_risk(RiskLevel.HIGH, RiskLevel.LOW) == RiskLevel.HIGH
    assert merge_risk(RiskLevel.NONE, RiskLevel.NONE) == RiskLevel.NONE
