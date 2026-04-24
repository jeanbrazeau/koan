# Phase Trust Model

Design decision document for how phases relate to each other's outputs across
both the plan and milestones workflows.

## Principle

Phases trust each other's outputs. Verification happens _within_ a phase,
not across phases. The user reviews artifacts at phase boundaries.

Three designated review phases serve as adversarial verifiers:

- **plan-review** -- verifies implementation plans
- **exec-review** -- verifies execution results
- **milestone-review** -- verifies milestone decomposition (milestones workflow)

Each adversarial phase uses the codebase as an external verification tool (the
CRITIC pattern). All other phases trust the chain.

## Why

Re-verification across phases is the "intrinsic self-correction" anti-pattern:
the same LLM re-checking its own prior work without external feedback. Research
shows this typically degrades performance -- the model is more likely to change
correct conclusions to incorrect ones than the reverse.

The fix is structural: designate verification phases with adversarial postures,
and have them use the codebase as an external verification tool. All other
phases trust the chain.

## Phase responsibilities

### intake (3 steps: Gather, Deepen, Summarize)

- Explores the codebase, asks the user targeted questions, resolves ambiguity.
- Owns: uncertainty resolution. Its output is verified understanding.
- Downstream phases trust intake's findings as their starting point.

### milestone-spec (2 steps: Analyze, Write) -- milestones workflow only

- Decomposes the initiative into milestones (CREATE mode) or updates milestone
  status after execution (UPDATE mode).
- Trusts intake's findings. Reads the codebase's module/package structure to
  ground the decomposition in actual code boundaries.
- Owns: `milestones.md` -- the milestone decomposition artifact.
- Does NOT plan implementation details. Produces rough sketches only.

### milestone-review (2 steps: Read, Evaluate) -- milestones workflow only

- The designated adversarial verifier for milestone decomposition. Trusts
  nobody -- not intake, not milestone-spec.
- For every milestone, maps its stated scope to actual files/modules in the
  codebase. Verifies those files exist. Verifies the ownership boundaries the
  decomposition implies are real.
- Owns: verification of decomposition soundness (scope, ordering,
  completeness, independence, feasibility).
- Advisory only -- reports findings, does not modify milestones.md.
- **Compound-risk framing**: a missed issue here is inherited by every
  subsequent plan-spec session. An ordering error or scope overlap at this
  layer contaminates every downstream plan and execution.

### plan-spec (2 steps: Analyze, Write)

- Reads codebase files to write precise implementation instructions.
- Trusts intake's findings. Reads code to understand structure for planning,
  not to re-verify what intake discovered.
- In milestones workflow: scoped to the current `[in-progress]` milestone.
  Produces `plan-milestone-N.md`.
- In plan workflow: produces `plan.md`.

### plan-review (2 steps: Read, Evaluate)

- The designated adversarial verifier. Trusts nobody.
- Opens every file the plan references and checks every claim (paths, function
  names, signatures, types) against reality.
- Owns: verification. Uses the codebase as an external tool to validate claims.
- Advisory only -- reports findings, does not modify the plan artifact.

### exec-review (2 steps: Verify, Assess)

- The designated verifier for execution results. Trusts nobody -- not the plan,
  not the executor's self-report.
- Reads the executor's deviation report from context.
- Runs verification commands (build, tests, type checks) to confirm executor
  claims.
- Owns: structured outcome classification (Clean / Minor deviations /
  Significant deviations / Incomplete).

### execute (2 steps: Compose, Request)

- Composes the executor handoff from the plan artifact and plan-review findings.
- Trusts the plan (it has been reviewed). Does not re-evaluate.
- Owns: clean handoff to the executor agent.

## Data flow: plan workflow

```
task_description
    |
    v
 intake  ---- questions/answers ----> user
    |
    | (trusted context in LLM memory)
    v
 plan-spec ----> plan.md
    |
    | (artifact in run_dir)
    v
 plan-review ----> severity-classified findings (in chat)
    |               \
    |                +---> loop back to plan-spec if critical/major
    v
 execute ----> koan_request_executor(artifacts, instructions)
    |
    v
 exec-review ----> outcome classification (in chat)
    |               \
    |                +---> loop back to plan-spec if significant deviations
    v
 curation
```

## Data flow: milestones workflow

```
task_description
    |
    v
 intake  ---- questions/answers ----> user
    |
    | (trusted context in LLM memory)
    v
 milestone-spec (CREATE) ----> milestones.md
    |
    v
 [milestone-review] ----> severity-classified findings (in chat)
    |                       \
    |                        +---> loop back to milestone-spec if critical/major
    v
 plan-spec ----> plan-milestone-1.md    <-- scoped to [in-progress] milestone
    |
    v
 [plan-review] ----> findings (in chat)
    |
    v
 execute ----> koan_request_executor(plan-milestone-1.md, milestones.md)
    |
    v
 exec-review ----> outcome classification (in chat)
    |
    v
 milestone-spec (UPDATE) ----> milestones.md updated:
    |                           mark completed [done], add Outcome,
    |                           mark next [in-progress]
    |
    +---> [if milestones remain] plan-spec -> ... -> exec-review -> [LOOP]
    |
    +---> [if all done/skipped] curation
```

## What this means for prompt design

- **Do NOT** add "verify against the actual code" directives to phases other
  than plan-review, exec-review, and milestone-review. That directive belongs
  exclusively to the adversarial phases.
- **Do** tell phases to trust prior phase output: "Intake has already explored
  the codebase and resolved ambiguities. Trust those findings."
- **Do** tell plan-review, exec-review, and milestone-review they trust nobody:
  "You are the only phase that independently checks claims against reality."
- **Do** frame milestone-review with compound-risk awareness: errors at this
  layer propagate through every subsequent plan-spec and executor session.
  See [milestones.md](./milestones.md) for the full design principles.
