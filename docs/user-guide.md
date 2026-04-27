# User Guide

This guide walks through using the prototype end-to-end. It covers the
**user-facing chat** (`/`), the **admin dashboard** (`/admin`), the
**per-conversation review page** (`/admin/conversations/{cid}`), and the
configuration knobs that change behavior.

Audiences:

- **Course reviewer / instructor.** Follow the [demo script](#demo-script-for-graders)
  to verify each rubric-relevant behavior in a few minutes.
- **Researcher / forker.** See [Configuration](#configuration) and
  [Extending](#extending) for what's tunable.
- **Reviewer in the takeover scenario.** See [Reviewer workflow](#reviewer-workflow).

---

## Running the prototype

### Docker Compose (recommended)

```bash
cp .env.example .env
# open .env and paste your OPENROUTER_API_KEY (free models work)
docker compose up --build
```

The first build is slow (~3 minutes) because it downloads PyTorch
(CPU build) plus the HuggingFace classifier weights so the second tier
is warm on first request. The third-tier LLM-judge does not require a
build-time download — it calls OpenRouter at request time, so it boots
instantly. Subsequent builds use the cached layer.

Open:

- Chat: <http://localhost:8000/>
- Admin: <http://localhost:8000/admin> (default `admin` / `change-me-locally`,
  configurable via `.env`)

If port 8000 is in use, set `HOST_PORT=8001` (or any free port) in `.env`.

### Local development (no Docker)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill in OPENROUTER_API_KEY
mkdir -p data
DATABASE_PATH=./data/app.db uvicorn app.main:app --reload
```

To run without the ML classifier (faster install, smaller footprint, regex
tier only): set `ENABLE_ML_CLASSIFIER=false` in `.env`.

### Tests

```bash
pip install pytest
pytest -q
```

There are 17 unit tests covering each regex tier (LOW / MEDIUM / HIGH /
pattern / merge_risk) and a regression suite for previously-missed
phrasings. The ML and LLM-judge tiers are exercised via Playwright +
httpx smoke tests against a running container.

---

## Chat workflow (user side)

1. The chat page (`/`) opens with a 988 banner and a sidebar listing your
   conversations.
2. Each conversation has its own UUID stored in `localStorage`. The same
   browser sees all your prior conversations in the sidebar; a different
   browser / incognito window sees a fresh slate.
3. **Typing a message** sends it to `/api/chat`, which streams the bot's
   reply back via Server-Sent Events. The bubble appears immediately and
   tokens fill in as they arrive.
4. The system prompt sent to the LLM is *risk-aware*: it adapts its tone
   based on the inbound risk classification.
5. **`+ New`** in the sidebar starts a fresh conversation without
   discarding the current one.
6. If the conversation is paused for human-reviewer takeover, a "human
   reviewer engaged" badge appears in the chat header. New user messages
   get a notice that a reviewer will respond; the bot is bypassed.

### What each risk level does, from the user's perspective

| If you say… | Effective risk | What you see |
|---|---|---|
| "What's a good study schedule?" | NONE | Normal helpful reply. No 988. |
| "ugh I keep messing up" *(emotion classifier picks up disappointment)* | LOW (via ML) | Validating reply. No 988. Logged for review. |
| "I'm exhausted lately" *(regex)* | LOW | Validating reply + one open question. No 988. |
| Three LOW-ish messages in a row | MEDIUM via pattern | Bot tone elevates: gentle 988 mention, stays engaged. |
| "I sometimes want to die" | MEDIUM | Validation + one soft 988 mention. |
| "I have the pills tonight" | HIGH | Urgent tone, prominent 988, asks if user is safe. |

You can verify these behaviors in the [demo script](#demo-script-for-graders).

---

## Admin dashboard (`/admin`)

Lists every escalation across every conversation, newest first. Auto-refreshes
every 3 seconds (toggleable).

### Columns

| Column | What it shows |
|---|---|
| ID | Internal escalation row id |
| When | Server timestamp |
| Risk | NONE / LOW / MEDIUM / HIGH / DIVERGENCE |
| Source | Which detector layer fired (see table below) |
| Conversation | Click the cid (or **Open**) to view in chat-style review page |
| User message | The message that triggered the row (truncated) |
| Matched signals | JSON of regex matches and/or per-label ML scores |
| Status | Open / acknowledged-by/at |
| Actions | Acknowledge, Open, Take over / Resume bot |

### `source` values quick reference

| `source` | Meaning |
|---|---|
| `input` | User message tripped the regex tier directly. |
| `ml-classifier` | Regex returned NONE; the emotion classifier elevated to LOW. The matched signals show per-label scores like `ml:sadness=0.87`. |
| `llm-judge` | Regex *and* ML both returned NONE; the third-tier LLM judge classified LOW or MEDIUM. The judge's one-sentence reason is included in `matched_signals`. |
| `pattern` | Multi-turn rolling window tripped (3+ consecutive non-NONE user messages). Logged once per streak; ack to reset. |
| `output` | The LLM's own reply tripped the outbound regex (unsafe content); the reply was *replaced* with the safe template. |
| `divergence` | The LLM volunteered crisis resources on a NONE-risk turn. The reply was *not* modified — this row exists for audit so you can see model drift from documented policy. Deduped while one is open. |
| `input-while-paused`, `ml-classifier-while-paused`, `llm-judge-while-paused` | Same as the corresponding source, but the row was logged while the bot was paused for human takeover. |

### Acknowledging a row

Click **Acknowledge** to record reviewer + timestamp + optional notes. Acked
rows hide by default (toggle "Show only unacknowledged"). Acking a `pattern`
or `divergence` row also resets its dedup, so a fresh occurrence can fire
later if the situation continues.

---

## Reviewer workflow — focused conversation review page

Click any conversation_id (or the **Open** button on its row) to land on
`/admin/conversations/{cid}`. This page renders the conversation in
chat-bubble style — but from the reviewer's perspective: the user's
messages are on the **left** ("them"), the bot/reviewer messages are on
the **right** ("our side"). Bubble colors are kept consistent with the
user's own view so identity reads the same.

### Components on the review page

- **Header:** back to dashboard, conversation id, live state badge, turn
  count, **Take over** / **Resume bot** button.
- **Message pane:** auto-refreshes every 4 seconds, so a live conversation
  updates as the user types and as the bot replies.
- **Reviewer composer:** type a message, hit **Send as reviewer**. The
  message is saved with `risk_level='human-reviewer'`. The user-side chat
  picks it up via polling, renders it as a bot-style bubble with a small
  italic *"answered by a human reviewer"* caption.
- **Escalation sidebar:** every escalation row for this cid, with quick
  Ack buttons.

### Take over → reviewer → resume

1. **Take over.** Click "Take over" on the header (or in the dashboard row).
   Confirm the dialog. Server flips `conversation_state.state` to `'human'`.
2. **User experience.** The user's chat header shows "human reviewer
   engaged". If they send another message while paused, they see a notice
   that a human reviewer is engaged; the LLM is bypassed.
3. **Reviewer messages.** Type and send via the composer at the bottom of
   the focused review page. The user's chat polls and renders your message
   inline.
4. **Resume.** Click "Resume bot". The state flips back, the user's badge
   disappears, and the bot resumes generating replies.

The decision to send a reviewer message is *separate* from pausing — you
can chime in alongside the bot without pausing if you want, or pause to
fully take over. Both options are clearly labeled in the composer hint.

---

## Configuration

All knobs are environment variables (read from `.env` by `pydantic-settings`).

| Variable | Default | Effect |
|---|---|---|
| `OPENROUTER_API_KEY` | *(required)* | OpenRouter API key. Without it, `/api/chat` returns a configuration-error token. |
| `OPENROUTER_MODEL` | `nvidia/nemotron-nano-9b-v2:free` | Which model to call. Free OpenRouter models hit upstream quotas. Switch if 429s pile up. |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | Override for self-hosted gateways. |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD` | `admin` / `change-me-locally` | HTTP Basic credentials for `/admin` and `/api/admin/*`. |
| `HOST_PORT` | `8000` | Host port mapped to the container. |
| `DATABASE_PATH` | `/data/app.db` (Docker) | SQLite location. |
| `ENABLE_ML_CLASSIFIER` | `true` | Toggle the second-tier emotion classifier. Set `false` to run regex-only. |
| `ML_CLASSIFIER_MODEL` | `SamLowe/roberta-base-go_emotions` | HuggingFace model id. Pre-downloaded into the Docker image. |
| `ML_CLASSIFIER_THRESHOLD` | `0.4` | Per-label score threshold for elevation to LOW. Tuned for go_emotions; raise to reduce false positives, lower to catch more. |
| `ML_CLASSIFIER_MIN_WORDS` | `4` | Skip the classifier on very short messages ("Hi", "ok"). |
| `ENABLE_LLM_JUDGE` | `true` | Toggle the third-tier LLM judge. Disable to skip the ~1–2s extra latency it adds. |
| `LLM_JUDGE_MODEL` | *empty (= chat model)* | Override to use a different model for judge calls. Recommended: a non-reasoning model so the entire token budget goes to the JSON answer. |
| `LLM_JUDGE_MIN_WORDS` | `6` | Skip the judge on short messages. |
| `LLM_JUDGE_TIMEOUT` | `10.0` | Seconds before the judge call fails open. |

---

## Demo script for graders

A 5-minute walkthrough covering each rubric-relevant behavior. Run after
`docker compose up`.

1. **Sidebar + multi-conversation.** Open `/`. Send "hi". Click `+ New`,
   send another message. Click the older sidebar entry — content swaps.
2. **Regex tier.** Send "I'm so tired lately". Bot validates without 988.
   Open `/admin` → row with `source=input`, `risk=low`.
3. **ML tier.** Send "I miss my old friends a lot, it's been hard". Regex
   doesn't match this; classifier scores `sadness ≈ 0.9`. Row appears with
   `source=ml-classifier`, signals `["ml:sadness=0.91"]`.
3a. **LLM-judge tier.** Send "I'm just so done with everything, I want it
    all to be over". Regex misses (no enumerated euphemism), the ML
    classifier reads it as `desire`, and the third-tier judge picks it up
    as `risk=medium` with a one-sentence reason in `matched_signals`.
4. **Pattern.** Send three LOW-tone messages in a row in a fresh conversation.
   First two log as `input`. Third also logs a `pattern` row at MEDIUM —
   bot tone elevates with a gentle 988 mention.
5. **Acknowledge.** Click Acknowledge on the pattern row. It greys out.
6. **Open conversation.** Click the cid (or **Open**). You land on the
   chat-style review page; user messages on the left, bot on the right;
   escalation list on the right.
7. **Take over.** Click "Take over". Confirm. The state badge flips to
   "human reviewer engaged".
8. **Reviewer message.** From the composer at the bottom, type "Hi —
   checking in. How are you doing right now?" → Send. Switch to the user
   tab → header shows "human reviewer engaged" badge, message appears as
   a bot-style bubble with the "answered by a human reviewer" caption.
9. **Paused chat.** From the user tab, type another message. Bot is
   bypassed; user sees a notice that a reviewer is engaged. Admin's
   escalation list keeps growing if the user trips a detector while paused
   (`source=input-while-paused`).
10. **Resume.** Click "Resume bot". State flips back. New user messages
    get bot replies normally.
11. **Divergence (optional, non-deterministic).** Send a borderline-vague
    message ("I just feel weird today"). Some LLMs volunteer 988 anyway;
    if so, a `divergence` row appears.

Every step has a corresponding line in `tests/test_guardrail.py` or a
Playwright smoke test under `/tmp/smoke_*.py` (kept out of the repo since
they exercise external services).

---

## Extending

- **Add regex patterns** in `app/guardrail.py`. Pair each addition with a
  positive case + a negative regression case in `tests/test_guardrail.py`.
- **Tune the ML threshold** via `ML_CLASSIFIER_THRESHOLD`. Lower → more
  recall, more false positives. Per-message scores in
  `escalations.matched_signals` make tuning auditable.
- **Swap the ML model.** Set `ML_CLASSIFIER_MODEL` to any HF
  `text-classification` model that returns label scores. Update the
  `_DISTRESS_LABELS` set in `app/ml_classifier.py` to match the new
  taxonomy.
- **Replace the LLM** by changing `OPENROUTER_MODEL`. The system prompt
  in `app/llm.py` is model-agnostic.
- **Add a third tier (LLM-judge)** as future work — see
  `docs/ethics-mapping.md` "What a production deployment would add next".

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `[Configuration error] OPENROUTER_API_KEY is not set` | Missing key in `.env` | Add it, restart container |
| `[Upstream error from OpenRouter]` 429 | Free model quota | Switch `OPENROUTER_MODEL` |
| Sidebar empty | localStorage cleared | Send a message; sidebar populates |
| ML classifier never fires | `ENABLE_ML_CLASSIFIER=false` *or* model failed to load | Check container logs for `ml_classifier failed to load`; verify weights pre-download succeeded in the build |
| Admin page shows 401 | Wrong credentials | Re-enter `ADMIN_USERNAME` / `ADMIN_PASSWORD` |
| Reviewer message doesn't appear in user's chat | User tab paused polling (background tab) | Switch focus back; polling resumes within 4 s |
