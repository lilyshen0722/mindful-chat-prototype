# Mindful Chat Prototype — Written Component

> **Required deliverable for DSCI 305 final project.** Per the rubric this
> document specifies (1) the intended audience, (2) the project's alignment
> with at least one ethical framework, and (3) its potential impact. Target
> length: under 1,000 words.

## 1. Intended audience

The primary audience for this prototype is **educators, students, and
applied-AI researchers** who are starting to wire safety guardrails around
chatbots and need a small, transparent reference they can read end-to-end and
fork. A secondary audience is **university policy and IT teams** evaluating
whether to deploy any kind of LLM-based chat tool inside campus services
(advising portals, student-life chatbots, library helpers); they can use this
artifact to interrogate questions like "what would minimum due diligence on
crisis-language handling look like?"

The prototype is **not** built for, and must never be deployed to, people in
distress. It is a teaching artifact about how to think about layered safety,
not a replacement for trained crisis counselors. This intent is encoded in
the UI (a persistent banner directing users to the 988 Lifeline) and in the
LLM system prompt itself, which forbids diagnosis, prescription, and clinical
advice.

## 2. Ethical framework alignment

The project is explicitly aligned with the **NIST AI Risk Management
Framework (AI RMF 1.0, 2023)** and informed by the Belmont Report's principle
of beneficence and the course's emphasis on **human-in-the-loop**.

NIST AI RMF organizes responsible AI work into four functions — Govern, Map,
Measure, Manage. Each is reflected in concrete code or documentation choices:

- **Govern.** The repository ships with an MIT license, a written intended
  audience, an explicit out-of-scope statement, and a rubric-aligned
  documentation set (`README.md`, `docs/architecture.md`,
  `docs/ethics-mapping.md`). Sensitive defaults (admin password, API key) are
  not hard-coded; they are surfaced through `.env.example` and a `.env` file
  that is `.gitignore`d, so secrets cannot be committed by accident.
- **Map.** `docs/architecture.md` describes the dataflow from user message
  through guardrail, LLM, and admin queue, naming the points where harm could
  enter (LLM hallucination, missed inbound signal, missed outbound signal,
  admin oversight failure). `docs/ethics-mapping.md` enumerates known failure
  modes of the rule-based detector.
- **Measure.** The detector's behavior is reproducible because it is rule
  based: the patterns live in `app/guardrail.py` and are tested in
  `tests/test_guardrail.py`. Every escalation is persisted to SQLite with
  the matched signals so future-me, an auditor, or a course TA can replay the
  triggers and check them against ground truth.
- **Manage.** Five mitigation layers are wired in: (a) outbound checks
  catch unsafe LLM replies and replace them with a safe template; (b) a
  *divergence* logger flags cases where the rule-based detector said NONE
  but the LLM raised crisis resources anyway, so reviewers can audit
  policy-vs-behavior drift; (c) a multi-turn pattern detector elevates
  tone when three consecutive distress signals appear; (d) every concern
  signal is surfaced on `/admin` with full transcript drill-down; (e) the
  reviewer can *take over* — pausing the LLM and chatting with the user
  as a human, with a visible "human reviewer engaged" badge.

The project also reflects two course-specific commitments. First, the
Belmont principle of **beneficence** ("do no harm; maximize benefit") is the
reason the AI is designed as *peer-like support* rather than a crisis
substitute: it engages warmly across the full risk spectrum so users feel
heard, while the intensity of resource mention scales with the guardrail
signal and any genuine handoff goes to a human, not a hard cutoff. Second,
the course's repeated insistence that LLM output be treated as a *draft*
— not as evidence — is encoded as a **human-in-the-loop with active
controls**: a reviewer can read the surrounding transcript, send messages
to the user as a human, and pause the bot entirely.

## 3. Potential impact

The realistic impact of this artifact is small and educational, and the
documentation is honest about that. Its value is threefold:

1. **A teaching scaffold.** Students working on similar projects can fork it
   and replace the rule-based detector with a trained classifier or an
   LLM-judge tier without touching the rest of the architecture, giving them
   a hands-on way to compare detection methods on the same harness.
2. **A discussion artifact.** The repository is a concrete object instructors
   can use to ground conversations about NIST AI RMF, false-positive vs.
   false-negative tradeoffs, and the limits of regex-based moderation — all
   without anyone having to deploy a real chatbot to vulnerable users.
3. **A starting point for safer university chat tools.** If campus teams
   eventually deploy LLM chat anywhere students might disclose distress (an
   academic-advising bot, a course Q&A assistant), this prototype offers a
   minimum-viable pattern — guardrail in front, guardrail behind, human
   review queue, mandatory crisis-line redirect — they can adapt instead of
   building from scratch and missing pieces.

The risks of misuse are addressed at three layers: the README's first line
declares the prototype is not a crisis service; the chat UI carries a
persistent banner with the 988 number; and the LLM system prompt forbids
clinical advice and reinforces the redirection. Anyone who deploys this
publicly in violation of those guardrails would be doing so against the
explicit written warnings in the code and documentation.

## 4. Limitations and honest caveats

This prototype's biggest known limitation is its **rule-based detector**.
Regex patterns will miss oblique, coded, multilingual, or sarcastic
expressions of distress, and they will fire on figurative language, song
lyrics, and third-person discussions ("my friend says she wants to die").
The pattern detector and divergence logger partially compensate, but the
underlying matcher is still English-only and rule-bound. A real deployment
would need a trained classifier, an LLM judge, and periodic re-evaluation
against fresh labels. The takeover feature is intentionally minimal: no
out-of-band reviewer notification, no SLA on response time, and no consent
flow that explicitly tells the user up front that a human may join. Each
limitation is documented in `docs/ethics-mapping.md` rather than hidden.
