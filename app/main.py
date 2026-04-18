from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import httpx
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import secrets

from .config import settings
from .crisis_resources import CRISIS_MESSAGE, US_RESOURCES
from .db import (
    acknowledge_escalation,
    init_db,
    list_escalations,
    log_escalation,
    recent_history,
    save_message,
)
from .guardrail import RiskLevel, assess
from .llm import LLMUnavailable, chat as llm_chat


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

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


class ChatResponse(BaseModel):
    reply: str
    risk_level: str
    escalated: bool
    resources: list[dict] = []


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


# ------------------------------------------------------------------ chat
@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest) -> ChatResponse:
    inbound = assess(req.message)
    save_message(req.conversation_id, "user", req.message, inbound.risk.value)

    # MEDIUM/HIGH inbound: skip the LLM entirely.
    if inbound.block_llm:
        reply = CRISIS_MESSAGE
        log_escalation(req.conversation_id, inbound, req.message, reply, source="input")
        save_message(req.conversation_id, "assistant", reply, inbound.risk.value)
        return ChatResponse(
            reply=reply,
            risk_level=inbound.risk.value,
            escalated=True,
            resources=US_RESOURCES,
        )

    # Otherwise call the LLM with recent history.
    history = recent_history(req.conversation_id, limit=10)
    try:
        reply = await llm_chat(history)
    except LLMUnavailable as e:
        reply = f"[Configuration error] {e}"
    except httpx.HTTPError as e:
        reply = f"[Upstream error from OpenRouter] {e}"

    # Defense in depth: assess the bot's reply too.
    outbound = assess(reply)
    if outbound.is_escalation:
        log_escalation(req.conversation_id, outbound, req.message, reply, source="output")
        reply = CRISIS_MESSAGE
        risk_for_reply = outbound.risk.value
    else:
        risk_for_reply = inbound.risk.value

    if inbound.risk == RiskLevel.LOW:
        log_escalation(req.conversation_id, inbound, req.message, reply, source="input")

    save_message(req.conversation_id, "assistant", reply, risk_for_reply)

    escalated = inbound.risk != RiskLevel.NONE or outbound.is_escalation
    return ChatResponse(
        reply=reply,
        risk_level=risk_for_reply,
        escalated=escalated,
        resources=US_RESOURCES if escalated else [],
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
