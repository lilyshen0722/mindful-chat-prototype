# AI usage disclosure

This document follows the DSCI 305 syllabus's AI Policy:

> **Disclosure Requirements.** When using AI tools (ChatGPT, Claude,
> Gemini, etc.), you must disclose: (a) which tool(s) you used, (b)
> how you used them (drafting, editing, coding, analysis, etc.), (c)
> what prompts you used (include key prompts in appendix or
> footnotes). AI-generated content should be clearly marked and
> attributed. You remain responsible for accuracy, quality, and
> ethical compliance of all submitted work.

## (a) Tools used

- **Claude (Anthropic)** via the **Claude Code** CLI agent (model:
  Claude Opus 4.7 with 1M-token context). All AI assistance on this
  project came from this one tool. No ChatGPT, Gemini, Copilot, or
  other.
- The Claude Code agent has filesystem and shell access to the local
  repo, which means it can read code, run tests, run Docker, run
  Playwright smoke tests, and issue git commands. I supervised every
  state-changing action; no autonomous merges or pushes happened
  without my OK.
- Underlying language models the *project itself* uses (separate from
  the AI assistance):
  - **OpenRouter** as the LLM provider for the chat reply and the
    third-tier LLM-judge. Default model is
    `nvidia/nemotron-nano-9b-v2:free`.
  - **`SamLowe/roberta-base-go_emotions`** (pretrained Hugging Face
    classifier) as the second tier of the guardrail.
  These are documented in `README.md` and `docs/architecture.md`.

## (b) How I used them

| Activity | AI's role | My role |
|---|---|---|
| **Code generation** | Wrote the FastAPI scaffolding, SQLite schema, regex patterns, classifier integration, LLM-judge integration, HTML/CSS, Docker setup, tests. | Designed the architecture and tier structure; reviewed every file; edited where I disagreed; ran the smoke tests; chose the cap design (ML at LOW, judge at MEDIUM). |
| **Debugging** | Diagnosed and fixed bugs I surfaced from real use (duplicate user bubble, leading whitespace in stream, mid-stream-disconnect signal loss, judge max-tokens issue with reasoning models). | Found the bugs by actually using the chat. Described the symptoms; verified the fixes. |
| **Drafting documentation** | Wrote initial drafts of `docs/architecture.md`, `docs/ethics-mapping.md`, `docs/threat-model.md`, `docs/user-guide.md`, and the structure of this disclosure. | Outlined what each doc should cover; reviewed and edited; rewrote prose-heavy sections in my own voice; rewrote `docs/written-component.md` (the required deliverable) directly. |
| **Editing assistance** | Tightened sentences, hit word-count budgets, removed AI-tell phrasing on request. | Decided what to keep and what to cut. |
| **Code annotation** | Added comments where I asked. | Read and trimmed where the comments were obvious. |
| **Analysis** | Helped me reason through which framework (NIST vs. EU AI Act) and which second-tier (HF model vs. LLM-judge) fit best for the rubric, by listing tradeoffs. | Made the calls. The tradeoff tables are AI-summarized but my conclusions. |
| **Smoke testing** | Wrote Playwright + httpx smoke scripts that drive the running container in a real browser and surface failing assertions. Scripts are not committed because they need a live OpenRouter key and the loaded HF classifier. | Specified what to test for each feature; reviewed the failures. |
| **Git operations** | Drafted commit messages; performed force-push for history rewrite (after my explicit go-ahead). | Approved every commit and every push. |

## (c) Key prompts

Representative prompts from the project's working sessions, in
roughly chronological order. These are paraphrased rather than
verbatim — Claude Code retains conversation history but I'm
listing the load-bearing instructions:

1. *"I want to implement a guardrail system for suicide prevention
   when a user is chatting with an AI bot... using NIST AI RMF as
   the framework, with notification to admin and crisis-line
   redirection. Use Docker Compose for local deployment."* — initial
   project framing; produced the FastAPI scaffold + regex tier +
   admin queue.
2. *"Stop pushing 988 on every distress signal. Re-frame as
   peer-like support that scales resource intensity with the
   guardrail signal."* — design pivot away from
   escalate-and-stop. Drove the system-prompt redesign.
3. *"Add a divergence detector — if the regex says NONE but the bot
   mentioned 988, log it for the admin to audit model drift."* —
   produced the `divergence` source value.
4. *"Add multi-turn risk aggregation — three consecutive non-NONE
   user messages should elevate to MEDIUM."* — produced
   `assess_pattern`.
5. *"Add a takeover feature: pause the bot, let the reviewer chat as
   a human, but keep the handoff visible to the user."* — produced
   `conversation_state` + the hybrid attribution model.
6. *"The chat shows the user's message twice and the bot reply
   starts with a blank line."* — surfaced two real bugs; drove the
   `user_saved`/`assistant_saved` SSE events and the leading-whitespace
   trim.
7. *"For the second tier, would HF or LLM-judge align better with
   the rubric?"* — produced the comparative analysis that led me
   to wire HF first, then LLM-judge as the third tier when I saw
   euphemistic ideation slipping past both.
8. *"Rewrite the docs in a more direct human-sounding voice; add an
   AI usage disclosure."* — drove the prose pass that produced this
   document.
9. *"Convert the ASCII architecture diagrams to Mermaid for GitHub
   rendering."* — produced the Mermaid blocks now in `README.md`
   and `docs/architecture.md`.

The full conversation history lives in Claude Code's session log; I
can produce the verbatim prompt list on request.

## What I decided vs. what AI implemented

The design choices are mine, even when the agent's suggestions
shaped them:

- Picking NIST AI RMF over the EU AI Act — read both, NIST mapped
  cleaner.
- Peer-like support framing — from frustration with chatbots that
  over-escalate, plus class discussion.
- The hybrid takeover model — rejected fully covert and loud
  distinct-color extremes during the design conversation.
- Regex first tier — auditable; an opaque ML/LLM as the only line
  of defense felt wrong for an ethics-class project.
- Adding the LLM-judge tier despite latency — the euphemism gap I
  hit in real testing convinced me.
- Caps on each tier (ML at LOW, judge at MEDIUM) — rejecting the
  scientism failure mode the course materials flag.

## Real-use bug catches

A lot of the iteration came from me poking at the chat:

- `"I hate school"` → bot pushed 988 → triggered the original
  peer-support redesign.
- The homework-failure roleplay → exposed both the regex gap
  (`"end all of this"` not in patterns) and the ML gap
  (`go_emotions` reads euphemism as `desire`). The fixes were mine
  to direct.
- Duplicate user bubbles + leading whitespace in streamed replies →
  found by use, not by tests.
- The mid-stream-disconnect signal loss → noticed because the
  Playwright smoke test wasn't logging escalations the agent
  expected.

## What I'm not claiming

- I didn't train any model. The HF classifier is pretrained.
- I'm not claiming clinical validity. The detector stack is patched
  iteratively; I don't pretend it's safe to deploy.
- I'm not the author of every line of code or prose. I'm the author
  of every decision about what got built and shipped, of the
  written component (`docs/written-component.md`), and of this
  disclosure.

The course rubric says "AI should assist, but you must write the
content." For the written component and this disclosure, I wrote
directly. For most other artifacts, I directed AI implementation
and reviewed the output the way I'd review a junior collaborator's
pull request — accepting most of it, pushing back where I
disagreed, testing what I was unsure about.
