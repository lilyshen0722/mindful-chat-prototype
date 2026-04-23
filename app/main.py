import json
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import httpx
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import settings
from .crisis_resources import CRISIS_MESSAGE, US_RESOURCES
from .db import (
    acknowledge_escalation,
    conversation_messages,
    init_db,
    list_escalations,
    log_divergence,
    log_escalation,
    recent_history,
    save_message,
)
from .guardrail import GuardrailResult, RiskLevel, assess
from .llm import LLMUnavailable, build_system_prompt, chat_stream


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title=settings.app_name, version="0.2.0", lifespan=lifespan)

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ------------------------------------------------------------------ auth
basic = HTTPBasic()


def admin_user(credentials: HTTPBasicCredentials = Depends(basic)) -> str:
    user_ok = secrets.compare_digest(credentials.username, settings.admin_username)
    pass_ok = secrets.compare_digest(credentials.password, settings.admin_password)
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


# ------------------------------------------------------------------ schema
class ChatRequest(BaseModel):
    conversation_id: str = Field(..., min_length=1, max_length=64)
    message: str = Field(..., min_length=1, max_length=4000)


class AcknowledgeRequest(BaseModel):
    notes: Optional[str] = None


# ------------------------------------------------------------------ pages
@app.get("/", response_class=HTMLResponse)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "chat.html")


@app.get("/admin", response_class=HTMLResponse)
def admin_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "admin.html")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/conversation/{conversation_id}/messages")
def get_conversation_messages(conversation_id: str) -> list[dict]:
    """Return the visible message log for a conversation_id (oldest first)."""
    return conversation_messages(conversation_id)


# ------------------------------------------------------------------ chat
RESOURCE_FOOTER = (
    "\n\nIf you'd like to talk to someone trained right now, **988** "
    "(call or text in the US) is free, confidential, and available 24/7."
)

_RESOURCE_HINTS = ("988", "crisis text line", "741741", "iasp.info", "samhsa", "trevor project")


def _mentions_resource(text: str) -> bool:
    t = text.lower()
    return any(hint in t for hint in _RESOURCE_HINTS)


def _sse(payload: dict) -> str:
    """Format a single Server-Sent Event with a JSON payload."""
    return f"data: {json.dumps(payload)}\n\n"


@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest) -> StreamingResponse:
    """Stream the bot's reply token by token.

    The LLM is always invoked with a risk-aware system prompt. Resources are
    grafted softly only when the inbound message tripped the guardrail and
    the LLM did not include any resource on its own. The outbound guardrail
    can still replace the entire reply if the LLM produced unsafe content.
    """
    inbound: GuardrailResult = assess(req.message)
    save_message(req.conversation_id, "user", req.message, inbound.risk.value)

    history = recent_history(req.conversation_id, limit=10)
    system_prompt = build_system_prompt(inbound.risk)

    async def generator():
        parts: list[str] = []
        try:
            async for token in chat_stream(history, system_prompt):
                parts.append(token)
                yield _sse({"type": "token", "value": token})
        except LLMUnavailable as e:
            msg = f"[Configuration error] {e}"
            parts = [msg]
            yield _sse({"type": "token", "value": msg})
        except httpx.HTTPError as e:
            msg = f"[Upstream error from OpenRouter] {e}"
            parts = [msg]
            yield _sse({"type": "token", "value": msg})

        full_reply = "".join(parts).strip() or "[no response]"

        # Outbound guardrail: if the LLM produced unsafe content, replace it
        # with the safe template. This is the only path that overrides the
        # model's reply.
        outbound = assess(full_reply)
        if outbound.is_escalation:
            log_escalation(
                req.conversation_id,
                outbound,
                req.message,
                full_reply,
                source="output",
            )
            full_reply = CRISIS_MESSAGE
            yield _sse({"type": "replace", "value": full_reply})

        # Soft resource graft: only if inbound was concerning AND the LLM
        # forgot to mention any resource. We do not replace its reply.
        elif inbound.risk in (RiskLevel.MEDIUM, RiskLevel.HIGH) and not _mentions_resource(full_reply):
            full_reply += RESOURCE_FOOTER
            yield _sse({"type": "token", "value": RESOURCE_FOOTER})

        # Always log inbound concern signals for the admin queue.
        if inbound.risk != RiskLevel.NONE:
            log_escalation(
                req.conversation_id,
                inbound,
                req.message,
                full_reply,
                source="input",
            )
        # Divergence: rule-based guardrail says NONE but the model volunteered a
        # crisis resource anyway. The reviewer needs to see this — it's evidence
        # the LLM is broadening "crisis" beyond the documented policy.
        elif not outbound.is_escalation and _mentions_resource(full_reply):
            log_divergence(req.conversation_id, req.message, full_reply)

        save_message(req.conversation_id, "assistant", full_reply, inbound.risk.value)

        yield _sse({
            "type": "done",
            "risk_level": inbound.risk.value,
            "escalated": inbound.risk != RiskLevel.NONE or outbound.is_escalation,
        })

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ------------------------------------------------------------------ admin api
@app.get("/api/admin/escalations")
def admin_list_escalations(
    unack_only: bool = False,
    _: str = Depends(admin_user),
) -> list[dict]:
    return list_escalations(unack_only=unack_only)


@app.post("/api/admin/escalations/{escalation_id}/acknowledge")
def admin_acknowledge(
    escalation_id: int,
    body: AcknowledgeRequest,
    user: str = Depends(admin_user),
) -> dict:
    acknowledge_escalation(escalation_id, reviewer=user, notes=body.notes)
    return {"ok": True, "id": escalation_id}
