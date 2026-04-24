# Architecture

## High-level dataflow

```
       ┌──────────────────┐
  user │   Browser (chat) │  ── localStorage holds the cid list (multi-conv switcher)
       └────────┬─────────┘     and polls every 4s for reviewer messages + state
                │  POST /api/chat   (Server-Sent Events response)
                ▼
       ┌──────────────────────────────────────────────────────────────────┐
       │ FastAPI app (app/main.py)                                         │
       │                                                                   │
       │ 1. inbound = assess(user_message)             ── single-message   │
       │ 2. pattern = assess_pattern(recent_user_msgs) ── multi-turn       │
       │ 3. effective_risk = max(inbound, pattern)                         │
       │ 4. state = get_conversation_state(cid)                            │
       │      ├─ "human" (paused) → skip LLM; return notice; log inbound  │
       │      │                     concern as input-while-paused          │
       │      └─ "bot" → continue                                          │
       │ 5. system_prompt = build_system_prompt(effective_risk)            │
       │ 6. stream OpenRouter → yield tokens to client                     │
       │ 7. outbound = assess(full_reply)                                  │
       │      ├─ unsafe?  → "replace" with safe template; escalations(output)│
       │      └─ safe but effective_risk MEDIUM/HIGH and no resource       │
       │         mentioned → emit short footer                              │
       │ 8. log to escalations:                                            │
       │      • input          if inbound != NONE                          │
       │      • pattern        if pattern triggered but inbound was NONE   │
       │      • divergence     if effective NONE but bot mentioned 988     │
       │ 9. persist conversation + emit "done" event                       │
       └────────┬──────────────────────────────────┬───────────────────────┘
                │ writes                           │ writes
                ▼                                  ▼
       ┌────────────────┐                ┌────────────────────┐
       │ conversations  │                │   escalations      │
       │   (sqlite)     │                │     (sqlite)       │
       └────────────────┘                └─────────┬──────────┘
                                                   │ read
                ┌────────────────────┐             │
                │ conversation_state │◀── pause/resume/send via admin API
                │     (sqlite)       │             │
                └─────────┬──────────┘             ▼
                          │              ┌────────────────────────┐
                          │              │ /admin dashboard       │
                          │              │ HTTP Basic auth        │
                          └─── read ────▶│ list + transcript +    │ ── reviewer
                                         │ ack/notes + take over  │   (human-in-the-loop)
                                         └────────────────────────┘
```

**Key design choices.**

- The LLM is never bypassed by the inbound guardrail; tone is *modulated*
  via the system prompt rather than replaced. Resources surface gradually
  rather than as a hard interrupt. The only paths that override the model's
  reply are the outbound guardrail (unsafe LLM output → safe template) and
  an explicit human pause (reviewer takes over the conversation).
- The guardrail is layered: inbound regex on a single turn, multi-turn
  pattern aggregation, outbound regex on the bot's reply, and a
  *divergence detector* that catches the model raising crisis resources
  unprompted. Each path logs to the escalation queue with a distinct
  `source` so a reviewer can tell which layer fired.
- Human review is not advisory: a reviewer can pause the bot and chat
  directly with the user as a human, and the user sees a "human reviewer
  engaged" badge so the takeover is transparent.

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
and auditable. Three tables:

- `conversations(id, conversation_id, role, content, risk_level, created_at)`
  — the linear message log. `risk_level='human-reviewer'` marks messages
  injected by the human reviewer.
- `escalations(id, conversation_id, risk_level, source, matched_signals,
  user_message, bot_response, acknowledged, acknowledged_by, acknowledged_at,
  notes, created_at)` — the review queue.
- `conversation_state(conversation_id PK, state, changed_at, changed_by)` —
  per-conversation `bot` / `human` flag for the takeover feature.

The `source` column on `escalations` distinguishes which layer of the
pipeline fired the alert:

| `source`              | Meaning                                                                 |
|-----------------------|-------------------------------------------------------------------------|
| `input`               | Inbound user message tripped the regex.                                 |
| `pattern`             | Multi-turn aggregation: 3 consecutive non-NONE user messages.           |
| `output`              | Outbound LLM reply tripped the regex (unsafe content; reply replaced).  |
| `divergence`          | Effective risk was NONE but the LLM volunteered a crisis resource — surfaces a model-vs-policy mismatch. |
| `input-while-paused`  | Inbound concern signal that arrived while a human reviewer had paused the bot. |

## Failure handling

| Failure                          | What happens                                                            |
|----------------------------------|-------------------------------------------------------------------------|
| `OPENROUTER_API_KEY` missing     | `LLMUnavailable` raised → user sees a `[Configuration error]` token.    |
| OpenRouter HTTP error / timeout  | `httpx.HTTPError` caught → user sees `[Upstream error]` token.          |
| Inbound guardrail trips (LOW/MED/HIGH) | LLM still answers, with a risk-aware system prompt; row in `escalations(input)`. If effective risk is MEDIUM/HIGH and the model didn't mention any resource, a short 988 footer is appended via a final `token` event. |
| Multi-turn pattern trips         | System prompt is elevated to MEDIUM tone; row in `escalations(pattern)`. |
| Outbound guardrail trips         | LLM reply is replaced with `CRISIS_MESSAGE` via a `replace` event; row in `escalations(output)`. |
| Bot mentions resource on NONE-risk turn | Reply is **not** modified; row in `escalations(divergence)` so the reviewer can audit model behavior against the documented policy. |
| Reviewer pauses the bot          | `/api/chat` skips the LLM and emits a single notice token; user-side polling renders the takeover badge. |
| Admin credentials wrong          | `401` with `WWW-Authenticate: Basic` header.                            |

## Local deployment

Docker Compose runs a single `api` service, mounts `./data` as `/data` in
the container so the SQLite file survives restarts, and reads secrets from a
local `.env` file that is gitignored.
