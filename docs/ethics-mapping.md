# Ethics framework mapping

This file documents how the prototype maps onto the **NIST AI Risk
Management Framework (AI RMF 1.0, 2023)** and onto the course's recurring
Belmont / human-in-the-loop themes. It also documents the prototype's known
limitations, because honesty about failure modes is itself a required
deliverable of the framework.

## NIST AI RMF — function-by-function mapping

### Govern

| AI RMF expectation                                    | How this repo addresses it                                                   |
|-------------------------------------------------------|------------------------------------------------------------------------------|
| Document AI system policies and accountability        | `README.md` (intent + scope), `docs/written-component.md` (audience + impact) |
| Manage AI risks throughout the lifecycle              | This file plus tests in `tests/test_guardrail.py` for the detector           |
| Address AI risks of third-party data, models, software | OpenRouter is documented in `docs/architecture.md`; model is configurable    |
| Maintain a culture that prioritizes safety            | UI banner + LLM system prompt + crisis-line template all reinforce safety    |

### Map

| AI RMF expectation                                    | How this repo addresses it                                                   |
|-------------------------------------------------------|------------------------------------------------------------------------------|
| Establish and understand the context                  | "What this is and is not" section of `README.md`                             |
| Categorize the AI system                              | Documented as a high-stakes-domain *prototype*, not a deployable service     |
| Identify potential risks and impacts                  | "Limitations" sections in this file and in `written-component.md`            |

### Measure

| AI RMF expectation                                    | How this repo addresses it                                                   |
|-------------------------------------------------------|------------------------------------------------------------------------------|
| Identify appropriate methods and metrics              | Risk levels NONE / LOW / MEDIUM / HIGH; tests assert each level              |
| Track AI risk through measurement and assessment      | Every escalation persisted with matched signals; admin dashboard exposes them |
| Track regression                                      | `tests/test_guardrail.py` catches regressions in pattern matching            |

### Manage

| AI RMF expectation                                    | How this repo addresses it                                                   |
|-------------------------------------------------------|------------------------------------------------------------------------------|
| Prioritize and respond to risks based on impact       | Risk-aware system prompt makes the LLM more attentive on LOW/MEDIUM/HIGH; multi-turn pattern aggregation elevates tone when a single message wouldn't; a soft 988 footer is appended only if the model omitted any resource; outbound guardrail still hard-replaces unsafe LLM output with the safe template |
| Allocate resources to manage risk                     | Human-in-the-loop admin queue at `/admin` plus active **takeover** controls — reviewer can pause the bot and inject messages directly into the conversation; the user sees a "human reviewer engaged" badge so the handoff is transparent |
| Detect model-policy divergence                        | Even when the rule-based guardrail rates a turn NONE, if the LLM volunteered a crisis resource the event is logged as `source=divergence` so reviewers can audit drift between documented policy and model behavior |
| Document residual risk                                | "Known limitations" section below                                            |

## Design philosophy: peer-like support, not crisis substitute

A central design question for any "mindful" chatbot is: *should the AI guide
the user through difficult feelings, or should it hand off to a human as
soon as anything concerning appears?*

This prototype takes a **tiered, peer-like-support stance** rather than an
"escalate-and-stop" stance. The reasoning:

- The vast majority of "negative" content in everyday chat is normal venting
  — frustration with school, work, relationships, ordinary sadness. Pushing
  crisis hotlines on these turns is dismissive, burns out human reviewers
  with false-positive escalations, and discourages the user from continuing.
- For genuinely concerning content, an immediate handoff that ends the
  conversation can feel rejecting and may discourage the user from seeking
  further help. Real systems (e.g., Crisis Text Line) use AI for *triage*
  but trained humans for the actual crisis chat — but they keep the user
  engaged, not bounced.
- The AI is therefore designed to engage warmly across the full risk
  spectrum, with the *intensity of resource mention* scaling with the
  guardrail signal (NONE = none, LOW = none, MEDIUM = one soft mention,
  HIGH = urgent + safety check). Outbound guardrail and the human-in-the-
  loop admin queue provide the safety floor.

The principle, encoded in the system prompt and enforced by tests:

> The AI is **peer-like support**, not a substitute for crisis care. It
> can listen, validate, and encourage talking to professionals. It must
> NEVER diagnose, prescribe, suggest methods, or guide the user toward
> harmful action.

A more conservative design — "AI triages, humans take over" — is
defensible and would be appropriate for any high-stakes deployment. The
prototype actually supports both modes: by default the AI engages across
all risk levels, but a reviewer can **pause the bot** for any conversation
from the admin dashboard. While paused, the LLM is bypassed entirely and
user messages get a short notice that a human is engaged; the reviewer can
then chat directly with the user. This means the *same artifact* can
demonstrate the tiered-engagement design and the conservative
triage-and-handoff design, depending on how a reviewer chooses to operate
it.

### Takeover transparency: hybrid attribution

When a reviewer sends a message, it renders in the user's chat with the
same bubble shape as a bot reply, *plus* (a) a small italic caption
"answered by a human reviewer" beneath the bubble, and (b) a persistent
"human reviewer engaged" badge in the chat header while the conversation
is paused. The bubble shape is shared with the bot intentionally — the
reviewer is "answering as the bot" so the user's mental model stays
continuous — but the caption and header badge keep the handoff visible.

A fully covert takeover (no caption, no badge) was rejected: it would
violate the course's transparency principle and the Belmont commitment to
respect for persons. A loud takeover with a distinct bubble color was
also rejected because it makes the reviewer feel like a different system
bolted on, which discourages reviewers from intervening at all. The
hybrid keeps the audit trail honest while preserving conversational
continuity.

### When does AI guide vs. hand off? (Operational rules encoded in code)

| Effective risk | AI behavior                                                | Human behavior                                                  |
|----------------|------------------------------------------------------------|-----------------------------------------------------------------|
| NONE           | Normal chat. **No** crisis resources, no admin queue noise.| Nothing — don't burn out reviewers on normal venting.           |
| LOW            | Validate + one open question. Still no resources.          | Logged for review (input).                                      |
| Pattern        | Tone elevated to MEDIUM (gentle resource mention).         | Logged separately (pattern source) — emerging concern.          |
| MEDIUM         | Validate + one soft 988 mention. Stay engaged.             | Logged (input). Reviewer may take over if they choose.          |
| HIGH           | Validate strongly + urgent 988 + safety check.             | Logged (input). Reviewer notified; common case for takeover.    |
| Divergence     | Bot already gave the resource — no further action needed.  | Logged (divergence) — reviewer audits model drift, not the user.|

The key invariant: **the AI must never guide the user toward a negative
action.** The system prompt forbids naming methods of self-harm, and the
outbound guardrail catches an unsafe model reply and replaces it with the
safe template. If a hard handoff is needed, the reviewer pauses the bot.

## Belmont alignment

- **Beneficence ("do no harm").** The system errs on the side of redirecting
  the user to human help rather than trying to solve distress with an LLM,
  which could hallucinate harmful content. The LLM is forbidden by its
  system prompt from giving clinical advice or naming methods of self-harm.
- **Respect for persons.** No identifying information (full names,
  addresses, etc.) is collected; the only identifier persisted is the
  client-generated `conversation_id` (a UUID stored in `localStorage`). The
  LLM system prompt instructs the model not to ask for identifying details.
- **Justice.** The crisis-resource template includes both US lines (988,
  Crisis Text Line, SAMHSA) and a link to the international IASP directory,
  so non-US users are not left without a referral.

## Course-specific themes

- **Human-in-the-loop.** Every escalation is logged and surfaced on a
  reviewer dashboard. The bot's output is treated as a *draft* (per the
  course materials) — a human reviewer can audit it after the fact, is
  notified at the moment of escalation, can drill into the full
  surrounding transcript, and can actively intervene by pausing the bot
  and chatting with the user directly. Reviewer messages are persisted
  with a distinct `risk_level='human-reviewer'` marker for audit.
- **Reproducibility.** The detector is rule-based and version-controlled, so
  any researcher can trace why a given message was classified the way it
  was. Tests cover each risk level.
- **Transparency vs. protection.** The repo is private during the course,
  the SQLite database is local-only, and the `.env` file is gitignored —
  protecting any test data — while the code is fully transparent.

## Multi-conversation context

A single browser can hold multiple parallel conversations: the client
keeps a list of `conversation_id`s in `localStorage` and the user can
switch between them via a sidebar. This is intentional for two reasons.
First, "New conversation" should not erase prior context — a user (and a
reviewer) need to be able to refer back to earlier threads. Second, the
prototype is single-user-per-browser by design: there is no `users`
table, no account creation, no PII collected. A `conversation_id` is an
opaque UUID generated client-side, which means the only thing the server
can attribute to a "person" is a browser's view of localStorage. This is
intentional and worth surfacing as both a privacy property (no PII) and
a limitation (a real deployment with multi-device sync would need real
identity, with all the data-handling obligations that brings).

## Known limitations

These are intentionally documented (not buried) because the framework
expects "residual risk" to be acknowledged:

1. **Rule-based detection is a starting point, not a clinical instrument.**
   It will miss oblique, coded, multilingual, or sarcastic expressions of
   distress. It will also fire on figurative speech, song lyrics, and
   third-person discussion.
2. **English-only.** All patterns and the canned safe template are in
   English. Non-English speakers are at risk of being missed.
3. **No trained classifier or LLM judge tier.** A production system should
   layer at least one ML classifier and an LLM judge on top of the rule
   set, then re-evaluate against fresh ground-truth labels periodically.
4. **No abuse / red-team testing in code.** The prototype documents the
   need for red-teaming but does not ship adversarial test cases.
5. **HTTP Basic admin auth is for local demos only.** Any real deployment
   would need real auth, audit logs, and TLS.
6. **OpenRouter is a third-party processor.** Anything sent to the chat
   endpoint reaches OpenRouter and the chosen upstream model. The README
   names the model so a reviewer can assess that processor's terms.

When in doubt, the repo defaults to the safer behavior: log it, surface it
to a human, and refer the user to a trained crisis line.
