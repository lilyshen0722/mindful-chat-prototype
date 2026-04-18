# Mindful Chat Prototype

> ⚠️ **This is an academic research prototype, not a deployable crisis service.**
> If you or someone you know is in crisis, contact a trained professional:
> **988 Suicide & Crisis Lifeline** (call or text **988** in the US),
> **Crisis Text Line** (text **HOME** to **741741**),
> or see https://www.iasp.info for international resources.

A demonstration of a layered guardrail that sits between a user-facing chat UI
and a Large Language Model, with the goals of (a) detecting language
associated with suicidal ideation or self-harm, (b) redirecting the user to
human-staffed crisis resources, and (c) routing the conversation to a
simulated administrator review queue so a human-in-the-loop can audit the
system's behavior.

Built for **DSCI 305 (Spring 2026)** — final project on data/AI ethics.

---

## What this is (and is not)

**Is:** an end-to-end prototype showing how a guardrail layer, an admin
escalation queue, and crisis-resource redirection can be wired around any LLM
backend. It is intended as a teaching artifact and a basis for further
research, not a production safety system.

**Is not:** a substitute for clinical judgment, a deployable service for
people in distress, or a validated mental-health tool. The rule-based
detector has known false-positive and false-negative modes that are
documented in `docs/ethics-mapping.md`.

## Architecture

```
┌──────────┐    ┌────────────────────────────────────────────────┐
│ chat UI  │───▶│ FastAPI                                         │
│ (HTML/JS)│◀───│  ├── /api/chat                                  │
└──────────┘    │  │    1. inbound guardrail (rule-based)         │
                │  │    2. if MEDIUM/HIGH → return crisis message │
                │  │       and skip the LLM                       │
                │  │    3. else → call OpenRouter (LLM)           │
                │  │    4. outbound guardrail on LLM reply        │
                │  │    5. log escalations to SQLite              │
                │  ├── /admin (HTTP Basic)                        │
                │  └── /api/admin/escalations                     │
                └────────────────────────────────────────────────┘
                              │
                              ▼
                       SQLite (./data/app.db)
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

## Repo layout

```
app/
  main.py              FastAPI app + routes
  guardrail.py         Rule-based crisis-language detector
  llm.py               OpenRouter chat client + safety system prompt
  crisis_resources.py  Hotline numbers + canned safe response
  db.py                SQLite schema + helpers
  config.py            Env-driven settings
  static/              Chat UI + admin dashboard (HTML/JS)
docs/
  written-component.md NIST-RMF-aligned written deliverable (<1000 words)
  architecture.md      System diagram + dataflow
  ethics-mapping.md    Explicit framework mapping + known limits
tests/
  test_guardrail.py    Unit tests for the detector
docker-compose.yml
Dockerfile
requirements.txt
```

## Ethical framework

This project is aligned with the **NIST AI Risk Management Framework (2023)**
(Govern / Map / Measure / Manage), and informed by the **Belmont Report**'s
principle of beneficence and the course's emphasis on
**human-in-the-loop**. See `docs/ethics-mapping.md` for the explicit mapping.

## License

MIT — see `LICENSE`.
