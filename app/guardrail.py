"""Rule-based first-tier detector for suicide / self-harm language.

Design notes
------------
- This is intentionally a transparent, rule-based filter so its behavior is
  reproducible, auditable, and explainable for the course's ethics framework.
- It is NOT a clinical instrument. It will produce false positives (over-
  triggering on figurative speech, song lyrics, third-person discussion) and
  false negatives (missing oblique or coded language).
- Real-world deployments must layer this with a trained classifier and an
  LLM-judge tier, and must keep a human reviewer in the loop. See
  `docs/ethics-mapping.md`.

Risk levels
-----------
- NONE   : no concerning signals detected
- LOW    : general distress / hopelessness language → log + LLM responds
- MEDIUM : explicit suicidal ideation or self-harm references → block LLM,
           return safe template, log escalation
- HIGH   : ideation combined with plan / means / time → block LLM, return
           safe template, log urgent escalation
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class RiskLevel(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


_LEVEL_RANK = {
    RiskLevel.NONE: 0,
    RiskLevel.LOW: 1,
    RiskLevel.MEDIUM: 2,
    RiskLevel.HIGH: 3,
}


_I_AM = r"(?:i['’]?m|i\s+am)"  # contracted or non-contracted

LOW_PATTERNS = [
    rf"\b{_I_AM}\s+(?:so\s+)?(?:tired|exhausted|hopeless|worthless|empty|numb|lost)\b",
    r"\bi\s+(?:can[’']?t|cannot)\s+(?:keep\s+going|do\s+this\s+anymore|take\s+(?:it|this)\s+anymore)\b",
    r"\bno\s+(?:point|reason)\s+(?:in|to)\s+(?:living|going\s+on|trying)\b",
    r"\bnothing\s+matters\b",
    r"\bgive\s+up\s+on\s+(?:life|everything)\b",
    r"\bi\s+(?:hate|don[’']?t\s+want)\s+my\s+life\b",
    r"\bi\s+feel\s+(?:so\s+)?(?:tired|exhausted|hopeless|worthless|empty|numb|lost|alone)\b",
]

MEDIUM_PATTERNS = [
    r"\b(?:want|wish|wanting|wishing)\s+(?:to|i\s+(?:could|was|were))\s+(?:die|be\s+dead|disappear|not\s+exist)\b",
    r"\bsuicid(?:e|al)\b",
    r"\bkill(?:ing)?\s+myself\b",
    r"\bend(?:ing)?\s+(?:my\s+life|it\s+all)\b",
    r"\bself[-\s]?harm\b",
    r"\bhurt(?:ing)?\s+myself\b",
    r"\bcut(?:ting)?\s+myself\b",
    r"\bdon[’']?t\s+want\s+to\s+(?:be\s+(?:here|alive)|live)\b",
    r"\bbetter\s+off\s+(?:without\s+me|dead)\b",
]

HIGH_PATTERNS = [
    # plan + lethal means
    r"\b(?:have|got|bought|stockpiled)\s+(?:the|a|some)?\s*(?:pills|gun|firearm|rope|knife|blade)\b",
    # explicit time + intent
    r"\b(?:tonight|today|right\s+now|tomorrow)\b[^.\n]{0,40}\b(?:die|kill\s+myself|end\s+(?:it|my\s+life))\b",
    # final-message signaling
    r"\bthis\s+is\s+(?:my\s+)?(?:final|last)\s+(?:message|note|goodbye)\b",
    r"\bsuicide\s+note\b",
    # explicit plan markers
    r"\bi\s+(?:have|[’']ve\s+got)\s+a\s+plan\b[^.\n]{0,40}\b(?:die|kill|end)\b",
]


def _compile(patterns: list[str]) -> list[re.Pattern[str]]:
    return [re.compile(p, re.IGNORECASE) for p in patterns]


_COMPILED = {
    RiskLevel.LOW: _compile(LOW_PATTERNS),
    RiskLevel.MEDIUM: _compile(MEDIUM_PATTERNS),
    RiskLevel.HIGH: _compile(HIGH_PATTERNS),
}


@dataclass
class GuardrailResult:
    risk: RiskLevel
    matched: list[str] = field(default_factory=list)

    @property
    def is_escalation(self) -> bool:
        return self.risk in (RiskLevel.MEDIUM, RiskLevel.HIGH)

    @property
    def block_llm(self) -> bool:
        # MEDIUM and HIGH bypass the LLM entirely. LOW is logged but allowed
        # to reach the LLM, which is given a safety-aware system prompt.
        return self.risk in (RiskLevel.MEDIUM, RiskLevel.HIGH)


def assess(text: str) -> GuardrailResult:
    if not text or not text.strip():
        return GuardrailResult(risk=RiskLevel.NONE)

    matched: list[str] = []
    highest = RiskLevel.NONE

    for level in (RiskLevel.HIGH, RiskLevel.MEDIUM, RiskLevel.LOW):
        for rx in _COMPILED[level]:
            m = rx.search(text)
            if m:
                matched.append(f"{level.value}:{m.group(0)}")
                if _LEVEL_RANK[level] > _LEVEL_RANK[highest]:
                    highest = level

    return GuardrailResult(risk=highest, matched=matched)


def assess_pattern(user_messages: list[str], threshold: int = 3) -> GuardrailResult:
    """Detect emerging concern across multiple turns.

    Single-message regex rules miss the case where someone is steadily venting
    over several turns without ever using a clearly-flagged phrase, and rules
    miss oblique buildup that only becomes meaningful in context. We treat
    `threshold` consecutive non-NONE user messages as a MEDIUM-level pattern
    so the system prompt elevates tone and the admin queue gets a heads-up.

    The pattern never invents a HIGH tier on its own — HIGH is reserved for
    explicit means/plan/time signals on a single message. Pattern caps at
    MEDIUM by design: this is a soft early-warning, not an emergency call.
    """
    if len(user_messages) < threshold:
        return GuardrailResult(risk=RiskLevel.NONE)
    window = user_messages[-threshold:]
    risks = [assess(m).risk for m in window]
    if not all(r != RiskLevel.NONE for r in risks):
        return GuardrailResult(risk=RiskLevel.NONE)
    matched = [f"pattern:{threshold}-in-a-row:{','.join(r.value for r in risks)}"]
    return GuardrailResult(risk=RiskLevel.MEDIUM, matched=matched)


def merge_risk(a: RiskLevel, b: RiskLevel) -> RiskLevel:
    return a if _LEVEL_RANK[a] >= _LEVEL_RANK[b] else b
