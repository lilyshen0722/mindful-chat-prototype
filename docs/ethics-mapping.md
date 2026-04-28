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

The core design question for a chatbot like this is: should the AI
guide a user through hard feelings, or hand off to a human the moment
anything concerning appears?

I picked the first framing. A few reasons:

- Most "negative" content in everyday chat is normal venting:
  frustration with school, work, relationships, ordinary sadness.
  Pushing crisis hotlines on those turns is dismissive, burns out
  reviewers with false positives, and trains people not to disclose
  anything real.
- For genuinely concerning content, an abrupt handoff that ends the
  conversation can feel rejecting. Crisis Text Line and similar
  services use AI for triage but keep the user *engaged* with a
  trained human, not bounced.
- So the AI is meant to engage warmly across the whole risk spectrum,
  with the intensity of resource mention scaling with the signal
  (NONE = none, LOW = none, MEDIUM = one soft mention, HIGH = urgent
  + safety check). The outbound guardrail and the admin queue are
  the safety floor.

The rule encoded in the system prompt and the tests:

> The AI is peer-like support, not crisis care. It can listen,
> validate, and encourage talking to professionals. It must never
> diagnose, prescribe, suggest methods, or guide the user toward
> harmful action.

A more conservative "AI triages, humans take over" stance is also
defensible, especially for high-stakes deployments. The prototype
supports both: by default the AI engages across risk levels, but a
reviewer can pause the bot from the admin dashboard. Paused
conversations bypass the LLM and surface a notice that a human is
engaged; the reviewer chats with the user directly. The same artifact
runs both modes depending on operator choice.

### Takeover transparency

When a reviewer sends a message, the user sees a normal-shaped bot
bubble with a small italic caption ("answered by a human reviewer")
underneath. The conversation header carries a persistent "human
reviewer engaged" badge while paused.

I considered two alternatives and rejected both. A fully covert
takeover (no caption, no badge) violates the transparency principle
and Belmont's respect-for-persons. A loud takeover with a distinct
bubble color makes the reviewer feel bolted on, which discourages
intervention. The hybrid keeps the audit trail honest while
preserving conversational continuity.

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
- **Transparency vs. protection.** The SQLite database is local-only,
  the `.env` file is gitignored (so any test data + the OpenRouter key
  stay off GitHub), and the code is otherwise fully open for review.
  Anyone forking this should swap the default admin password and
  re-issue an OpenRouter key before running.

## Multi-conversation context

A single browser can hold multiple parallel conversations: the client
stores a list of `conversation_id`s in `localStorage` and the user
switches between them via a sidebar. Two reasons:

- "New conversation" should not erase prior context. A user (or a
  reviewer auditing them) needs to be able to refer back to earlier
  threads.
- The prototype is single-user-per-browser. There is no `users`
  table, no account creation, no PII collected. A `conversation_id`
  is an opaque UUID generated client-side, so the only thing the
  server can attribute to a person is a browser's view of
  localStorage.

This is both a privacy property (no PII) and a limitation (a real
deployment with multi-device sync would need real identity, with all
the data-handling obligations that come with it).

## Second-tier emotion classifier

To close gaps the regex tier inevitably has, the second tier runs
`SamLowe/roberta-base-go_emotions` (a pretrained 28-emotion
multi-label classifier from Hugging Face) on inbound messages the
regex didn't already classify. When any of a conservative
negative-affect label set (`sadness`, `grief`, `disappointment`,
`remorse`, `fear`, `nervousness`) crosses the threshold, the message
is elevated to `LOW` and logged with `source=ml-classifier`. The
per-label scores go into `matched_signals` for audit.

Why this model:

- **Govern.** Weights are pinned (specific HF repo + revision baked
  into the Docker image). A reviewer can inspect the model card, the
  dataset (GoEmotions, which is Reddit comments labeled by crowd
  workers), and the inference path. An opaque vendor LLM in this
  slot would route to a model that could change without notice.
- **Map.** The dataset's known biases — English-only, Reddit
  demographic skew, US-cultural framing, label noise — are nameable
  and citable instead of opaque.
- **Measure.** Frozen weights mean a regression test can pin "this
  phrase produces `sadness ≥ 0.5`" indefinitely.
- **Respect for persons.** The classifier runs locally; no extra
  user-data egress beyond the chat LLM call we already make.
- **Course theme: scientism.** Per-message label scores in the audit
  log let a reviewer interrogate "why did this fire?" That's the
  kind of artifact the course materials kept calling for, and it's
  more interpretable than another LLM in the same slot.

**Hard cap at LOW.** `MEDIUM` and `HIGH` stay reserved for the regex
tier's explicit ideation/plan/means signals. An emotion classifier
shouldn't fabricate clinical urgency from emotional tone — that's
the overreach the course's scientism critique warns about.

**Failure mode.** If the model fails to load (HF unreachable, weights
corrupted), the classifier fails open: a warning is logged, calls
return `NONE`, the regex tier carries on. A broken second tier
should not take the chat offline.

**Next step in a production deployment.** A classifier fine-tuned on
a clinical corpus (CLPsych or similar) audited by clinicians, plus
continuous threshold re-evaluation against fresh ground truth.

## Third-tier LLM-judge

When the regex tier and the ML classifier both return NONE, the
third tier consults a configurable LLM acting as a safety
classifier. It receives the message plus a strict system prompt that
asks for a structured `{risk, reason}` JSON classification. The
judge's one-sentence reason ends up in `matched_signals` so
reviewers can audit why it fired.

Why this tier exists at all: regex can miss a phrase semantically,
and go_emotions can classify the same phrase as something outside
the distress label set. Euphemistic suicidality is the canonical
example — `"I want to end everything"` reads as `desire ≈ 0.80` to
go_emotions, which we deliberately exclude from the distress set
because adding it would over-trigger on benign wants. An LLM with a
conservative system prompt can read the message holistically —
distinguishing "end this Zoom call" from "I'm just so done with
everything, I want it all to be over" — without us enumerating
regex patterns for every permutation.

**Hard cap at MEDIUM.** The system prompt explicitly tells the judge
to only return `NONE`, `LOW`, or `MEDIUM`. `HIGH` stays reserved for
the regex tier's plan/means/time signals; an LLM reading ambiguous
text shouldn't fabricate clinical urgency.

**Failure mode.** Fails open. Provider quota errors, network blips,
malformed JSON, empty content (some reasoning models burn the whole
token budget on hidden reasoning before emitting any visible output)
all return NONE with a logged warning, while the first two tiers
still run.

**Latency.** A judge call adds about 1–2 seconds before the chat
stream starts. Toggle off via `ENABLE_LLM_JUDGE=false` for
latency-sensitive demos. Skipped on short messages (default
`LLM_JUDGE_MIN_WORDS=6`) and whenever the prior tiers already
classified the message.

**Reflexive caveat.** This is "AI evaluating AI", which the course
materials flag specifically as a thing to scrutinize ("Drafting
Ethics with AI: Is it ethically wise or logically sound to use LLMs
to draft the very AI policies meant to govern them?"). I accept the
critique and partially mitigate it three ways: the judge can't
elevate to HIGH; every classification is logged with the judge's
reasoning so humans audit the judgments and not just the outcomes;
the judge model is configurable, so an operator can route judge
traffic to a different vendor than the chat LLM to avoid
same-vendor cross-contamination. None of those make the tension go
away.

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
