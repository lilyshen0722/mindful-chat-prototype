"""OpenRouter chat client with streaming and risk-aware system prompts.

The system prompt is built per-turn from the inbound risk level so the model
behaves like a normal supportive chatbot on neutral messages and grows more
attentive as the guardrail signals concern. The model is never bypassed —
only the outbound guardrail in `main.py` can replace its reply, and only if
the model itself produces unsafe content.
"""
from __future__ import annotations

import json
from typing import AsyncIterator

import httpx

from .config import settings
from .guardrail import RiskLevel


_BASE_PROMPT = """\
You are a supportive conversational assistant inside an academic research \
prototype called "Mindful Chat". Treat the conversation like a normal chat \
with a thoughtful peer — be warm, listen, and respond naturally to whatever \
the user brings up.

Hard rules you must always follow:
1. You are NOT a therapist, doctor, or crisis counselor. Never diagnose, \
prescribe, or give clinical advice.
2. Keep responses warm, brief, and human. Do not lecture or moralize.
3. Do not pretend to be human. If asked, say you are an AI prototype.
4. Do not ask for or store identifying information (full name, address, \
SSN, medical record numbers).
5. NEVER provide any information about methods of self-harm or suicide. \
If the user asks about methods, refuse and redirect them to a trained \
crisis professional.
6. Do NOT bring up crisis lines, hotlines, 988, or similar resources on \
your own initiative. Mention them ONLY when (a) the user is clearly \
describing self-harm or suicidal ideation, or (b) the section below in \
this system prompt explicitly directs you to. For everyday topics — \
school stress, work problems, relationships, frustration, ordinary \
sadness, "I hate my class," etc. — be a supportive listener WITHOUT \
bringing up crisis resources. Pushing hotlines on normal venting is \
unhelpful and feels dismissive.
"""

_NONE_GUIDANCE = """
For this turn the user has shown no signs of crisis or self-harm. Engage \
naturally as a helpful peer. Do NOT mention crisis lines, hotlines, 988, \
or similar resources — they are not relevant to this turn.
"""

_LOW_GUIDANCE = """
For this turn the user has shown some signs of distress (fatigue, \
hopelessness, "nothing matters" type language) but nothing acute. Respond \
with warmth and curiosity. Validate the feeling in one sentence, then ask \
one gentle open question to invite them to say more. Do NOT mention \
hotlines or 988 — at this stage the user just needs to feel heard. This \
is the early part of what may be a longer conversation.
"""

_MEDIUM_GUIDANCE = """
For this turn the user has expressed something concerning (passive \
ideation, "want to disappear", self-harm references). First validate \
their feelings briefly. Then, in one short sentence, gently mention that \
talking with someone trained — like the 988 Lifeline (call or text) — \
can help. Stay engaged in the conversation; do not lecture; do not \
disengage.
"""

_HIGH_GUIDANCE = """
For this turn the user has expressed something urgent (a plan, means, \
specific time, or a final goodbye). Respond carefully:
- Validate their feelings strongly in one sentence.
- Warmly but clearly urge them to call or text 988 (US Suicide & Crisis \
Lifeline) right now, or call local emergency services if they are in \
immediate physical danger.
- Ask if they are somewhere safe.
- Stay engaged. Do NOT give any information about methods. Do NOT give \
clinical advice.
"""


def build_system_prompt(risk: RiskLevel) -> str:
    if risk == RiskLevel.LOW:
        return _BASE_PROMPT + _LOW_GUIDANCE
    if risk == RiskLevel.MEDIUM:
        return _BASE_PROMPT + _MEDIUM_GUIDANCE
    if risk == RiskLevel.HIGH:
        return _BASE_PROMPT + _HIGH_GUIDANCE
    return _BASE_PROMPT + _NONE_GUIDANCE


class LLMUnavailable(RuntimeError):
    """Raised when the LLM cannot be called (e.g. missing API key)."""


def _payload(history: list[dict[str, str]], system_prompt: str, *, stream: bool) -> dict:
    return {
        "model": settings.openrouter_model,
        "messages": [{"role": "system", "content": system_prompt}, *history],
        "temperature": 0.5,
        "max_tokens": 800,
        "stream": stream,
    }


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/lilyshen0722/mindful-chat-prototype",
        "X-Title": settings.app_name,
    }


async def chat_stream(
    history: list[dict[str, str]],
    system_prompt: str,
) -> AsyncIterator[str]:
    """Yield reply tokens from OpenRouter as they arrive."""
    if not settings.openrouter_api_key:
        raise LLMUnavailable(
            "OPENROUTER_API_KEY is not set. Add it to your .env to enable replies."
        )

    url = f"{settings.openrouter_base_url}/chat/completions"
    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, read=60.0)) as client:
        async with client.stream(
            "POST",
            url,
            json=_payload(history, system_prompt, stream=True),
            headers=_headers(),
        ) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                line = line.strip()
                if not line.startswith("data: "):
                    continue
                data = line[len("data: "):]
                if data == "[DONE]":
                    return
                try:
                    chunk = json.loads(data)
                    delta = chunk["choices"][0]["delta"].get("content")
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
                if delta:
                    yield delta
