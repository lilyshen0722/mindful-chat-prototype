# AI usage disclosure

> ⚠️ Draft — please edit in your own voice before submission.

I built this project for DSCI 305 with significant help from Claude
(Anthropic's AI assistant), used through the Claude Code CLI. This
document is meant to be honest about what AI did, what I did, and how
the collaboration worked. The course rubric requires disclosure, and
pretending otherwise would defeat the point of an ethics class.

## What AI did

Most of the code was AI-implemented from my design discussions. The
agent typed faster than I could, and I directed it. In particular:

- The FastAPI scaffolding, the SQLite schema, the front-end HTML and
  CSS, the Docker setup. I read every file and adjusted things I
  disagreed with, but the boilerplate is AI-generated.
- The regex patterns in `app/guardrail.py`. I gave examples of distress
  phrases I wanted caught; the agent wrote regex that covers them. I
  added or rejected patterns when smoke testing turned up gaps or
  false positives.
- The Hugging Face emotion classifier integration and the LLM-judge
  tier (`app/ml_classifier.py`, `app/llm_judge.py`). I picked the
  model after reading the model card and the cap design (LLM-judge
  stops at MEDIUM, ML at LOW); the agent wired up the inference path.
- Tests in `tests/test_guardrail.py`. I gave examples of what to
  assert; the agent wrote them. I reviewed every assertion.
- Initial drafts of every doc under `docs/`. I outlined what each one
  should cover, the agent drafted, and I edited.

## What I decided

The design choices are mine, even when the agent's suggestions shaped
them:

- Picking the NIST AI Risk Management Framework over the EU AI Act.
  I read both and decided NIST's four-function structure (Govern, Map,
  Measure, Manage) mapped more cleanly onto a layered guardrail.
- The peer-like-support framing — don't push 988 on every distress
  signal, only when it's clinically warranted. This came from
  frustration with chatbots that over-escalate, and from class
  discussions about dismissive moderation.
- The hybrid takeover model: reviewer messages render as
  bot-shaped bubbles with a small italic attribution, instead of full
  impersonation (covert) or a loud distinct color (jarring). I
  rejected each extreme for ethical reasons during the design
  conversation.
- Using a regex first tier instead of going pure-ML. Regex is
  auditable; an opaque classifier as the only line of defense felt
  wrong for a project literally about transparency.
- Adding the LLM-judge tier even though it adds latency. The
  euphemism gap I hit in real testing convinced me the trade-off was
  worth it.

## What I caught by actually using it

A lot of iteration was driven by me poking at the chat:

- I sent "I hate school" and noticed the bot pushed 988. That triggered
  the original peer-support redesign.
- I walked through the homework-failure scenario in chat and noticed
  nothing flagged for admin even though the bot was reading the
  conversation as a crisis. That exposed both the regex gap
  (`"end all of this"` wasn't in the patterns) and the ML gap
  (`go_emotions` reads euphemistic ideation as `desire`, which we
  exclude from the distress label set). The fixes were mine to
  direct.
- I noticed user messages were rendering twice in the chat UI and
  traced it to the polling loop racing the optimistic bubble. The
  agent implemented the fix after I described the symptom.
- The conversation-state race during takeover, the leading whitespace
  on streamed replies — both surfaced from my real use, not from
  AI-driven testing.

## What I reviewed and edited

- Every commit before pushing.
- Every doc in this repo. The structure is mostly the agent's, but I
  rewrote sections in my own voice for the deliverable
  (`docs/written-component.md`) and trimmed AI-tell phrasing
  elsewhere.
- The chat LLM's system prompt (`app/llm.py`). I read every line and
  adjusted the per-tier guidance after testing how the bot actually
  behaved.
- The threat model. The threats came from real concerns I raised in
  conversation; the agent's contribution was structuring them.

## What I'm not claiming

- I didn't train any model. The Hugging Face classifier is pretrained;
  I picked it and tuned the threshold.
- I'm not claiming clinical validity. The detector stack gets patched
  iteratively as I find gaps. I don't pretend it's safe to deploy.
- I'm not the author of every line of code or prose. I'm the author
  of every decision about what got built and what shipped, and of the
  written component and this disclosure.

The course rubric says "AI should assist, but you must write the
content." For the written component and this disclosure, I wrote
directly. For most other artifacts, I directed AI implementation and
reviewed the output the way I'd review a junior collaborator's pull
request — accepting most of it, pushing back where I disagreed,
testing what I was unsure about.
