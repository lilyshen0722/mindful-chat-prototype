# Architecture

## High-level dataflow

```
       ┌──────────────────┐
  user │   Browser (chat) │
       └────────┬─────────┘
                │  POST /api/chat
                ▼
       ┌──────────────────────────────────────────┐
       │ FastAPI app (app/main.py)                │
       │                                          │
       │  1. assess(user_message)                 │  ── app/guardrail.py
       │     ├─ NONE → continue                   │
       │     ├─ LOW  → log; continue (LLM still)  │
       │     └─ MEDIUM/HIGH → block, log,         │
       │           return CRISIS_MESSAGE          │  ── app/crisis_resources.py
       │                                          │
       │  2. recent_history(conversation_id)      │  ── app/db.py
       │  3. POST /chat/completions to OpenRouter │  ── app/llm.py
       │  4. assess(llm_reply)                    │
       │     └─ MEDIUM/HIGH → log; replace reply  │
       │           with CRISIS_MESSAGE            │
       │  5. save assistant message               │
       │  6. return ChatResponse(reply, risk,     │
       │                         escalated, …)    │
       └────────┬──────────────────────────┬──────┘
                │                          │
                │ writes                   │ writes
                ▼                          ▼
       ┌────────────────┐         ┌────────────────────┐
       │ conversations  │         │   escalations      │
       │   (sqlite)     │         │     (sqlite)       │
       └────────────────┘         └─────────┬──────────┘
                                            │ read
                                            ▼
                                  ┌────────────────────┐
                                  │ /admin dashboard   │
                                  │ HTTP Basic auth    │  ── reviewer
                                  │ ack + notes        │     (human-in-the-loop)
                                  └────────────────────┘
```

## Components

| File                         | Responsibility                                                  |
|------------------------------|-----------------------------------------------------------------|
| `app/main.py`                | FastAPI routes; orchestrates guardrail → LLM → guardrail → DB.  |
| `app/guardrail.py`           | Rule-based crisis-language detector. Returns `RiskLevel`.       |
| `app/llm.py`                 | OpenRouter HTTP client + safety system prompt.                  |
| `app/crisis_resources.py`    | Hotline list and the canned safe response template.             |
| `app/db.py`                  | SQLite schema + helpers (save / log / list / acknowledge).      |
| `app/config.py`              | `pydantic-settings`-driven env config.                          |
| `app/static/chat.html`       | User-facing chat UI with persistent crisis banner.              |
| `app/static/admin.html`      | Reviewer-facing dashboard for the escalation queue.             |

## Why a single FastAPI service

A multi-service split (separate "chat", "guardrail", "admin") was considered
and rejected for this prototype: the extra HTTP hops would increase surface
area without changing the safety model, and would make local-first review
harder for a course-grading audience. The same defense-in-depth properties
(inbound check, LLM safety prompt, outbound check, human review queue) are
achievable inside one process and one Docker container.

## Storage

A single SQLite database in a Docker volume keeps the prototype local-first
and auditable. Two tables:

- `conversations(id, conversation_id, role, content, risk_level, created_at)`
- `escalations(id, conversation_id, risk_level, source, matched_signals,
  user_message, bot_response, acknowledged, acknowledged_by, acknowledged_at,
  notes, created_at)`

`source` is `"input"` for user-message detections and `"output"` for
LLM-reply detections, which lets a reviewer see which side of the pipeline
fired the alert.

## Failure handling

| Failure                          | What happens                                                            |
|----------------------------------|-------------------------------------------------------------------------|
| `OPENROUTER_API_KEY` missing     | `LLMUnavailable` raised → user sees a `[Configuration error]` reply.    |
| OpenRouter HTTP error / timeout  | `httpx.HTTPError` caught → user sees `[Upstream error]`.                |
| Inbound guardrail trips          | LLM is bypassed entirely; user gets `CRISIS_MESSAGE`; row in `escalations`. |
| Outbound guardrail trips         | LLM reply is replaced with `CRISIS_MESSAGE` before being saved/sent.    |
| Admin credentials wrong          | `401` with `WWW-Authenticate: Basic` header.                            |

## Local deployment

Docker Compose runs a single `api` service, mounts `./data` as `/data` in
the container so the SQLite file survives restarts, and reads secrets from a
local `.env` file that is gitignored.
