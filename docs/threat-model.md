# Threat model

What can go wrong with this prototype, what mitigates each thing,
what residual risk remains, and where the evidence lives. The
companion to `docs/ethics-mapping.md`: that doc maps the project to
the *frameworks*; this one names the *concrete* failure surface.
Serves the NIST AI RMF Map function ("identify potential risks and
impacts").

---

## Assets being protected

1. **The user.** A person who may be in distress and is interacting with
   an LLM-powered chat. The primary harm to mitigate is the user being
   given unsafe content (methods of self-harm, dismissive responses to
   ideation, false reassurance) or being silently failed (distress
   reaching no one).
2. **The reviewer / human-in-the-loop.** Their attention is a finite
   resource. False positives that bury real signals are a harm.
3. **The audit trail.** Anyone reviewing the system after the fact —
   instructor, researcher, downstream forker — needs to be able to
   reconstruct what happened and why. Loss of audit data is a harm to
   accountability.

## Adversaries / failure agents (not all malicious)

- The user themselves (in distress, using oblique or sarcastic language).
- The LLM (hallucinating, broadening categories, citing wrong resources).
- The regex / ML detector (coverage gaps, false positives).
- A future operator (treating the prototype as production-ready, deploying
  it without the documented additional safeguards).

---

## Threats and mitigations

Each threat is named (`Tn`), described, mapped to its mitigations and
residual risk, and points at the concrete code or doc that addresses it.

### T1 — LLM produces unsafe content (methods of self-harm, harmful advice)

- **Mitigations:**
  1. System prompt explicitly forbids method-of-harm discussion, clinical
     advice, and disclosure-asking (`app/llm.py:_BASE_PROMPT`).
  2. Outbound regex tier (`app/guardrail.py.assess` re-run on the LLM's
     reply in `app/main.py`). On match, the reply is *replaced* with the
     safe template in `app/crisis_resources.py.CRISIS_MESSAGE`.
  3. Row logged as `source=output` so the reviewer sees model failure.
- **Residual risk:** the regex coverage isn't perfect — methods can be
  obliquely described in prose that doesn't trip explicit patterns. This
  is the strongest argument for an LLM-judge third tier.
- **Evidence:** `tests/test_guardrail.py::test_high_*`, manual smoke tests.

### T2 — Distress message missed by all detectors

- **Mitigations:**
  1. First tier — regex with deliberately broad LOW patterns + iteratively
     patched MEDIUM euphemism patterns (`app/guardrail.py.LOW_PATTERNS`,
     `MEDIUM_PATTERNS`).
  2. Second tier — `SamLowe/roberta-base-go_emotions` classifier
     (`app/ml_classifier.py`). Catches phrases the regex misses
     (e.g., "I miss my old friends", "ugh today was rough").
  3. Third tier — LLM judge (`app/llm_judge.py`). Catches euphemistic
     ideation and contextually-clear distress that neither regex nor
     emotion classification owns cleanly.
  4. Multi-turn pattern aggregator (`assess_pattern`) elevates risk when a
     conversation drifts concerning over multiple turns even if no single
     turn hits MEDIUM.
  5. The full transcript is *always* visible to the reviewer in
     `/admin/conversations/{cid}`, so a missed detector signal can still
     be caught by an attentive reviewer reading context.
- **Residual risk:** detectors are English-only; each tier reflects its
  data lineage's biases (regex ≈ author's English; ML ≈ Reddit
  GoEmotions; LLM judge ≈ whatever its training corpus was). Coded
  language, multilingual users, and adversarial phrasing all leak
  through. The LLM judge is also "AI evaluating AI" — partially
  mitigated by the cap at MEDIUM and audit logging of every judgment,
  but worth scrutinizing per the course's "drafting ethics with AI"
  critique.
- **Evidence:** `tests/test_guardrail.py::test_low_catches_*`,
  `test_medium_catches_*`, `test_pattern_*`; ML and judge tiers
  exercised via Playwright + httpx smoke scripts run against a live
  container (not committed because they require a running OpenRouter
  key and the loaded HF classifier).

### T3 — False positive escalations burn out the reviewer

- **Mitigations:**
  1. NONE-risk turns produce no admin row.
  2. LOW does *not* push 988 in the bot's reply; the system prompt
     explicitly instructs against it.
  3. `pattern` and `divergence` rows dedupe while one is still
     unacknowledged for the same cid (`db.has_open_escalation_for_source`).
- **Residual risk:** song lyrics, third-person discussion ("my friend
  said she wants to die"), and quoted text will still trip the regex.
  Reviewer must be trained to read the surrounding context.
- **Evidence:** `app/main.py` source-routing logic; verified by
  Playwright smoke run against a live container (5 LOWs in a row →
  exactly 1 pattern row; ack → fresh pattern row fires on next LOW).

### T4 — Disconnect mid-stream silently drops the safety signal

This was an actual bug found by smoke testing in the browser.

- **Mitigation:** inbound + pattern logging happens *before* the SSE
  generator begins streaming, so a client disconnect that cancels the
  generator can't lose the inbound signal. The relevant logic lives at
  the top of the `chat_endpoint` handler in `app/main.py`.
- **Residual risk:** outbound and divergence checks still run inside the
  generator (they require the full reply). A client that disconnects
  before the LLM finishes will lose those — but those are detector
  signals on the bot's *own* output, and the bot's reply also wasn't
  seen by the user, so the harm surface is bounded.

### T5 — Reviewer impersonation / takeover misuse

- **Mitigations:**
  1. `/admin` and `/api/admin/*` require HTTP Basic auth.
  2. Reviewer messages are stamped with `risk_level='human-reviewer'` so
     the audit log distinguishes them from bot replies.
  3. The user-facing chat shows a small "answered by a human reviewer"
     caption beneath each reviewer bubble, plus a "human reviewer engaged"
     badge in the header while paused.
- **Residual risk:** HTTP Basic is for local demo only. There is no audit
  log of *who* the reviewer was beyond the basic-auth username, no rate
  limiting, no consent flow that warns the user up front that a human
  may join. This is documented as unsuitable for production in
  `docs/ethics-mapping.md`.

### T6 — Data exfiltration via OpenRouter

- **Mitigations:**
  1. No PII collected by design (`docs/ethics-mapping.md`, "Multi-conversation
     context"). The only identifier is a client-generated UUID.
  2. The model + base URL are configurable, so a deployer can pin to a
     compliant provider (self-hosted, on-prem, BAA-covered).
  3. The ML classifier runs locally — the second tier doesn't add
     additional egress.
- **Residual risk:** the conversation content itself reaches OpenRouter
  and the chosen upstream model. Any deployer is responsible for that
  third party's terms applying to the use case. The `.env` and README
  surface this explicitly.

### T7 — Stored XSS via user content rendered in the admin UI

- **Mitigations:**
  1. All user content and bot content is HTML-escaped (`escapeHtml`) in
     both `chat.html` and `admin.html` before being inserted via
     `innerHTML`.
  2. The minimal Markdown subset re-introduced (bold, links, newlines)
     operates on already-escaped strings.
  3. The admin view never executes user-supplied JS; reviewer messages
     are also escaped.
- **Residual risk:** if a future contributor adds a new render path that
  forgets to escape, the admin view would be the highest-impact target.
  Bug class is well-known and contained.

### T8 — Replay / CSRF on admin endpoints

- **Mitigations:** HTTP Basic on every `/api/admin/*` route. SameSite
  cookie behavior is irrelevant since auth is per-request basic.
- **Residual risk:** no CSRF tokens, no rate limiting. Acceptable for
  localhost demo; documented as inadequate for production.

### T9 — ML classifier or LLM-judge load/runtime failure

- **Mitigation:** both tiers *fail open*. `app/ml_classifier.py` returns
  NONE if the model can't load (HF unreachable, weights corrupted).
  `app/llm_judge.py` returns NONE on provider quota errors, malformed
  JSON, empty content (some reasoning models exhaust their token budget
  on hidden reasoning before emitting any visible output), or timeout.
  Whichever tier fails, the others still run.
- **Residual risk:** silent loss of a tier could let oblique distress
  slip through unnoticed. The container logs the warning, but there is
  no alerting layer in this prototype.

### T10 — Conversation_state race during takeover

- **Scenario:** reviewer pauses the bot while a `/api/chat` call is mid-
  stream.
- **Mitigation:** state is checked at the start of `/api/chat`. The
  in-flight call already past the check streams to completion; the *next*
  user message gets the paused notice.
- **Residual risk:** a user may receive one bot reply after the reviewer
  thinks they've paused. Acceptable: the reply was already a draft the
  reviewer can audit; nothing harmful flows from the brief delay.

### T11 — Treating the prototype as production-ready

This is the meta-threat the documentation is designed to defuse.

- **Mitigations:**
  1. `README.md` opens with a bold "not a deployable crisis service"
     warning.
  2. Chat UI carries a persistent banner with 988.
  3. `LICENSE` (MIT) does not imply fitness for any purpose.
  4. `docs/ethics-mapping.md` enumerates known limits.
- **Residual risk:** legal disclaimers don't stop deployment. A bad-faith
  forker could deploy this anywhere. The honest mitigation is that the
  artifact remains *less harmful* than building from scratch and
  forgetting layers — but a deployer making good-faith use is encouraged
  to consult an ethicist + a clinical reviewer before going live.

---

## What's *not* in scope for this prototype's threat model

- DDoS / availability (no SLA; localhost-only).
- Adversarial prompt injection (the LLM's own behavior is treated as
  untrusted, but injection attacks aren't actively red-teamed).
- Long-term data retention / GDPR / right-to-be-forgotten flows.
- Cross-conversation correlation attacks (would matter if `users` table
  existed, but it doesn't).

These are real threats for any production deployment and are listed
under "What a production deployment would add next" in
`docs/ethics-mapping.md`.
