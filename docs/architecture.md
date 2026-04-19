# Architecture

## High-level dataflow

```
       ┌──────────────────┐
  user │   Browser (chat) │
       └────────┬─────────┘
                │  POST /api/chat   (Server-Sent Events response)
                ▼
       ┌────────────────────────────────────────────────────────┐
       │ FastAPI app (app/main.py)                              │
       │                                                        │
       │ 1. inbound = assess(user_message)        ── guardrail  │
       │ 2. system_prompt = build_system_prompt(inbound.risk)   │
       │      (NONE / LOW / MEDIUM / HIGH variants — see        │
       │       app/llm.py — modulate tone, not flow)            │
       │ 3. stream OpenRouter → yield tokens to client          │
       │ 4. outbound = assess(full_reply)                       │
       │      ├─ unsafe?  → emit "replace" event with safe       │
       │      │             template; row in escalations(output)│
       │      └─ safe but inbound was MEDIUM/HIGH and the LLM   │
       │         omitted any resource → emit short footer       │
       │ 5. inbound risk != NONE  → row in escalations(input)   │
       │ 6. persist conversation + emit "done" event            │
       └────────┬──────────────────────────────────┬────────────┘
                │ writes                           │ writes
                ▼                                  ▼
       ┌────────────────┐                ┌────────────────────┐
       │ conversations  │                │   escalations      │
       │   (sqlite)     │                │     (sqlite)       │
       └────────────────┘                └─────────┬──────────┘
                                                   │ read
                                                   ▼
                                         ┌────────────────────┐
                                         │ /admin dashboard   │
                                         │ HTTP Basic auth    │  ── reviewer
                                         │ ack + notes        │     (human-in-the-loop)
                                         └────────────────────┘
```

**Key design choice (v0.2):** the LLM is never bypassed. The guardrail is
*advisory* — it modulates the model's system prompt and logs every concern
signal to the admin queue. Resources surface gradually through conversation
rather than as a hard interrupt. The only path that overrides the model's
reply is the outbound guardrail (when the LLM itself produces unsafe
content), and it falls back to the safe template in `crisis_resources.py`.

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
| `OPENROUTER_API_KEY` missing     | `LLMUnavailable` raised → user sees a `[Configuration error]` token.    |
| OpenRouter HTTP error / timeout  | `httpx.HTTPError` caught → user sees `[Upstream error]` token.          |
| Inbound guardrail trips (LOW/MED/HIGH) | LLM still answers, with a risk-aware system prompt; row in `escalations(input)`. If MEDIUM/HIGH and the model didn't mention any resource, a short 988 footer is appended via a final `token` event. |
| Outbound guardrail trips         | LLM reply is replaced with `CRISIS_MESSAGE` via a `replace` event; row in `escalations(output)`. |
| Admin credentials wrong          | `401` with `WWW-Authenticate: Basic` header.                            |

## Local deployment

Docker Compose runs a single `api` service, mounts `./data` as `/data` in
the container so the SQLite file survives restarts, and reads secrets from a
local `.env` file that is gitignored.
