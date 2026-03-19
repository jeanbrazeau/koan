# Koan Architecture

Koan is a deterministic pipeline that spawns isolated LLM subagents to plan and
execute complex coding tasks. This document captures the design invariants,
principles, and pitfalls that govern the codebase.

**Spoke documents** cover subsystems in depth:

- [Subagents](./subagents.md) — spawn lifecycle, boot protocol, step-first
  workflow, phase dispatch, permissions, model tiers
- [IPC](./ipc.md) — file-based inter-process communication between parent and
  subagent, scout spawning, question routing
- [State & Driver](./state.md) — the driver/LLM boundary, JSON vs markdown
  ownership, epic and story state, routing rules
- [Intake Loop](./intake-loop.md) — confidence-gated investigation loop,
  non-linear step progression, prompt engineering principles

---

## Core Invariants

These are load-bearing rules. Violating any one of them breaks the system in
ways that are difficult to diagnose.

### 1. File boundary

LLMs write **markdown files only**. The driver maintains **JSON state files**
internally — no LLM ever reads or writes a `.json` file.

Tool code bridges both worlds: orchestrator tools write JSON state (for the
driver) and templated `status.md` (for LLMs). The driver reads JSON and exit
codes; it never parses markdown.

```
Orchestrator calls koan_complete_story(story_id)
  → tool code writes state.json + status.md
  → driver reads state.json to route next action
  → LLM reads status.md if it needs to reference the decision
```

**Why:** If an LLM writes JSON, schema drift and parse errors become runtime
failures in the deterministic driver. Markdown is forgiving; JSON is not.

### 2. Step-first workflow

Every subagent is a `pi -p` process. Once the LLM produces text without a tool
call, the process exits — there is no stdin to recover. The entire workflow
depends on the LLM calling `koan_complete_step` reliably.

**The first thing any subagent does is call `koan_complete_step`.** The spawn
prompt contains *only* this directive. The tool returns step 1 instructions.
This establishes the calling pattern before the LLM sees complex instructions.

```
Boot prompt:  "You are a koan {role} agent. Call koan_complete_step to receive your instructions."
     ↓ LLM calls koan_complete_step (step 0 → 1 transition)
Tool returns:  Step 1 instructions (rich context, task details, guidance)
     ↓ LLM does work...
     ↓ LLM calls koan_complete_step
Tool returns:  Step 2 instructions (or "Phase complete.")
```

Three reinforcement mechanisms make this robust across model capability levels:

| Mechanism | Where | Why |
|-----------|-------|-----|
| **Primacy** | Boot prompt is the LLM's very first message | First action = tool call, at the top of conversation history |
| **Recency** | `formatStep()` appends "WHEN DONE: Call koan_complete_step..." last | LLMs weight end-of-context instructions heavily |
| **Muscle memory** | By step 2+ the LLM has called the tool N times | Pattern is locked in through repetition |

### 3. Driver determinism

The driver (`driver.ts`) is a deterministic state machine. It reads JSON state
files and exit codes, applies routing rules, and spawns the next subagent. It
never makes judgment calls, parses free-text output, or adapts to LLM behavior.

**Routing priority** in the story loop:
1. `retry` status → re-execute (retry takes precedence over new work)
2. `selected` status → plan + execute
3. All stories `done` or `skipped` → epic complete
4. None of the above → error ("orchestrator may have exited without a routing decision")

### 4. Default-deny permissions

Every tool call in a subagent passes through a permission fence (`tool_call`
event handler in `BasePhase`). Unknown roles are blocked. Unknown tools are
blocked. Planning roles can only write inside the epic directory.

The one accepted limitation: `READ_TOOLS` (bash, read, grep, glob, find, ls)
are always allowed because distinguishing "read bash" from "write bash" is
intractable at the permission layer. **Prompt engineering constrains intended
bash use; enforcement does not.**

### 5. Need-to-know prompts

Each subagent receives only the minimum context for its task:

- The **boot prompt** is one sentence (role identity + "call koan_complete_step")
- The **system prompt** establishes role identity and rules, but no task details
- **Task details** arrive via step 1 guidance (returned by the first tool call)

This is not just tidiness — it is load-bearing. A previous design injected
step 1 guidance into the first user message (via a `context` event handler),
but that front-loaded complex instructions before the LLM had established the
`koan_complete_step` calling pattern. Weaker models (haiku) produced text
output and exited without entering the workflow. The `context` event handler
was deliberately removed; step guidance is now delivered exclusively through
`koan_complete_step` return values.

### 6. Directory-as-contract

The subagent directory is the **sole interface** between parent and child.
Everything a subagent needs — its task, its communication channel, its
observable state — lives in well-known files inside that directory.

Three JSON files, three lifecycles:

| File | Writer | Reader | Lifecycle |
|------|--------|--------|-----------|
| **`task.json`** | Parent (before spawn) | Child (once, at startup) | Write-once, never modified |
| **`state.json`** | Child (continuously) | Parent (polling) | Eagerly materialized audit projection |
| **`ipc.json`** | Both (request/response) | Both (polling) | Temporary — created per request, deleted after response |

The spawn command carries only the directory path. The child reads `task.json`
to discover its role, epic context, and task-specific parameters. No
structured configuration flows through CLI flags, environment variables, or
other process-level channels.

```
# Spawn interface: one koan flag, the rest is pi-level
pi -p -e {extensionPath} --koan-dir {subagentDir} [--model {model}] "{bootPrompt}"
```

**Why:** CLI flags are a flat namespace — they cause naming collisions (e.g.,
`--koan-role` for pipeline role vs `--koan-scout-role` for investigator
persona), cannot represent nested structure, are visible in process listings,
and are subject to `ARG_MAX` limits for large values like retry context.
Files are structured, inspectable (`cat task.json`), typed, and consistent
with how we already handle runtime communication (IPC) and observation (audit).

See [subagents.md § Task Manifest](./subagents.md#task-manifest) for the
`task.json` schema and spawn flow.

---

## Atomic Writes

All persistent writes (JSON state, IPC files, status.md, audit state.json)
use the same pattern: write to a `.tmp` file, then `fs.rename()` to the target.
This prevents partial reads during concurrent access.

```typescript
const tmp = path.join(dir, "file.tmp");
await fs.writeFile(tmp, content, "utf8");
await fs.rename(tmp, target);
```

This is not optional — the IPC responder, web server, and audit system all
poll files concurrently. A partial read of `ipc.json` or `state.json` would
cause silent data corruption or spurious errors.

---

## Tool Registration Constraint

All tools **must** be registered unconditionally at extension init, before
pi's `_buildRuntime()` snapshot. Tools registered after `_buildRuntime()` are
invisible to the LLM.

CLI flags are unavailable during init (`getFlag()` returns undefined before
`_buildRuntime()` sets flagValues), so conditional registration based on role
is impossible. Instead:

1. All tools register at init, reading from the mutable `RuntimeContext` at call time
2. `BasePhase.registerHandlers()` adds a `tool_call` event listener that checks permissions per-role at runtime
3. The `RuntimeContext` is populated later, during `before_agent_start`

This is the **mutable-ref pattern**: static registration, dynamic dispatch.

---

## Pitfalls

Lessons learned from previous failures. Check new changes against these.

### Don't put task content in spawn prompts

The boot prompt must be exactly one sentence: role identity + "call
koan_complete_step". Putting task content (file paths, instructions, context)
risks the LLM producing text output on the first turn and exiting. This has
happened with haiku-class models and is not recoverable.

### Don't inject step guidance via the `context` event

A `context` event handler that injects step 1 guidance into the first user
message was tried and removed. It creates the same problem as putting content
in the spawn prompt — the LLM sees complex instructions before establishing
the tool-calling pattern.

### Don't add `escalated` as a story status

Escalation is handled via `koan_ask_question` (IPC → web server → user
answers → IPC response). A separate `escalated` status was tried and created
a dead routing path — the driver had nowhere clean to send it without
duplicating the ask UI flow that IPC already handles.

### Don't add `scouting` as an epic phase

Scouts run inside the IPC responder during intake/decomposer/planner phases,
not as a top-level driver phase. Adding `scouting` to `EpicPhase` would imply
a driver state that never exists, creating dead code paths.

### Don't rely on file existence for scout success

Scout success is derived from the JSON projection (`readProjection()` →
`status === "completed"`), not from checking whether `findings.md` exists.
A scout can write a partial findings file and then crash — file existence is
not proof of completion.

### Don't write state.json from outside state.ts / tool code

The state module (`epic/state.ts`) and orchestrator tools are the only
writers of JSON state. `status.md` writes belong exclusively in
`tools/orchestrator.ts`. Mixing these responsibilities violates the file
boundary invariant.

### Don't call koan_complete_step in the tool description eagerly

The tool description says "DO NOT call this tool until the step instructions
explicitly tell you to." Without this guard, aggressive models call
`koan_complete_step` immediately after receiving step guidance, skipping
the actual work.

### Don't assume bash is restricted per role

`bash` is in `READ_TOOLS` and always allowed. The permission layer cannot
distinguish a read-bash from a write-bash. Prompt engineering is the only
constraint. Do not assume bash calls are blocked for planning roles.

### Don't rely on prompt instructions alone to restrict step behavior

Prompt instructions can be ignored by the LLM. The intake phase learned this
the hard way: the original 3-step design told the LLM not to scout in step 1,
but the LLM frontloaded all work into step 1 anyway, causing duplicate scout
requests in later steps.

Mechanical enforcement is required for any behavior that is critical to
correctness. Use the permission fence (`checkPermission` with `intakeStep`) to
block tools that must not be used in a given step. Use
`validateStepCompletion()` to block step advancement when required pre-calls
have not been made. Prompts express intent; enforcement catches non-compliance.

See [intake-loop.md § Step-Aware Permission Gating](./intake-loop.md#step-aware-permission-gating).

### Don't parse free-text for loop control decisions

Confidence (the gate that controls the intake loop) is a structured enum
value set via a dedicated tool call, not a sentiment extracted from the LLM's
`thoughts` text. The driver determinism invariant prohibits parsing free-text
for routing decisions. Any loop gate must flow through a typed tool parameter
and a structured context field.

### Don't put side effects in getNextStep()

`getNextStep()` must be a pure query — it returns the next step number and
nothing else. Putting state mutations, counter increments, or event emission
inside `getNextStep()` violates this contract and makes the method unsafe to
reason about (e.g., a test that calls `getNextStep()` to inspect the decision
should not trigger side effects).

Side effects that accompany a loop-back belong in `onLoopBack()`, which
`BasePhase` calls after detecting a backward transition:

```
BAD:  getNextStep(4) { this.iteration++; this.ctx.confidence = null; return 2; }
GOOD: getNextStep(4) { return 2; }
      onLoopBack(4, 2) { this.iteration++; this.ctx.confidence = null; }
```

The `onLoopBack()` hook is async and properly awaited, ensuring event
emission (`emitIterationStart`) is correctly sequenced in `events.jsonl`.

### Don't pass structured data through CLI flags

If information is needed by a subagent, write it to `task.json` in the
subagent directory before spawning. CLI flags are for bootstrap only (locating
the directory). Structured data in flags creates flat-namespace collisions,
size limits, and an uninspectable interface. The directory-as-contract
invariant exists specifically to prevent this.
