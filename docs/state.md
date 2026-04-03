# State & Driver

How the driver manages epic and story state, routes between phases, and
enforces the file boundary invariant.

> Parent doc: [architecture.md](./architecture.md)

---

## The File Boundary in Practice

The driver writes JSON; LLMs write markdown. Tool code bridges both.

| Actor         | Reads                           | Writes                              |
| ------------- | ------------------------------- | ----------------------------------- |
| **Driver**    | `.json` state files, exit codes | `.json` state files                 |
| **LLM**       | `.md` files, codebase files     | `.md` files (output)                |
| **Tool code** | `.json` state (to validate)     | `.json` state + `.md` status (both) |

### Why the epic state module must not write markdown

The epic state module (`koan/epic_state.py`) reads and writes JSON only.
`status.md` writes belong exclusively in orchestrator tool handlers, which
bridge the two worlds by writing JSON state (for the driver) and templated
markdown (for LLMs) in the same operation.

### Filesystem-driven story discovery

Story IDs are discovered by scanning `stories/*/story.md`, not by reading a
driver-maintained JSON list. The orchestrator (during the ticket-breakdown phase) creates `story.md` files using
the `write` tool -- it has no reason to know the JSON state format. The driver
discovers what the LLM created by scanning, then populates the JSON story list
itself.

---

## Epic State

`epic-state.json` in the epic directory root. Tracks the current pipeline
phase and the list of story IDs.

```python
# koan/epic_state.py
{
    "phase": "intake",  # intake -> brief-generation -> core-flows -> tech-plan
                        # -> ticket-breakdown -> cross-artifact-validation
                        # -> execution -> implementation-validation -> completed
    "stories": []       # populated by driver after filesystem scan
}
```

### Epic phases

| Phase                       | What happens                                                                                |
| --------------------------- | ------------------------------------------------------------------------------------------- |
| `intake`                    | Intake subagent reads conversation, scouts codebase, asks user questions                    |
| `brief-generation`          | Brief-writer subagent distills landscape.md into brief.md; user reviews via artifact review |
| `core-flows`                | Define user journeys with sequence diagrams                                                 |
| `tech-plan`                 | Specify technical architecture                                                              |
| `ticket-breakdown`          | Generate story-sized implementation tickets                                                 |
| `cross-artifact-validation` | Validate cross-boundary consistency                                                         |
| `execution`                 | Implement tickets through supervised batch process                                          |
| `implementation-validation` | Post-execution alignment review                                                             |
| `completed`                 | All phases done                                                                             |



**`scouting` is intentionally absent.** Scouts run inside the
`koan_request_scouts` tool handler during intake/planning phases,
not as a top-level phase.

---

## Story State

One `state.json` per story in `stories/{story_id}/`.

```python
{
    "story_id": "auth-middleware",
    "status": "pending",
    "retry_count": 0,
    "max_retries": 2,
    "failure_summary": None,   # set by koan_retry_story
    "skip_reason": None,       # set by koan_skip_story or driver
    "updated_at": "2026-03-27T..."
}
```

### Story status lifecycle

```
pending --> selected --> planning --> executing --> verifying --> done
   |            ^                                       |
   |            +------------- retry <------------------+
   |                                                    |
   +---> skipped <--------------------------------------+
```

| Status      | Set by                                     | Meaning                                   |
| ----------- | ------------------------------------------ | ----------------------------------------- |
| `pending`   | Driver (initial)                           | Story exists, not yet started             |
| `selected`  | Orchestrator (`koan_select_story`)         | Chosen for execution                      |
| `planning`  | Driver                                     | Planner subagent is running               |
| `executing` | Driver                                     | Executor subagent is running              |
| `verifying` | Driver                                     | Post-execution orchestrator is evaluating |
| `done`      | Orchestrator (`koan_complete_story`)       | Successfully completed                    |
| `retry`     | Orchestrator (`koan_retry_story`)          | Failed, queued for re-execution           |
| `skipped`   | Orchestrator (`koan_skip_story`) or Driver | Permanently skipped                       |

### No `escalated` status

Escalation is handled via `koan_ask_question` -- the orchestrator asks the user
a question through MCP, gets an answer, then decides `retry` or `skip`.

### Retry budget

Each story starts with `max_retries: 2`. When the driver sees `status: "retry"`,
it increments `retry_count` and re-executes. When `retry_count >= max_retries`,
the driver sets the story to `skipped`.

---

## Driver and Orchestrator

The driver spawns the orchestrator once at run start and awaits its exit.
The orchestrator drives the entire workflow, including phase transitions and
story execution.

### Story execution (orchestrator-driven)

The orchestrator selects and manages stories during the execution phase via
MCP tools:

```
orchestrator calls koan_select_story(story_id)
  -> story status set to "selected"
orchestrator calls koan_spawn_executor(story_id, role="planner")
  -> driver spawns planner subagent, blocks until exit
orchestrator calls koan_spawn_executor(story_id, role="executor")
  -> driver spawns executor subagent, blocks until exit
  -> (if retry needed: pass retry_context to koan_spawn_executor)
orchestrator calls koan_complete_story / koan_retry_story / koan_skip_story
```

### Model config gate

When a web server is available, the pipeline blocks at startup until the user
confirms model tier selection. This happens before the orchestrator spawns.

---

## Atomic Writes

All state writes use atomic tmp-file + rename via `os.rename()`:

```python
tmp = f"{file_path}.tmp"
with open(tmp, "w") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
os.rename(tmp, file_path)
```

This applies to:

- `epic-state.json` (driver)
- `stories/{id}/state.json` (driver + orchestrator tools)
- `stories/{id}/status.md` (orchestrator tools)
- `subagents/{label}/task.json` (driver, before spawn)
- `subagents/{label}/state.json` (audit projection)

---

## Epic Directory Structure

```
{epic_dir}/
  epic-state.json           # Epic phase + story list
  landscape.md              # Written by orchestrator (intake phase)
  brief.md                  # Written by orchestrator (brief-generation phase)
  stories/
    {story_id}/
      story.md              # Written by orchestrator (ticket-breakdown phase)
      state.json            # Story lifecycle state
      status.md             # Templated status for LLM consumption
      plan/
        plan.md             # Written by planner
  subagents/
    orchestrator/
      task.json             # Task manifest (written once at run start)
      state.json            # Audit projection
      events.jsonl          # Audit log (covers entire run, all phases)
    scout-{id}-{timestamp}/
      task.json
      findings.md           # Scout output
      ...
    planner-{story_id}/
      task.json
      state.json
      events.jsonl
    executor-{story_id}/
      task.json
      state.json
      events.jsonl
```

---

## Audit Projection (`state.json`)

Each subagent's `state.json` is an eagerly-materialized summary written
atomically after every audit event. It is available on disk for debugging and
post-mortem analysis. Live SSE events are pushed directly from in-process state
transitions.

Key projection fields common to all roles:

| Field             | Type   | Meaning                                                 |
| ----------------- | ------ | ------------------------------------------------------- |
| `phase`           | string | Overall phase name (e.g., "intake", "brief-generation") |
| `step`            | number | Current step index within the phase                     |
| `step_name`       | string | Human-readable step label (e.g., "Scout (round 2)")     |
| `tokens_sent`     | number | Cumulative tokens in                                    |
| `tokens_received` | number | Cumulative tokens out                                   |

Orchestrator state tracked in `AppState` (in-memory, not persisted):

| Field | Type | Purpose |
|-------|------|---------|
| `user_message_buffer` | `list[ChatMessage]` | Buffered user chat messages, drained at each `koan_complete_step` |
| `phase_complete_future` | `asyncio.Future \| None` | Non-None while `koan_complete_step` is blocking at a phase boundary |

`ChatMessage` carries `content: str` and `timestamp_ms: int`. Messages are
appended by `POST /api/chat` and removed atomically by `drain_user_messages()`.
