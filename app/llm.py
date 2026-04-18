import httpx

from .config import settings


SYSTEM_PROMPT = """\
You are a supportive conversational assistant inside an academic research \
prototype.

Strict rules you must follow:
1. You are NOT a therapist, doctor, or crisis counselor. Never diagnose, \
never prescribe, never give clinical advice.
2. If the user describes distress, briefly validate their feelings (1-2 \
sentences) and gently encourage them to talk to a trained professional or \
a crisis line. Mention 988 (call or text, US) and \
https://www.iasp.info for international resources.
3. Keep responses warm, brief, and non-judgmental. Do not lecture.
4. If the user asks about methods of self-harm or suicide, refuse and \
redirect to a crisis line.
5. Do not pretend to be human. If asked, say you are an AI prototype.
6. Do not collect or ask for identifying information (full name, address, \
SSN, medical record numbers).
"""


class LLMUnavailable(RuntimeError):
    """Raised when the LLM cannot be called (e.g. missing API key)."""


async def chat(history: list[dict[str, str]]) -> str:
    if not settings.openrouter_api_key:
        raise LLMUnavailable(
            "OPENROUTER_API_KEY is not set. Add it to your .env to enable replies."
        )

    payload = {
        "model": settings.openrouter_model,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}, *history],
        "temperature": 0.4,
        "max_tokens": 500,
    }

    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        # OpenRouter recommends these for attribution.
        "HTTP-Referer": "https://github.com/lilyshen0722/mindful-chat-prototype",
        "X-Title": settings.app_name,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            f"{settings.openrouter_base_url}/chat/completions",
            json=payload,
            headers=headers,
        )
        r.raise_for_status()
        data = r.json()

    return data["choices"][0]["message"]["content"]
