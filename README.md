# Mindful Chat Prototype

> ⚠️ **This is an academic research prototype, not a deployable crisis service.**
> If you or someone you know is in crisis, contact a trained professional:
> **988 Suicide & Crisis Lifeline** (call or text **988** in the US),
> **Crisis Text Line** (text **HOME** to **741741**),
> or see https://www.iasp.info for international resources.

A demonstration of an *advisory* guardrail layered around an LLM-powered
chatbot. The bot itself is meant to feel like a normal chat assistant —
the guardrail does NOT replace its replies. Instead it (a) detects
distress and self-harm language via a regex tier, (b) when regex finds
nothing, runs a second-tier emotion classifier
(`SamLowe/roberta-base-go_emotions`) to catch oblique phrasings, (c)
when both regex and ML say NONE, runs a third-tier LLM-judge that
catches euphemistic ideation neither earlier tier owns cleanly, (d)
modulates the LLM's system prompt so it responds with the right tone
(curious on LOW, validating + gently mentioning 988 on MEDIUM, urgent
on HIGH), (e) softly appends crisis resources only if the model failed
to, (f) flags *divergence* when the model volunteers crisis resources
on a NONE-risk turn, (g) elevates tone when several consecutive turns
show distress (multi-turn pattern aggregation), and (h) routes every
concern signal to a simulated administrator review queue so a
human-in-the-loop can audit, open any conversation in a chat-style
review page, and **take over** (pause the bot, send messages as the
reviewer). The only paths that override the model's reply are the
outbound guardrail (replaces unsafe LLM content with a safe template)
and an explicit reviewer pause.

Built for **DSCI 305 (Spring 2026)** — final project on data/AI ethics.

---

## What this is (and is not)

**Is:** an end-to-end prototype showing how a guardrail layer, an admin
escalation queue, and crisis-resource redirection can be wired around any LLM
backend. It is intended as a teaching artifact and a basis for further
research, not a production safety system.

**Is not:** a substitute for clinical judgment, a deployable service for
people in distress, or a validated mental-health tool. All three
detector tiers (regex + ML + LLM-judge) have known false-positive and
false-negative modes, documented in `docs/ethics-mapping.md`
(limitations) and `docs/threat-model.md` (concrete failure modes).

## Architecture

```
┌──────────┐    ┌──────────────────────────────────────────────────────────┐
│ chat UI  │───▶│ FastAPI                                                   │
│ (HTML/JS)│◀───│  ├── /api/chat (SSE)                                      │
│ + sidebar│    │  │   1. regex assess + (if NONE) ML + (if NONE) LLM-judge│
│ + polling│    │  │   1b. multi-turn pattern assess on recent user msgs   │
│          │    │  │   2. if state=human → bypass LLM, send paused notice  │
│          │    │  │   3. else → call OpenRouter with risk-aware prompt    │
│          │    │  │   4. outbound assess; replace unsafe replies          │
│          │    │  │   5. log: input/ml-classifier/llm-judge/pattern/      │
│          │    │  │           output/divergence rows                       │
│          │    │  ├── /api/conversation/{cid}/messages, /state            │
│          │    │  ├── /api/conversations/preview (sidebar)                │
│          │    │  ├── /admin + /admin/conversations/{cid} (HTTP Basic)    │
│          │    │  └── /api/admin/conversations/{cid}/{pause|resume|message}│
│          │    └──────────────────────────────────────────────────────────┘
│          │                  │
│          │                  ▼
│          │   SQLite: conversations, escalations, conversation_state
│          │
│          │   The chat UI polls every 4s for new reviewer messages and
│          │   conversation state, so a paused conversation surfaces a
└──────────┘   "human reviewer engaged" badge to the user.
```

See `docs/architecture.md` for a more detailed walkthrough.

## Quick start (Docker Compose)

```bash
cp .env.example .env
# Open .env and paste your OpenRouter API key (free models work).
docker compose up --build
```

Then:

- Chat UI: http://localhost:8000/
- Admin dashboard: http://localhost:8000/admin (default creds: `admin` / `change-me-locally` — please change in `.env`)

If port 8000 is already in use on your machine, set `HOST_PORT=8001` (or any
free port) in your `.env`. The container always binds 8000 internally; only
the host-side port is remapped.

## Local development without Docker

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill in your OPENROUTER_API_KEY
mkdir -p data
DATABASE_PATH=./data/app.db uvicorn app.main:app --reload
```

## Tests

```bash
pip install pytest
pytest -q
```

Seventeen unit tests cover each detector tier (regex LOW/MEDIUM/HIGH,
multi-turn pattern, merge-risk helper) plus regression tests for
previously-missed phrasings (`feeling really down`, `end all of this`,
etc.). The ML and LLM-judge tiers are exercised via Playwright + httpx
smoke tests against a running container; results documented inline in
their commit messages.

## Demo script

For a 5-minute walkthrough that exercises every rubric-relevant
behavior (multi-conversation switcher, all three detector tiers,
multi-turn pattern, divergence, takeover, paused chat, resume), see
[docs/user-guide.md § Demo script for graders](docs/user-guide.md#demo-script-for-graders).

## Repo layout

```
app/
  main.py              FastAPI app + routes (chat, admin, takeover, switcher)
  guardrail.py         Regex detector + multi-turn pattern aggregator
  ml_classifier.py     Second-tier emotion classifier (HuggingFace)
  llm_judge.py         Third-tier LLM safety classifier (OpenRouter)
  llm.py               OpenRouter chat client + risk-aware system prompts
  crisis_resources.py  Hotline numbers + canned safe response
  db.py                SQLite schema + helpers (conversations, escalations,
                       conversation_state, divergence + reviewer logging,
                       dedup helper)
  config.py            Env-driven settings (LLM, ML, judge, admin auth)
  static/              chat.html + admin.html + admin-conversation.html
                       + style.css
docs/
  written-component.md DSCI 305 final deliverable (<1000 words)
  architecture.md      System diagram, components, API surface, config
  ethics-mapping.md    NIST AI RMF + Belmont mapping, rubric crosswalk
  threat-model.md      Eleven concrete threats with mitigations + residual risk
  user-guide.md        How to run + use + extend, plus a demo script
tests/
  test_guardrail.py    Unit tests (17) for regex, pattern, merge_risk
docker-compose.yml
Dockerfile             Pre-downloads ML weights at build time
requirements.txt       FastAPI + transformers + CPU torch
```

## Documentation map

The required course deliverable is `docs/written-component.md`. The
remaining docs back it up:

| Doc | What it covers |
|---|---|
| [docs/written-component.md](docs/written-component.md) | The under-1000-word deliverable: problem, audience, framework alignment, impact, limitations |
| [docs/user-guide.md](docs/user-guide.md) | How to run, use, configure, demo, troubleshoot |
| [docs/architecture.md](docs/architecture.md) | Dataflow diagram, component table, API surface, storage schema, config |
| [docs/ethics-mapping.md](docs/ethics-mapping.md) | Function-by-function NIST AI RMF mapping, Belmont alignment, rubric crosswalk, design philosophy, known limitations |
| [docs/threat-model.md](docs/threat-model.md) | Eleven concrete threats (T1–T11), mitigations, residual risk, scope exclusions |

## Ethical framework

Aligned with the **NIST AI Risk Management Framework (2023)** —
Govern / Map / Measure / Manage — and informed by the **Belmont Report**
and the course's emphasis on **human-in-the-loop**. See
`docs/ethics-mapping.md` for the function-by-function mapping and the
rubric crosswalk.

## License

MIT — see `LICENSE`.
