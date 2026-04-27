"""Third-tier LLM-judge for the safety pipeline.

Consulted only when the regex tier (`app.guardrail.assess`) AND the ML
classifier (`app.ml_classifier.assess_ml`) both return ``NONE``. Asks a
configured LLM (default: same OpenRouter model as the chat) to read the
message holistically and return a structured ``{risk, reason}`` JSON
classification.

Why a third tier
================

The first two tiers have known structural gaps:

- The regex tier misses semantic rephrasings ("end all of this", "put an
  end to everything") until each is enumerated.
- ``go_emotions`` reads euphemistic suicidality as ``desire`` — a label
  we deliberately exclude from our distress set because adding it would
  fire on every benign want.

A judge LLM can read the message holistically and catch these natively.

Design constraints (documented in ``docs/ethics-mapping.md``):

- **Cap at MEDIUM.** ``HIGH`` stays reserved for explicit plan + means +
  time signals from the regex tier; an LLM judge shouldn't fabricate
  clinical urgency from semantic understanding alone.
- **Conservative by prompt.** The system prompt explicitly tells the
  judge to favor ``NONE`` on ambiguous benign uses ("end this Zoom
  call").
- **Fail open.** If the judge model is unreachable, returns malformed
  output, or the API key is missing, log a warning and return ``NONE``;
  the first two tiers still ran.
- **Reasoning is logged.** The judge's one-sentence ``reason`` is
  surfaced in ``matched_signals`` so a reviewer can audit *why* it
  fired.
- **Latency disclosure.** A judge call adds ~1–2s before the chat
  stream starts. Toggle off via ``ENABLE_LLM_JUDGE=false`` for
  latency-sensitive demos.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

import httpx

from .config import settings
from .guardrail import RiskLevel

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a safety classifier reviewing a single user message from a chat application.

Classify the message into one of three risk levels for self-harm or suicidal distress:

- NONE: ordinary conversation, no distress signals.
- LOW: signs of distress, sadness, hopelessness, social isolation, frustration with school/work/relationships, but NO ideation about ending one's life or self-harm.
- MEDIUM: passive ideation, euphemistic phrasings about ending one's life ("end all of this", "put an end to everything", "I just want it all to stop", "I'm done"), references to wanting to die / disappear / not exist, references to self-harm. Includes contextually-clear euphemism even if the words are mild on their own.

Do NOT use HIGH. HIGH is reserved for explicit plan / means / time signals which a separate rule-based filter handles.

Be conservative on benign-but-similar phrasings: "end this Zoom call", "end this lecture", "I want this homework to be over" are NONE. Use MEDIUM only when the most natural reading of the message is about the speaker's life or wellbeing.

Output ONLY valid JSON of the form:
{"risk": "NONE" | "LOW" | "MEDIUM", "reason": "<one short sentence>"}

No prose before or after. No code fences."""


@dataclass
class JudgeAssessment:
    risk: RiskLevel = RiskLevel.NONE
    matched: list[str] = field(default_factory=list)
    reason: str = ""


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", flags=re.MULTILINE)


def _parse_judge_output(raw: str) -> tuple[RiskLevel, str]:
    """Parse the judge's reply into (risk, reason). Tolerates code fences
    and small wrappers; falls back to NONE on any parsing failure."""
    cleaned = _FENCE_RE.sub("", raw).strip()
    # Some models prefix with "Here is the JSON:" — extract the first {...} block.
    m = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if not m:
        return RiskLevel.NONE, ""
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return RiskLevel.NONE, ""
    risk_str = str(data.get("risk", "NONE")).upper().strip()
    reason = str(data.get("reason", "")).strip()[:200]
    if risk_str == "MEDIUM":
        return RiskLevel.MEDIUM, reason
    if risk_str == "LOW":
        return RiskLevel.LOW, reason
    return RiskLevel.NONE, reason


async def assess_llm_judge(text: str) -> JudgeAssessment:
    """Run the LLM judge on a message. Fails open to NONE on any error."""
    if not settings.enable_llm_judge or not text or not text.strip():
        return JudgeAssessment()
    if len(text.split()) < settings.llm_judge_min_words:
        return JudgeAssessment()
    if not settings.openrouter_api_key:
        return JudgeAssessment()

    model = settings.llm_judge_model or settings.openrouter_model
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        "temperature": 0.0,
        # Reasoning models (e.g. Nemotron Nano) consume tokens on hidden
        # reasoning before emitting content — 120 wasn't enough for any
        # output to survive. 800 leaves headroom while still capping cost.
        "max_tokens": 800,
    }
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/lilyshen0722/mindful-chat-prototype",
        "X-Title": settings.app_name,
    }
    url = f"{settings.openrouter_base_url}/chat/completions"

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(settings.llm_judge_timeout)) as client:
            r = await client.post(url, json=payload, headers=headers)
            r.raise_for_status()
            data = r.json()
        msg = data["choices"][0]["message"]
        raw = msg.get("content")
        # Reasoning models put their answer in `reasoning` if `content` is
        # empty (Nemotron, OpenRouter o1-style providers). Fall back to it
        # so we can still extract the JSON block.
        if not isinstance(raw, str) or not raw.strip():
            raw = msg.get("reasoning") or ""
    except (httpx.HTTPError, KeyError, ValueError) as e:
        log.warning("llm_judge unavailable: %s", e)
        return JudgeAssessment()

    if not isinstance(raw, str) or not raw.strip():
        log.warning("llm_judge returned empty content and empty reasoning")
        return JudgeAssessment()

    try:
        risk, reason = _parse_judge_output(raw)
    except Exception as e:  # noqa: BLE001 — never let parsing errors break chat
        log.warning("llm_judge parse error: %s", e)
        return JudgeAssessment()
    if risk == RiskLevel.NONE:
        return JudgeAssessment(risk=RiskLevel.NONE, reason=reason)
    return JudgeAssessment(
        risk=risk,
        matched=[f"llm-judge:{risk.value}: {reason[:120]}"],
        reason=reason,
    )
