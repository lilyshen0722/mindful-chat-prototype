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
    PAUSED_NOTICE,
    acknowledge_escalation,
    conversation_messages,
    conversation_previews,
    get_conversation_state,
    has_open_escalation_for_source,
    init_db,
    list_escalations,
    log_divergence,
    log_escalation,
    recent_history,
    save_message,
    save_reviewer_message,
    set_conversation_state,
)
from .guardrail import GuardrailResult, RiskLevel, assess, assess_pattern, merge_risk
from .llm import LLMUnavailable, build_system_prompt, chat_stream
from .llm_judge import assess_llm_judge
from .ml_classifier import assess_ml


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


class PreviewRequest(BaseModel):
    ids: list[str] = Field(default_factory=list, max_length=200)


class ReviewerMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=4000)


# ------------------------------------------------------------------ pages
@app.get("/", response_class=HTMLResponse)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "chat.html")


@app.get("/admin", response_class=HTMLResponse)
def admin_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "admin.html")


@app.get("/admin/conversations/{conversation_id}", response_class=HTMLResponse)
def admin_conversation_page(conversation_id: str) -> FileResponse:
    """Chat-style view of a single conversation for the reviewer.

    Note: this route serves the static HTML; the API calls it makes are
    auth-gated, so the page itself is harmless without credentials.
    """
    return FileResponse(STATIC_DIR / "admin-conversation.html")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/conversation/{conversation_id}/messages")
def get_conversation_messages(conversation_id: str) -> list[dict]:
    """Return the visible message log for a conversation_id (oldest first)."""
    return conversation_messages(conversation_id)


@app.get("/api/conversation/{conversation_id}/state")
def get_conversation_state_endpoint(conversation_id: str) -> dict:
    return {"state": get_conversation_state(conversation_id)}


@app.post("/api/conversations/preview")
def get_conversation_previews(body: PreviewRequest) -> list[dict]:
    """Return previews for the conversations the client is tracking.

    The client owns the list of conversation IDs (in localStorage); the server
    only knows about a cid once it has stored a message for it. This endpoint
    is a no-auth lookup because conversation_ids are already opaque UUIDs and
    the client can only ask about ones it knows.
    """
    return conversation_previews(body.ids)


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

    If a human reviewer has paused the conversation, the LLM is bypassed
    entirely and the user gets a short notice that a human is engaged.
    """
    # First tier: regex. Cheap, deterministic, audit-friendly.
    inbound_regex: GuardrailResult = assess(req.message)
    # Second tier: emotion classifier — only consulted when regex didn't
    # already classify. Caps at LOW.
    ml_result = assess_ml(req.message) if inbound_regex.risk == RiskLevel.NONE else None

    # Persist the user message *before* the third-tier (async) judge call,
    # so a mid-call disconnect can't lose the message itself. The risk_level
    # written here reflects the synchronous tiers; the async judge can still
    # log a separate escalation row if it fires.
    sync_risk = ml_result.risk if (ml_result and ml_result.risk != RiskLevel.NONE) else inbound_regex.risk
    user_msg_id = save_message(req.conversation_id, "user", req.message, sync_risk.value)

    # Third tier: LLM judge — only when regex and ML both said NONE. Caps at MEDIUM.
    # Wrapped so any unexpected failure (provider quota, transient network, etc.)
    # cannot take down the chat — fail-open is the design contract for this tier.
    judge_result = None
    if inbound_regex.risk == RiskLevel.NONE and (ml_result is None or ml_result.risk == RiskLevel.NONE):
        try:
            judge_result = await assess_llm_judge(req.message)
        except Exception:  # noqa: BLE001
            judge_result = None

    # Resolve final inbound risk. The order — judge > ml > regex — matters
    # because the judge can elevate to MEDIUM, the ML tier caps at LOW, and
    # the regex tier might have already returned MEDIUM/HIGH.
    if judge_result is not None and judge_result.risk != RiskLevel.NONE:
        inbound = GuardrailResult(
            risk=judge_result.risk,
            matched=inbound_regex.matched + judge_result.matched,
        )
        inbound_source = "llm-judge"
    elif ml_result is not None and ml_result.risk != RiskLevel.NONE:
        inbound = GuardrailResult(
            risk=ml_result.risk,
            matched=inbound_regex.matched + ml_result.matched,
        )
        inbound_source = "ml-classifier"
    else:
        inbound = inbound_regex
        inbound_source = "input"

    history = recent_history(req.conversation_id, limit=10)
    user_history = [h["content"] for h in history if h["role"] == "user"]
    pattern: GuardrailResult = assess_pattern(user_history)
    effective_risk: RiskLevel = merge_risk(inbound.risk, pattern.risk)

    state = get_conversation_state(req.conversation_id)

    # Log inbound + pattern concern signals synchronously, before any streaming
    # starts. If the client disconnects mid-stream the SSE generator is
    # cancelled and any code after `yield` never runs — so any reviewer-relevant
    # signal that depends on the *user's* message must be logged here. Outbound
    # and divergence checks remain in the generator because they need the full
    # bot reply.
    if state != "human" and inbound.risk != RiskLevel.NONE:
        log_escalation(
            req.conversation_id, inbound, req.message, None, source=inbound_source
        )
    if (
        state != "human"
        and pattern.risk != RiskLevel.NONE
        and merge_risk(inbound.risk, pattern.risk) != inbound.risk
        and not has_open_escalation_for_source(req.conversation_id, "pattern")
    ):
        log_escalation(
            req.conversation_id, pattern, req.message, None, source="pattern"
        )

    if state == "human":
        # Bot is paused — log inbound concern signals (so the reviewer still
        # sees risk patterns) but do not invoke the LLM. The reviewer will
        # respond out-of-band via the admin UI.
        if inbound.risk != RiskLevel.NONE:
            paused_source_map = {
                "ml-classifier": "ml-classifier-while-paused",
                "llm-judge": "llm-judge-while-paused",
            }
            paused_source = paused_source_map.get(inbound_source, "input-while-paused")
            log_escalation(
                req.conversation_id,
                inbound,
                req.message,
                PAUSED_NOTICE,
                source=paused_source,
            )
        asst_msg_id = save_message(
            req.conversation_id, "assistant", PAUSED_NOTICE, "none"
        )

        async def paused_generator():
            # Tell the client what ids their just-saved messages got, so the
            # polling loop can advance lastSeenMsgId without re-rendering
            # bubbles that are already on screen.
            yield _sse({"type": "user_saved", "id": user_msg_id})
            yield _sse({"type": "token", "value": PAUSED_NOTICE})
            yield _sse({"type": "assistant_saved", "id": asst_msg_id})
            yield _sse({
                "type": "done",
                "risk_level": inbound.risk.value,
                "escalated": inbound.risk != RiskLevel.NONE,
                "paused": True,
            })

        return StreamingResponse(
            paused_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    system_prompt = build_system_prompt(effective_risk)

    async def generator():
        # Tell the client what id their just-saved message got, so polling
        # can advance lastSeenMsgId and not re-render the optimistic bubble.
        yield _sse({"type": "user_saved", "id": user_msg_id})
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

        # Soft resource graft: only if effective risk was concerning AND the
        # LLM forgot to mention any resource. We do not replace its reply.
        elif effective_risk in (RiskLevel.MEDIUM, RiskLevel.HIGH) and not _mentions_resource(full_reply):
            full_reply += RESOURCE_FOOTER
            yield _sse({"type": "token", "value": RESOURCE_FOOTER})

        # Inbound + pattern were logged synchronously above (with bot_response
        # left null). Divergence is the only inbound-correlated signal we can
        # only resolve once we know what the bot actually said. Deduped while
        # an open divergence row exists for this cid so persistent model drift
        # surfaces as one actionable item, not one row per turn.
        if (
            effective_risk == RiskLevel.NONE
            and not outbound.is_escalation
            and _mentions_resource(full_reply)
            and not has_open_escalation_for_source(req.conversation_id, "divergence")
        ):
            log_divergence(req.conversation_id, req.message, full_reply)

        asst_msg_id = save_message(
            req.conversation_id, "assistant", full_reply, effective_risk.value
        )

        yield _sse({"type": "assistant_saved", "id": asst_msg_id})
        yield _sse({
            "type": "done",
            "risk_level": effective_risk.value,
            "inbound_risk": inbound.risk.value,
            "pattern_risk": pattern.risk.value,
            "escalated": (
                inbound.risk != RiskLevel.NONE
                or pattern.risk != RiskLevel.NONE
                or outbound.is_escalation
            ),
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


@app.get("/api/admin/conversations/{conversation_id}/messages")
def admin_conversation_messages(
    conversation_id: str,
    _: str = Depends(admin_user),
) -> list[dict]:
    """Full transcript for a conversation. Auth-gated mirror of the public
    endpoint so escalation reviewers can see surrounding context, not just
    the single message that tripped the guardrail."""
    return conversation_messages(conversation_id)


@app.get("/api/admin/conversations/{conversation_id}/escalations")
def admin_conversation_escalations(
    conversation_id: str,
    _: str = Depends(admin_user),
) -> list[dict]:
    """All escalation rows for a single conversation (for the focused view)."""
    return [r for r in list_escalations(unack_only=False, limit=500) if r["conversation_id"] == conversation_id]


@app.post("/api/admin/conversations/{conversation_id}/pause")
def admin_pause(
    conversation_id: str,
    user: str = Depends(admin_user),
) -> dict:
    set_conversation_state(conversation_id, "human", changed_by=user)
    return {"ok": True, "state": "human"}


@app.post("/api/admin/conversations/{conversation_id}/resume")
def admin_resume(
    conversation_id: str,
    user: str = Depends(admin_user),
) -> dict:
    set_conversation_state(conversation_id, "bot", changed_by=user)
    return {"ok": True, "state": "bot"}


@app.post("/api/admin/conversations/{conversation_id}/message")
def admin_send_reviewer_message(
    conversation_id: str,
    body: ReviewerMessageRequest,
    user: str = Depends(admin_user),
) -> dict:
    """Inject a message from the human reviewer into the user's chat.

    The user-facing chat polls the messages endpoint and renders messages with
    risk_level='human-reviewer' in a distinct style with attribution. Sending
    a reviewer message does not by itself pause the bot — pause/resume are
    separate controls so the reviewer can choose to chime in alongside the
    bot or fully take over.
    """
    msg_id = save_reviewer_message(conversation_id, body.content)
    return {"ok": True, "id": msg_id, "by": user}
