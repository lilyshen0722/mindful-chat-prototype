# Mindful Chat Prototype — Written Component

> **Required deliverable for DSCI 305 final project.** Per the rubric this
> document specifies (1) the intended audience, (2) the project's alignment
> with at least one ethical framework, and (3) its potential impact, plus a
> short *Problem & motivation* up front and an honest *Limitations* section.
> Target length: under 1,000 words.

## 1. Problem & motivation

LLM-powered chat is being deployed inside university tools — academic
advising, library help, course assistants — with little discipline around
what happens when a student discloses distress mid-conversation. The two
common failure modes are symmetric and harmful: the bot ignores the
disclosure (silent failure, no human notified) or the bot pivots
abruptly to a crisis hotline mention regardless of severity (dismissive
of normal venting, trains users not to disclose). Both arise because
the *guardrail* is treated as a single regex or a single LLM call.

This prototype answers the question: *what does layered, auditable,
human-in-the-loop crisis-language handling look like as a working
artifact you can read end-to-end?* It is small by design — a single
FastAPI service, three SQLite tables, two HTML pages — so a reader can
follow the entire safety pipeline without losing it inside framework
code. It is not a deployable service.

## 2. Intended audience

The primary audience is **educators, students, and applied-AI
researchers** wiring safety guardrails around chatbots and looking for a
small, transparent reference they can fork. A secondary audience is
**university policy and IT teams** evaluating LLM chat deployments
inside campus services; they can use this artifact to interrogate "what
would minimum due diligence on crisis-language handling look like?"

The prototype is **not** built for, and must never be deployed to,
people in distress. The chat UI carries a persistent banner directing
users to the 988 Lifeline, and the LLM system prompt forbids diagnosis,
prescription, and clinical advice.

## 3. Ethical framework alignment

The project is explicitly aligned with **NIST AI Risk Management
Framework (AI RMF 1.0, 2023)** — Govern, Map, Measure, Manage — and
informed by the Belmont Report's principle of beneficence and the
course's emphasis on **human-in-the-loop**.

- **Govern.** MIT-licensed repo with stated intended use, an
  out-of-scope statement, and a documentation set
  (`README.md`, `docs/architecture.md`, `docs/ethics-mapping.md`,
  `docs/threat-model.md`, `docs/user-guide.md`). Secrets via
  `.env.example`; the real `.env` is gitignored. Third-party
  dependencies (OpenRouter LLM provider, HuggingFace classifier
  weights) are named and configurable.
- **Map.** `docs/architecture.md` traces the full dataflow.
  `docs/threat-model.md` enumerates eleven concrete threats (T1–T11),
  the mitigation for each, and the residual risk that remains.
- **Measure.** Five distinct `source` values on each escalation row
  (`input`, `ml-classifier`, `pattern`, `output`, `divergence`) make
  *each tier's* contribution separately measurable. Pinned ML model
  weights mean classifier behavior is reproducible; 15 unit tests in
  `tests/test_guardrail.py` pin both per-level detector behavior and
  regressions for previously-missed phrasings.
- **Manage.** Six mitigation layers are wired in:
  (a) a second-tier emotion classifier (pinned
  `SamLowe/roberta-base-go_emotions`, runs locally in the container)
  catches oblique distress the regex misses; (b) outbound checks
  replace unsafe LLM replies with a safe template; (c) a *divergence*
  logger flags model drift when the LLM volunteers crisis resources on
  a NONE-risk turn; (d) a multi-turn pattern detector elevates tone
  when three consecutive distress signals appear; (e) every concern is
  surfaced on `/admin` plus a per-conversation chat-style review page;
  (f) the reviewer can *take over* — pausing the LLM and chatting with
  the user as a human, with a visible "human reviewer engaged" badge.

Two course-specific commitments. First, **beneficence** is the reason
the AI is *peer-like support* rather than a crisis substitute: it
engages warmly across the risk spectrum so users feel heard, while the
intensity of resource mention scales with the guardrail signal and any
genuine handoff goes to a human. Second, the course's repeated
insistence that LLM output be treated as a *draft* — not as evidence —
is encoded as a **human-in-the-loop with active controls**: a reviewer
can open any conversation in chat-style, send messages as the reviewer,
and pause the bot entirely.

## 4. Potential impact

Realistic impact is small and educational, and the documentation says so.

1. **A teaching scaffold.** Students working on similar projects can
   fork it and replace any tier — regex, ML classifier, LLM-judge —
   without touching the rest of the architecture. The five distinct
   `source` values let a researcher A/B compare detection methods on
   the same harness.
2. **A discussion artifact.** The repo is a concrete object instructors
   can use to ground conversations about NIST AI RMF, the
   tier-by-tier tradeoff between recall and reviewer fatigue, the
   transparency cost of using a third-party HuggingFace classifier
   versus another opaque LLM, and the limits of any rule-based
   moderation — all without deploying anything to vulnerable users.
3. **A starting point for safer university chat tools.** A campus team
   that eventually deploys an LLM chat where students might disclose
   distress (advising bot, course Q&A) can adapt this minimum-viable
   pattern — guardrail in front, classifier in front, guardrail behind,
   human review queue, takeover affordance, mandatory crisis-line
   redirect — instead of building from scratch and missing pieces.

Risks of misuse are addressed at three layers: README's first line
declares the prototype is not a crisis service; the chat UI carries a
persistent 988 banner; and the LLM system prompt forbids clinical
advice. The threat-model names "treating the prototype as
production-ready" as the meta-threat (T11).

## 5. Limitations and honest caveats

The biggest honest limitation is that the detector stack is still
**English-only and non-clinical**. The regex tier patches iteratively
as audit surfaces misses; the ML tier inherits the GoEmotions Reddit
distribution and its demographic skew; neither claims clinical
validity. Capping the ML tier at LOW (never MEDIUM/HIGH) is
deliberate — emotion classification cannot responsibly fabricate
clinical urgency. A production deployment would add a classifier
fine-tuned on a clinical corpus, an LLM-judge tier for borderline
cases, real reviewer auth + audit logs, and an upfront consent banner
warning users that messages may be reviewed by a human. Each is
documented in `docs/ethics-mapping.md` and `docs/threat-model.md`
rather than hidden.
