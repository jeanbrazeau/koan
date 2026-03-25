# State & Driver

How the driver manages epic and story state, routes between phases, and
enforces the file boundary invariant.

> Parent doc: [architecture.md](./architecture.md)

---

## The File Boundary in Practice

The driver writes JSON; LLMs write markdown. Tool code bridges both.

| Actor | Reads | Writes |
|-------|-------|--------|
| **Driver** | `.json` state files, exit codes | `.json` state files |
| **LLM** | `.md` files, codebase files | `.md` files (output) |
| **Tool code** | `.json` state (to validate) | `.json` state + `.md` status (both) |

### Why state.ts must not write markdown

The state module (`epic/state.ts`) reads and writes JSON only. Putting
`writeStatusMarkdown()` there would make one module responsible for both
communication channels. `status.md` writes belong exclusively in
`tools/orchestrator.ts`, which bridges the two worlds by writing JSON state
(for the driver) and templated markdown (for LLMs) in the same operation.

### Filesystem-driven story discovery

Story IDs are discovered by scanning `stories/*/story.md`, not by reading a
driver-maintained JSON list. The decomposer LLM creates `story.md` files using
the `write` tool — it has no reason to know the JSON state format. Requiring
it to update `epic-state.json` would force an LLM to write JSON, violating the
core invariant.

The driver discovers what the LLM created by scanning, then populates the JSON
story list itself.

---

## Epic State

`epic-state.json` in the epic directory root. Tracks the current pipeline
phase and the list of story IDs.

```typescript
interface EpicState {
  phase: EpicPhase;     // intake → brief-generation → core-flows → tech-plan → ticket-breakdown → cross-artifact-validation → execution → implementation-validation → completed
  stories: string[];    // populated by driver after filesystem scan
}
```

### Epic phases

| Phase | What happens |
|-------|-------------|
| `intake` | Intake subagent reads conversation, scouts codebase, asks user questions |
| `brief-generation` | Brief-writer subagent distills landscape.md into brief.md; user reviews via artifact review |
| `core-flows` | Define user journeys with sequence diagrams (stub — auto-advances) |
| `tech-plan` | Specify technical architecture (stub — auto-advances) |
| `ticket-breakdown` | Generate story-sized implementation tickets (stub — auto-advances) |
| `cross-artifact-validation` | Validate cross-boundary consistency (stub — auto-advances) |
| `execution` | Implement tickets through supervised batch process (stub — auto-advances) |
| `implementation-validation` | Post-execution alignment review (stub — auto-advances) |
| `completed` | All phases done |

**`scouting` is intentionally absent.** Scouts run inside the IPC responder
during intake/decomposer/planner phases, not as a top-level phase. Adding it
would imply a driver state that never exists.

---

## Story State

One `state.json` per story in `stories/{storyId}/`.

```typescript
interface StoryState {
  storyId: string;
  status: StoryStatus;
  retryCount: number;
  maxRetries: number;       // default: 2
  failureSummary?: string;  // set by koan_retry_story
  skipReason?: string;      // set by koan_skip_story or driver on budget exhaustion
  updatedAt: string;
}
```

### Story status lifecycle

```
pending ──→ selected ──→ planning ──→ executing ──→ verifying ──→ done
   │            ↑                                       │
   │            └──────────── retry ←───────────────────┤
   │                                                    │
   └──→ skipped ←───────────────────────────────────────┘
```

| Status | Set by | Meaning |
|--------|--------|---------|
| `pending` | Driver (initial) | Story exists, not yet started |
| `selected` | Orchestrator (`koan_select_story`) | Chosen for execution |
| `planning` | Driver | Planner subagent is running |
| `executing` | Driver | Executor subagent is running |
| `verifying` | Driver | Post-execution orchestrator is evaluating |
| `done` | Orchestrator (`koan_complete_story`) | Successfully completed |
| `retry` | Orchestrator (`koan_retry_story`) | Failed, queued for re-execution |
| `skipped` | Orchestrator (`koan_skip_story`) or Driver | Permanently skipped |

**Driver-internal states** (`planning`, `executing`, `verifying`) are set by
the driver only. The LLM never writes these — it reads them indirectly via
`status.md`.

**Orchestrator-driven transitions** (`selected`, `done`, `retry`, `skipped`)
are set by orchestrator tool calls. Each tool validates the source status
before transitioning:

| Tool | Valid source | Target |
|------|-------------|--------|
| `koan_select_story` | `pending`, `retry` | `selected` |
| `koan_complete_story` | `verifying` | `done` |
| `koan_retry_story` | `verifying` | `retry` |
| `koan_skip_story` | `pending`, `retry` | `skipped` |

### No `escalated` status

Escalation is handled via `koan_ask_question` — the orchestrator asks the user
a question through IPC, gets an answer, then decides `retry` or `skip`. A
separate `escalated` status was tried and created a dead routing path.

### Retry budget

Each story starts with `maxRetries: 2`. When the driver sees `status: "retry"`,
it increments `retryCount` and re-executes. When `retryCount >= maxRetries`,
the driver sets the story to `skipped`:

```
skipReason: "Retry budget exhausted after N attempt(s). Last failure: {failureSummary}"
```

The `failureSummary` field flows from `koan_retry_story` (the orchestrator
writes a concrete description of what went wrong) to `retryContext` in the
executor's `task.json` on re-execution.

---

## Driver Routing

The driver's story loop is a deterministic state machine:

```typescript
while (true) {
  const stories = await loadAllStoryStates(epicDir);
  const routing = routeFromState(stories);

  switch (routing.action) {
    case "retry":   → re-execute story (increment retryCount)
    case "execute": → plan + execute story
    case "complete": → all stories terminal → exit loop
    case "error":   → no actionable state → fail
  }
}
```

**Priority:** `retry` is checked before `selected`. A story queued for retry
takes precedence over a newly selected story.

**Terminal states:** exactly `done` and `skipped`. The epic is complete when
every story is in a terminal state.

**Error state:** If no story is `retry` or `selected` and not all are terminal,
the driver reports: "orchestrator may have exited without a routing decision."

### Story execution pipeline

For each story selected for execution:

```
Driver sets status → planning
  → spawn planner subagent
  → if planner fails: skip executor, go to post-execution orchestrator
Driver sets status → executing
  → spawn executor subagent
Driver sets status → verifying
  → spawn orchestrator (post-execution)
  → orchestrator decides: koan_complete_story / koan_retry_story / koan_skip_story
```

### Planner failure fallthrough

When the planner exits with non-zero exit code, the driver skips the executor
and proceeds directly to the post-execution orchestrator. This gives the
orchestrator a chance to make a routing decision (retry, skip) rather than
leaving the story in a dead state.

### Model config gate

When a web server is available, the pipeline blocks at startup until the user
confirms model tier selection. This happens before any subagent spawns.

### Spec review gate

The spec review gate was removed as development scaffolding. Story review will
be revisited in the `cross-artifact-validation` phase using a different
mechanism. No web UI review gate exists in the current pipeline.

---

## Atomic Writes

All state writes use atomic tmp-file + rename:

```typescript
async function atomicWriteJson(filePath: string, data: unknown): Promise<void> {
  const tmp = `${filePath}.tmp`;
  await fs.writeFile(tmp, JSON.stringify(data, null, 2) + "\n", "utf8");
  await fs.rename(tmp, filePath);
}
```

This applies to:
- `epic-state.json` (driver)
- `stories/{id}/state.json` (driver + orchestrator tools)
- `stories/{id}/status.md` (orchestrator tools)
- `subagents/{label}/task.json` (driver, before spawn)
- `subagents/{label}/state.json` (audit projection)
- `subagents/{label}/ipc.json` (both sides)

---

## Epic Directory Structure

```
{epicDir}/
  epic-state.json           # Epic phase + story list
  conversation.jsonl        # Exported conversation (input to intake)
  landscape.md               # Written by intake (task summary, prior art, codebase findings, project conventions, decisions, constraints, open items)
  stories/
    {storyId}/
      story.md              # Written by decomposer
      state.json            # Story lifecycle state
      status.md             # Templated status for LLM consumption
      plan/
        plan.md             # Written by planner
  subagents/
    intake/
      task.json             # Task manifest
      state.json            # Audit projection
      events.jsonl          # Audit log
      stdout.log, stderr.log
    decomposer/
      ...
    scout-{id}-{timestamp}/
      task.json
      findings.md           # Scout output
      ...
    planner-{storyId}/
      ...
    executor-{storyId}/
      ...
    orchestrator-pre/
      ...
    orchestrator-post-{storyId}/
      ...
```

---

## Audit Projection (`state.json`)

Each subagent writes a `state.json` (the "projection") to its directory. The
projection is an eagerly-materialized summary of the subagent's current state,
updated atomically after every audit event. The web server polls it to push
SSE events to the UI without having to replay the full `events.jsonl`.

Key projection fields common to all roles:

| Field | Type | Meaning |
|-------|------|---------|
| `phase` | string | Overall phase name (e.g., "intake", "brief-generation") |
| `step` | number | Current step index within the phase |
| `stepName` | string | Human-readable step label (e.g., "Scout (round 2)") |
| `tokensSent` | number | Cumulative tokens in |
| `tokensReceived` | number | Cumulative tokens out |

Intake-specific fields (zero/null for all other roles):

| Field | Type | Meaning |
|-------|------|---------|
| `intakeConfidence` | `"exploring"\|"low"\|"medium"\|"high"\|"certain"\|null` | Last confidence level declared by `koan_set_confidence`. Null until first declaration; retains last value between loop iterations (not reset in projection on loop-back). |
| `intakeIteration` | number | Current loop iteration (1-based). Updated by `confidence_change` and `iteration_start` events. Zero for non-intake subagents. |

**Note on `intakeConfidence` and loop-back:** When `getNextStep()` decides to
loop from Reflect (step 4) back to Scout (step 2), it resets
`ctx.intakeConfidence = null` internally. This internal reset is NOT
propagated to the projection immediately — the projection retains the
previous iteration's confidence level until the next `koan_set_confidence`
call emits a `confidence_change` event. The UI therefore shows the last
declared confidence between iterations, which is intentional: it reflects
the most recent authoritative assessment rather than showing a transient
null state.
