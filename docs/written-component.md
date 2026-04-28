# Mindful Chat Prototype — Written Component

> Final project for DSCI 305 (Spring 2026). Covers audience,
> framework alignment, and impact (per rubric), plus the problem and
> known limitations. AI assistance disclosed in
> [`AI_USAGE.md`](../AI_USAGE.md).

## 1. The problem

LLM chatbots are showing up inside university tools — academic
advising, library help, course Q&A — without much thought about what
happens when a student discloses distress mid-conversation. From my
own poking at deployed campus chat tools, I've seen two failure modes.
Either the bot ignores the disclosure entirely, so no human ever
hears about it. Or it pivots abruptly to a 988 hotline mention
regardless of severity, which feels dismissive when someone is
venting about a hard week and trains people not to disclose anything
real next time.

Both failures come from treating the safety guardrail as one layer:
one regex, or one LLM call, or one prompt. I wanted to build
something concrete that shows what a layered, auditable,
human-in-the-loop guardrail looks like as code you can read top to
bottom. Small enough to follow, opinionated enough to argue
something. Not deployable.

## 2. Intended audience

The primary audience is educators, students, and applied-AI
researchers starting to wire safety guardrails around chatbots and
looking for a small reference they can fork. A secondary audience is
university policy and IT teams thinking about deploying LLM chat
anywhere students might disclose distress: an advising bot, a
course-staff Q&A assistant, anything similar. They can use this as a
starting point for "what would minimum due diligence look like?"
before they ship.

The prototype is not for, and must never be deployed to, people in
distress. The chat UI carries a 988 banner, the README opens with the
warning, and the LLM system prompt forbids diagnosis, prescription,
and clinical advice.

## 3. How it aligns with NIST AI RMF (and Belmont)

I picked the NIST AI Risk Management Framework (2023) over the EU AI
Act because NIST's four-function structure (Govern, Map, Measure,
Manage) mapped more cleanly onto a layered guardrail than the EU
Act's risk-tier categorization. Belmont supports it: "do no harm"
underwrites the peer-support framing, and "respect for persons"
underwrites the no-PII / opaque-conversation-id design.

**Govern.** MIT-licensed repo with stated intended use, an explicit
out-of-scope section, and a documentation set under `docs/`. Secrets
go through `.env.example`; the real `.env` is gitignored. Third-party
dependencies are named and configurable so a deployer can swap them.

**Map.** `docs/architecture.md` walks through the dataflow.
`docs/threat-model.md` lists eleven concrete threats (T1–T11) with
mitigations and residual risk. Writing the threats down explicitly
was the part of the project that surprised me most: once a threat has
a name, you notice when it's not addressed.

**Measure.** The detector pipeline has three tiers (regex, Hugging
Face emotion classifier, LLM-judge), and each writes to the
escalation queue with a distinct `source` value. A reviewer auditing
the queue can tell which layer fired, so each tier's contribution is
measurable from operations alone. Tests pin regex behavior; pinned
ML weights keep the second tier reproducible.

**Manage.** Seven layers: regex, ML classifier capped at LOW,
LLM-judge capped at MEDIUM, an outbound check that replaces unsafe
LLM replies with a safe template, a multi-turn pattern aggregator, a
divergence logger that flags when the LLM volunteers crisis
resources unprompted, and reviewer takeover with a "human reviewer
engaged" badge that makes the handoff visible to the user.

The peer-support framing is the Belmont piece: the AI engages warmly
across the risk spectrum so users feel heard, while the intensity of
resource mention scales with the signal. A genuine handoff goes to a
human via the takeover flow, not a hard cutoff. The course's framing
of LLM output as a "draft" that humans verify became literal here —
every bot reply is auditable in `/admin`, and a reviewer can pause
the bot or send a message in their own voice.

## 4. Potential impact

The realistic impact is small and educational, and I'm not claiming
otherwise. What it does offer:

- A teaching scaffold. Anyone on a similar project can fork this and
  replace any tier without touching the rest. The distinct `source`
  values let a researcher A/B detection methods on the same harness.
- A discussion artifact. The demo in `docs/user-guide.md` grounds
  conversations about NIST RMF, the trade-off between recall and
  reviewer fatigue, and the limits of single-layer moderation.
- A starting point for safer university chat tools. A team shipping
  LLM chat where students might disclose distress can adapt the
  pattern (guardrail in front, classifier in front, guardrail
  behind, human review, takeover, crisis-line redirect) instead of
  reinventing it and forgetting layers.

Misuse is mitigated at three levels: the README's first sentence
declares the prototype is not a crisis service; the chat UI carries a
persistent 988 banner; and the LLM system prompt forbids clinical
advice. The threat model names "treating the prototype as
production-ready" as the meta-threat the documentation is designed to
defuse.

## 5. What I know is broken

The detector stack is English-only and not clinically validated. I
patched the regex twice during development when real conversations
exposed gaps (`"feeling really down today"` slipped past the LOW
patterns; `"end all of this"` slipped past the MEDIUM patterns). The
ML tier inherits Reddit/GoEmotions demographic skew. The LLM-judge
tier is "AI evaluating AI" — exactly the tension the course materials
flagged. I cap it at MEDIUM and log the reasoning so humans audit
decisions, not just outcomes, but I haven't fully resolved the
critique and I don't claim to.

A production deployment would need a clinical-corpus classifier,
real reviewer auth and audit logs, an upfront consent banner, and
out-of-band reviewer notifications. None of those are here.

What I learned: every layer I added uncovered a gap in the previous
one. The discipline isn't picking the perfect detector — it's making
the gaps visible to the humans who have to act on them.
