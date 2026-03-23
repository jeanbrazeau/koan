# Epic Brief

The epic brief is a compact product-level artifact produced between intake and
decomposition. It captures the **what and why** of an epic and serves as a
correctness anchor for all downstream phases.

> Related: [artifact-review.md](./artifact-review.md) — the IPC mechanism used
> to present brief.md for human review before pipeline advancement.

---

## What It Captures

| Section | Content |
|---------|---------|
| **Summary** | 3–8 sentences: what this epic is about |
| **Context & Problem** | Who is affected, where in the product, what the current pain is |
| **Goals** | Numbered list of measurable objectives |
| **Constraints** | Hard constraints from landscape.md (technical, timeline, compatibility) |

**Size constraint:** Under 50 lines. The brief is consulted by the decomposer,
planner, and orchestrator on every pipeline run — compact size ensures it
remains a quick reference rather than a specification to read in full.

The 50-line limit is a forcing function: a brief that requires 200 lines is
not a brief — it is a spec. If the brief writer cannot distill intake context
into 50 lines, the intake phase likely gathered more context than necessary,
or the epic scope is too large to address in one pipeline run.

## What It Excludes

- UI flows and wireframes
- Technical architecture decisions
- Implementation details
- Story decomposition

These belong in later artifacts (story sketches, `plan/context.md`). The brief
is deliberately non-technical so it remains stable as the pipeline progresses.

---

## Pipeline Position

```
intake → brief → decomposition → review → executing → completed
```

The brief sits between intake and decomposition:

- **After intake:** `landscape.md` is complete — the LLM has investigated the
  codebase, asked all clarifying questions, and produced a synthesis of
  findings and decisions. The brief distills this into a problem statement.
- **Before decomposition:** The decomposer reads `brief.md` to scope stories
  against stated goals and constraints. Without the brief, the decomposer
  would invent scope not present in the user's intent.

---

## Brief-Writer Subagent

Role: `"brief-writer"`. Model tier: `"strong"` (same tier as intake and
decomposer — synthesis from intake context requires genuine reasoning, not
mechanical transformation).

### Step Progression

```
Boot → koan_complete_step (step 0 → 1)

Step 1 (Read):
  Read landscape.md. Build mental model of task summary, prior art, codebase findings, project conventions,
  decisions, and constraints. No file writes allowed.

Step 2 (Draft & Review):
  Write brief.md. Call koan_review_artifact.
  If feedback → revise brief.md, call koan_review_artifact again.
  If "Accept" → call koan_complete_step.
  [Loops within step 2 until user accepts]

Step 3 (Finalize):
  Phase complete.
```

**Review gate:** `validateStepCompletion(step=2)` requires at least one
`koan_review_artifact` call before `koan_complete_step` is allowed. The LLM
cannot skip the review by calling `koan_complete_step` directly after writing
the file.

**Step 2 loop is implicit:** The LLM remains in step 2 by continuing to call
`koan_review_artifact` rather than advancing. There is no backward step
transition and no `getNextStep()` override.

See [artifact-review.md](./artifact-review.md) for the IPC protocol that
powers the review gate.

### Permissions

```typescript
["brief-writer", new Set([
  "koan_complete_step",
  "koan_review_artifact",
  "edit",
  "write",
  // No koan_ask_question — uses artifact review, not structured questions.
  // No koan_request_scouts — all codebase context arrives via landscape.md.
])]
```

Write/edit access is path-scoped to the epic directory (`PLANNING_ROLES`).

---

## Downstream References

All planning phases are prompted to read `brief.md` before acting:

| Phase | Why |
|-------|-----|
| **Decomposer** | Scopes stories against brief goals; must not invent scope absent from brief |
| **Planner** | Plans must serve product-level goals and respect constraints |
| **Orchestrator** | Validates story completion against product goals |

The executor reads `plan/context.md` (story-level context) and does not
consult the epic brief directly — it works from the plan, which already
incorporates brief context via the planner.

Downstream agents receive a nudge in step 1 guidance: they are told to read
`brief.md` themselves. This keeps prompts stable across brief evolution and
ensures agents see current file content rather than a spawn-time snapshot.

---

## Design Rationale

### Artifact cascade

Each phase produces an artifact that downstream phases consult. The cascade
in this pipeline:

```
landscape.md        (intake synthesis)
  → brief.md          (problem + goals + constraints)
    → story.md × N  (decomposition)
      → plan/context.md × N  (story plans)
```

Each artifact is progressively more specific. The brief is the
most-referenced — every phase from decomposition through execution can check
it to stay aligned with the original problem.

### Why a separate brief phase

A merged "brief + decompose" agent would violate the single-cognitive-goal
principle: writing a product brief and decomposing it into story sketches are
distinct reasoning tasks. Separating them:

- Forces the brief to be reviewed and accepted before decomposition begins
- Prevents the decomposer from anchoring on its own interpretation of scope
- Creates a reviewable artifact that can be corrected before downstream work starts
- Enables the decomposer's scope to be validated against an explicit human-approved brief
