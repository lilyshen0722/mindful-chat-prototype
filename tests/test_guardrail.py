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


def test_medium_catches_euphemistic_end_phrasings():
    # These were missed in an actual user conversation: the regex only
    # caught "end my life" / "end it all" but not "end all of this",
    # "put an end to everything", or the contextualized "ending this".
    # go_emotions also misses these — it rates them as 'desire'.
    cases = [
        "I want to end all of this",
        "I want to put an end to everything",
        "by 'ending this', I really mean it, put an end to everything",
        "I just want to end it all tonight",
        "I can't go on like this",
        "I cannot keep living this way",
    ]
    for text in cases:
        r = assess(text)
        assert r.risk == RiskLevel.MEDIUM, f"expected MEDIUM for {text!r}, got {r.risk.value} ({r.matched})"


def test_medium_phrasings_dont_overtrigger():
    # Make sure the broader MEDIUM patterns don't fire on benign uses.
    cases = [
        "Let me end this conversation, thanks for the help",
        "I want to end this lecture early",
        "How do I put an end to my subscription?",
    ]
    for text in cases:
        r = assess(text)
        assert r.risk == RiskLevel.NONE, f"unexpected {r.risk.value} for {text!r} ({r.matched})"


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


def test_low_catches_sad_depressed_lonely_phrasings():
    # These were missed by the original regex set; documented in
    # docs/ethics-mapping.md as a known gap and patched iteratively.
    cases = [
        "feeling really down today, can you help me think of something funny?",
        "I'm still quite sad, I don't have any friends at school",
        "I am so depressed lately",
        "I'm lonely and overwhelmed",
        "I feel really down",
        "I don't have any friends",
        "no one understands me",
        "I'm pretty broken right now",
    ]
    for text in cases:
        r = assess(text)
        assert r.risk == RiskLevel.LOW, f"expected LOW for {text!r}, got {r.risk.value} ({r.matched})"


def test_neutral_phrasings_still_pass():
    # Regression check — make sure the broader LOW patterns don't fire on
    # normal conversation.
    cases = [
        "Hi can you suggest a good study schedule for finals?",
        "Tell me a joke please",
        "What's a good recipe for chili?",
        "I am happy with the project",
        "I feel great today",
    ]
    for text in cases:
        r = assess(text)
        assert r.risk == RiskLevel.NONE, f"unexpected {r.risk.value} for {text!r} ({r.matched})"


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
