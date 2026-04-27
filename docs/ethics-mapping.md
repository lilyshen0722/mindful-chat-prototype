# Ethics framework mapping

This file documents how the prototype maps onto the **NIST AI Risk
Management Framework (AI RMF 1.0, 2023)** and onto the course's recurring
Belmont / human-in-the-loop themes. It also documents the prototype's
known limitations, because honesty about failure modes is itself a
required deliverable of the framework.

For the *concrete* failure surface (specific threats, mitigations,
residual risks), see `docs/threat-model.md`. For *how to operate* the
prototype, see `docs/user-guide.md`. For the *required course
deliverable* (audience / framework / impact, < 1000 words), see
`docs/written-component.md`.

## Rubric crosswalk

The DSCI 305 final-project rubric has five criteria. This is where each
is addressed in the artifact:

| Rubric criterion | Where it lives in this repo |
|---|---|
| **Problem / Question (20%)** | `docs/written-component.md` §1 ("Problem & motivation"); `README.md` opening paragraphs frame the problem as "how should an LLM chatbot handle disclosed distress, and how do you know it's doing so safely?" |
| **Framework Application (25%)** | This file — function-by-function NIST AI RMF mapping below; Belmont alignment; course-themes section. `docs/threat-model.md` makes the *Map* function concrete. The tiered cap design (regex up to HIGH, ML at LOW, LLM-judge at MEDIUM) is itself a framework-driven choice and is documented in the second-tier and third-tier sections below. |
| **Execution / Quality (30%)** | `app/` source code; `tests/test_guardrail.py`; the iterative commit history (each new mitigation paired with a smoke test). `docs/architecture.md` documents the layering. |
| **Impact / Utility (15%)** | `docs/written-component.md` §3; "What this is and is not" section of `README.md`; with `ENABLE_LLM_JUDGE=false` the prototype runs primarily offline (only the chat LLM call leaves the host), and either ML or judge tier can be disabled to suit a deployer's privacy / cost / latency profile — relevant properties for a campus deployment. |
| **Documentation (10%)** | `README.md`, `docs/user-guide.md`, `docs/architecture.md`, this file, `docs/threat-model.md`, `docs/written-component.md`. Each commit message explains the *why*, not just the *what*. |

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
| Identify potential risks and impacts                  | `docs/threat-model.md` (T1–T11) plus the "Limitations" section in this file |

### Measure

| AI RMF expectation                                    | How this repo addresses it                                                   |
|-------------------------------------------------------|------------------------------------------------------------------------------|
| Identify appropriate methods and metrics              | Risk levels NONE / LOW / MEDIUM / HIGH; per-tier signal sources (`input` / `ml-classifier` / `llm-judge` / `pattern` / `output` / `divergence`, plus `*-while-paused` variants) so each tier's contribution is separately measurable from the admin queue alone |
| Track AI risk through measurement and assessment      | Every escalation persisted with matched signals (regex matches *and* per-label ML scores); admin dashboard + per-conversation review page expose the audit trail |
| Track regression                                      | `tests/test_guardrail.py` (17 tests) covers each regex tier (LOW / MEDIUM / HIGH / pattern / merge_risk) and pins regressions for previously-missed phrasings ("feeling really down today", "I don't have any friends at school", "I want to end all of this", "put an end to everything"). Pinned ML model weights mean classifier behavior stays comparable across runs; the LLM-judge tier is exercised via Playwright + httpx smoke tests against a running container |

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
  notified at the moment of escalation, can open any conversation in a
  chat-style focused review page (`/admin/conversations/{cid}`), and can
  actively intervene by pausing the bot
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

## Second-tier emotion classifier (ML tier)

To close coverage gaps that the regex tier inevitably has, a second tier
runs `SamLowe/roberta-base-go_emotions` (a pretrained 28-emotion
multi-label classifier from Hugging Face) on every inbound message that
the regex didn't already classify. If any of a deliberately conservative
set of negative-affect labels (`sadness`, `grief`, `disappointment`,
`remorse`, `fear`, `nervousness`) crosses the configured threshold, the
inbound risk is elevated to `LOW` and the row is logged to the admin
queue with `source=ml-classifier` and the per-label scores embedded in
`matched_signals` for audit.

**Why this model and this design:**

- *NIST AI RMF Govern.* The model weights are pinned (specific HF repo
  + specific revision shipped via the Docker image). A reviewer can
  inspect the model card, the dataset (GoEmotions = Reddit comments
  labeled by crowd workers), and the inference path. By contrast, an
  LLM-judge tier would route to a third-party model that can change
  without notice.
- *NIST AI RMF Map.* The dataset's known biases — English-only, Reddit
  demographic skew, US-cultural framing of emotion words, possible
  noise in crowd labels — are nameable and citable rather than opaque.
- *NIST AI RMF Measure.* Frozen weights + deterministic inference mean
  the test suite stays meaningful over time. A regression test can
  pin "this phrase produces sadness ≥ 0.5" forever.
- *Belmont (Respect for Persons).* The classifier runs locally inside
  the same container; no additional user data egress to a third party
  beyond the LLM call we already make for the chat reply itself.
- *Course theme — interpretability and "scientism".* The classifier
  is *more* auditable than another LLM, not less. Per-message label
  scores let a reviewer interrogate "why did this fire?" — the kind
  of artifact the course materials repeatedly call for.

**Hard limit, by design.** The classifier can only ELEVATE inbound risk
from `NONE` to `LOW`. `MEDIUM` and `HIGH` stay reserved for explicit
ideation/plan/means signals from the regex tier and from the multi-turn
pattern aggregator. An emotion classifier should not fabricate clinical
urgency from emotional tone — that would be the kind of overreach the
course's "scientism" critique warns against.

**Failure mode.** If the model fails to load (e.g., HF unreachable in a
new build, weights corrupted), the classifier *fails open*: a warning
is logged, every call returns `NONE`, and the chat continues to operate
on the regex tier alone. This is intentional — a broken second tier
should not take the system offline.

**What a production deployment would add next.** A trained domain
classifier (e.g., fine-tuned on CLPsych or a curated mental-health
corpus rather than GoEmotions/Reddit) plus continuous re-evaluation of
label thresholds against fresh ground-truth audited by clinical
reviewers.

## Third-tier LLM-judge

When the regex tier and the ML classifier *both* return NONE, a third
tier — a configurable LLM acting as a safety classifier — is consulted.
It receives the message and a strict system prompt asking for a
structured `{risk, reason}` JSON classification. The judge's reason is
embedded in `matched_signals` so reviewers can audit *why* it fired.

**Why this tier exists:**

- It catches the failure mode where regex misses a phrase semantically
  *and* go_emotions classifies it as something outside our distress
  label set (e.g., euphemistic suicidality reading as `desire` ≈ 0.80).
- An LLM with a deliberately conservative system prompt can read the
  message holistically — distinguishing "end this Zoom call" (NONE)
  from "I'm just so done with everything, I want it all to be over"
  (MEDIUM) — without us enumerating regex patterns for every
  permutation.

**Hard limit, by prompt design.** The judge is instructed to only
return `NONE`, `LOW`, or `MEDIUM`. `HIGH` stays reserved for the
regex tier's explicit plan/means/time signals. An LLM reading
ambiguous text shouldn't fabricate clinical urgency.

**Failure mode.** Fail open: provider quota, network flake, malformed
JSON, empty content (some reasoning models exhaust their token budget
on hidden reasoning before emitting any visible output) — all return
NONE with a logged warning. The first two tiers still ran.

**Latency disclosure.** A judge call adds ~1–2s before the chat stream
starts. The user sees the typing-indicator dots that long. Toggle off
via `ENABLE_LLM_JUDGE=false` for latency-sensitive demos. Skipped
entirely for short messages (`LLM_JUDGE_MIN_WORDS`, default 6) and when
the prior tiers already classified the message.

**Reflexive ethics caveat.** This is "AI evaluating AI" — a topic the
course materials specifically flag for scrutiny ("Drafting Ethics with
AI: Is it ethically wise or logically sound to use LLMs to draft the
very AI policies and ethical codes meant to govern them?"). We accept
the critique and partially mitigate it three ways: (a) the judge
cannot elevate to HIGH; (b) every judge classification is logged with
its reasoning so a human reviewer audits the judgments, not just the
outcomes; (c) the judge model is configurable, so an operator can
deliberately route judge traffic to a *different vendor* than the chat
LLM to avoid same-vendor cross-contamination.

## Known limitations

These are intentionally documented (not buried) because the framework
expects "residual risk" to be acknowledged. Each numbered item links to
the threat-model entry where applicable.

1. **Rule-based detection is a starting point, not a clinical
   instrument** *(threat-model T2)*. It will miss oblique, coded,
   multilingual, or sarcastic expressions of distress. It will also
   fire on figurative speech, song lyrics, and third-person discussion.
   The pattern set is patched iteratively when reviewer audit surfaces a
   miss. Two examples worth recording (each paired with a regression
   test in `tests/test_guardrail.py`):
   - **LOW gap:** *"feeling really down today"* and *"I don't have
     any friends at school"* were originally classified NONE because
     the LOW pattern set only covered `tired|exhausted|hopeless|...`
     and didn't include `sad|depressed|down|lonely|isolated|overwhelmed|broken`
     or social-isolation phrasings.
   - **MEDIUM gap:** *"I want to end all of this"* and *"by 'ending
     this', I really mean it, put an end to everything"* were missed
     because the MEDIUM regex only covered `end my life` / `end it all`,
     not the broader euphemistic family `end (everything | all of this | this all)`
     or the `put an end to ...` paraphrase. The ML tier *also* missed
     these — go_emotions rates "I want to end everything" as `desire`
     (≈0.80), which is correctly excluded from our distress label set
     because it would over-trigger on benign wants. Owning euphemistic
     ideation in regex is the disciplined fix; an LLM-judge tier would
     handle these natively.

   Each patch is paired with a regression test plus a *negative*
   regression test confirming benign uses ("end this conversation",
   "put an end to my subscription") still classify NONE. The ML tier
   (item 3 below) closes some LOW-tier gaps; an LLM-judge tier would
   close more, especially the euphemistic-MEDIUM family.
2. **English-only.** All patterns, the LLM system prompt, and the canned
   safe template are in English. Non-English speakers are at risk of
   being missed at every tier — the regex doesn't match, the GoEmotions
   classifier was trained on English Reddit, and the LLM's safety prompt
   is English. Internationalization is real work, not a translation
   pass.
3. **The ML classifier inherits its training data's biases.** The
   second-tier classifier (`SamLowe/roberta-base-go_emotions`) was
   trained on the GoEmotions dataset, which is Reddit comments labeled
   by crowd workers. That distribution is younger, more US-centric,
   more Anglophone, and more "online vernacular" than the general
   population a campus chat tool would serve. The classifier may
   underperform on phrasings that don't look like Reddit. We mitigate
   this by *capping* its impact at LOW (it can never elevate to MEDIUM
   or HIGH) and by surfacing per-label scores in `matched_signals` so a
   reviewer can audit decisions; we do not pretend it's clinically
   validated.
4. **No clinical-corpus classifier.** A production deployment would
   add a classifier fine-tuned on a curated mental-health corpus
   (e.g., CLPsych) audited by clinicians, replacing the consumer-data
   GoEmotions classifier we ship. The LLM-judge third tier (now
   wired) partially compensates for the missing clinical corpus, but
   neither tier is clinically validated and neither claims to be.
5. **No red-team / adversarial test cases shipped.** The prototype
   documents the need for red-teaming (and the course materials cite it
   as a discipline) but does not ship adversarial test cases. A future
   contributor should add a `tests/test_adversarial.py` covering jailbreak
   prompts, multi-turn manipulation, and known crisis-vocabulary
   evasions.
6. **HTTP Basic admin auth is for local demos only** *(threat-model T5,
   T8)*. Any real deployment would need real auth (SSO / OIDC), audit
   logs of reviewer actions, TLS, and CSRF protection.
7. **OpenRouter is a third-party processor** *(threat-model T6)*.
   Anything sent to the chat endpoint reaches OpenRouter and the chosen
   upstream model. The README and `.env.example` name the model so a
   reviewer can assess that processor's terms before any deployment.
8. **No notification channel for reviewers.** The admin dashboard
   auto-refreshes, but there is no email, Slack, paging, or SLA.
   Reviewer attention is a human factor not addressed by this
   prototype's scope.
9. **No consent flow for takeover.** When a reviewer takes over, the
   user sees the badge and per-message attribution, but has not been
   asked up front to consent to potential human review. A real
   deployment would need an upfront notice ("messages are reviewed by
   a human if our system flags them as concerning") in the chat banner
   *before* the user starts typing.

When in doubt, the repo defaults to the safer behavior: log it, surface
it to a human, and refer the user to a trained crisis line.
