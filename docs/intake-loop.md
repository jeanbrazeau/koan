# Intake Phase Design

How the intake phase gathers context in three steps, and the prompt
engineering principles that govern it.

> Parent doc: [architecture.md](./architecture.md)
> Related: [subagents.md -- Step-First Workflow](./subagents.md#step-first-workflow)

---

## Overview

The intake phase is the most consequential subagent in the pipeline. Its
single output -- `landscape.md` -- is the sole input for all downstream phases.
Every story boundary, every implementation plan, and every line of code
produced downstream depends on the completeness and accuracy of that file.
Gaps in `landscape.md` compound: a missed decision becomes a wrong story
boundary becomes a wrong plan becomes wrong code.

The intake phase runs a focused **three-step workflow**: gather context
(conversation + codebase orientation + scouts), evaluate findings and ask the
user questions, then write `landscape.md`.

### Step structure

| Step | Name     | Runs | Purpose                                                                           |
| ---- | -------- | ---- | --------------------------------------------------------------------------------- |
| 1    | Gather   | 1x   | Read conversation, open obvious files (≤5), dispatch 3-5 scouts.                  |
| 2    | Deepen   | 1x   | Process scout results, verify by reading files, deepen understanding through iterative dialogue. |
| 3    | Write    | 1x   | Write `landscape.md`. Review gate: calls `koan_review_artifact` before completing.  |

Step 3 is review-gated: it blocks until `koan_review_artifact` is accepted.
All other steps advance linearly.

---

## Step Design

### Step 1: Gather

The Gather step combines what was previously three separate activities
(reading the conversation, orienting in the codebase, and dispatching scouts)
into a single `koan_complete_step` cycle. This avoids the latency and context
re-derivation overhead of artificially separating them.

The step has a **5-file budget** for initial exploration: project root listing,
orientation files (README.md, AGENTS.md, CLAUDE.md), and files the conversation
explicitly referenced. This is enough to write scout prompts that reference
actual function names and file paths rather than conversation labels.

No read-only permission gate -- the Gather step has full access to all intake
tools including `koan_request_scouts`.

### Step 2: Deepen

The Deepen step builds genuine understanding through iterative dialogue with
the user. It processes scout results, verifies findings by reading source files
directly, identifies gaps, and asks the user targeted questions -- then deepens
further as each answer reveals new dimensions.

Key properties:
- **Scout verification**: Scouts are good at exploration but their output should
  be confirmed. The Deepen step reads actual files to verify key scout findings
  that affect scope or story boundaries.
- **Iterative deepening**: Understanding deepens through multiple rounds of
  dialogue. Each answer may shift the picture of adjacent areas, revealing
  assumptions the agent was making without realizing it. Multiple rounds of
  questions are expected for any non-trivial task.
- **Impact classification**: Each unknown is classified as ASK (user input
  needed) or SAFE (implementation detail). Only ASK items become questions.
- **Default-ask framing**: Question-asking is the default; skipping requires
  triple justification. This inverts the typical LLM bias toward advancing.

### Step 3: Write

The Write step produces `landscape.md` with required sections (Task Summary,
Prior Art, Codebase Findings, Project Conventions, Decisions, Constraints,
Open Items). Review-gated: the step calls `koan_review_artifact` and loops
on step 3 until the user accepts.

---

## Review Gate

The step engine calls `validate_step_completion(step, ctx)` before
`get_next_step()`. For step 3, it verifies that `koan_review_artifact` was
called and accepted:

```python
def validate_step_completion(step, ctx):
    if step == 3:
        if ctx.last_review_accepted is None:
            return "You must call koan_review_artifact..."
        if ctx.last_review_accepted is False:
            return "The user requested revisions..."
    return None
```

```python
def get_next_step(step, ctx):
    if step < 3:
        return step + 1
    if ctx.last_review_accepted is True:
        return None  # done
    return 3  # loop on review
```

---

## Prompt Engineering Principles

The intake prompts apply several techniques from the prompting literature.
This section records the reasoning so future changes don't inadvertently remove
mechanisms that address specific failure modes.

### MARP (Maximizing Operations per Step)

The three-step structure applies the MARP principle: maximize operations
per `koan_complete_step` call while minimizing planning or meta-reasoning
steps. Each step does real work across multiple activities rather than
artificially separating them into sequential tool calls.

### Iterative deepening through dialogue

The Deepen step positions dialogue as the core mechanism, not an afterthought.
The agent maps knowns and unknowns, then enters an iterative loop: ask
questions, process answers, verify against code, surface new gaps, and ask
again. Each answer is treated as a thread to pull -- it may shift understanding
of adjacent areas and reveal assumptions the agent was making without realizing
it. This ripple effect is what produces genuine understanding rather than
surface-level coverage.

### Default-ask question framing (preventing question avoidance)

The Deepen step frames question-asking as the default, with skipping
requiring triple justification. This inverts the typical LLM bias toward
advancing the workflow.

### Stakes framing (EmotionPrompt for accountability)

The system prompt includes: "A question you don't ask is an answer you're
making up." This connects intake shortcuts directly to downstream failures.

### Contrastive examples for thinking density

The system prompt includes WRONG → RIGHT examples for processing scout reports,
resolving conflicts, and classifying unknowns. These demonstrate the target
density for internal reasoning without affecting tool arguments or written
artifacts.

---

## Pitfalls

### Don't re-add a step-1 read-only gate for intake

Intake's Gather step needs all tools (especially `koan_request_scouts`) from
the start. The brief-generation phase still has a step-1 read-only gate, but intake
does not.

### Don't add a confidence loop

Previous iterations had a confidence-gated loop (steps 2-4 repeating).
This was removed because: (a) it produced unnecessary second scout batches,
(b) the self-verification step (Reflect) risked intrinsic self-correction
without external grounding, and (c) one focused pass is sufficient when the
Evaluate step is thorough.

### Don't separate scout verification from question-asking

Scout result evaluation and question formulation are tightly coupled -- a scout
finding directly informs what questions to ask. Separating them forces the LLM
to defer questions it could ask immediately.

### Don't cap question rounds

Previous iterations suggested "aim for 3-5 questions" in a single batch. This
created an implicit ceiling that discouraged iterative deepening. The current
design has no per-round limit and explicitly expects multiple rounds for
non-trivial tasks. Completion is defined by depth of understanding, not
question count.
