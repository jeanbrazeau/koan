# Inter-Process Communication

HTTP MCP-based communication between the driver and subagent processes.

> Parent doc: [architecture.md](./architecture.md)
>
> The MCP endpoint at `http://localhost:{port}/mcp?agent_id={id}` is the sole
> communication channel between parent and child. See
> [architecture.md -- Directory-as-contract](./architecture.md#6-directory-as-contract).

---

## Overview

Subagent CLI processes (`claude`, `codex`, `gemini`) communicate with the
driver via HTTP MCP tool calls. The driver runs a single Starlette HTTP server
that handles both the web dashboard and the MCP tool endpoint. When a tool call
arrives, the server looks up the agent's state by `agent_id` in an in-process
registry and handles the call directly.

Three tool calls involve blocking interactions -- the HTTP request is held open
while the driver awaits an external response:

| Tool                   | What blocks             | Who responds                   |
| ---------------------- | ----------------------- | ------------------------------ |
| `koan_ask_question`    | User input needed       | User via web UI                |
| `koan_request_scouts`  | Scout subagents running | Driver (after scouts complete) |
| `koan_review_artifact` | User review needed      | User via web UI                |
| `koan_propose_workflow`| User workflow decision  | User via web UI                |

User-facing tools (`koan_ask_question`, `koan_review_artifact`,
`koan_propose_workflow`) go through the `PendingInteraction` queue on
`AppState`. The MCP handler creates an `asyncio.Future`, stores it in
`AgentState.pending_tool`, enqueues a `PendingInteraction` on `AppState`, and
awaits the Future. The HTTP connection stays open until the Future resolves.

`koan_request_scouts` is handled entirely inline: the handler spawns scouts via
`asyncio.gather` of `spawn_subagent` calls (bounded by a semaphore), collects
their results, and returns directly. No `PendingInteraction` is created; the
HTTP connection is held open only by the `await asyncio.gather(...)` call.

There is no polling and no intermediate files for any of these flows.

---

## Blocking Interaction Model

### `asyncio.Future` resolution (user-facing interactions)

When a user-facing blocking tool is called:

1. MCP endpoint receives tool call with `agent_id`
2. Handler creates `asyncio.Future`, stores it in `AgentState.pending_tool`,
   and enqueues a `PendingInteraction` on `AppState.interaction_queue`
3. If no interaction is currently active, the interaction is promoted to
   `AppState.active_interaction` and an SSE event is pushed to browsers
   (question form, review form, or workflow-decision form)
4. Handler `await`s the Future -- HTTP connection stays open
5. User fills the form in the web UI and submits:
   - `POST /api/answer` resolves the Future for `koan_ask_question`
   - `POST /api/artifact-review` resolves it for `koan_review_artifact`
   - `POST /api/workflow-decision` resolves it for `koan_propose_workflow`
6. Handler returns the resolved value as the MCP tool result; the next queued
   interaction (if any) is promoted to active

```
subagent ---POST /mcp koan_ask_question---> driver
                                             |
                                             +-- create Future
                                             +-- store Future in AgentState.pending_tool
                                             +-- enqueue PendingInteraction on AppState
                                             +-- push SSE "ask" event to browser
                                             +-- await Future
                                             |
                          user fills form <---+
                          POST /api/answer ---+
                                             |
                                             +-- resolve Future with answer
                                             |
subagent <---tool result (answer)----------- +
```

### `PendingInteraction`

The `PendingInteraction` object stored in `AppState.active_interaction` (or
queued in `AppState.interaction_queue`):

- `type` -- one of `"ask"`, `"artifact-review"`, `"workflow-decision"`
- `agent_id` -- the agent that issued the blocking call
- `token` -- UUID for SSE correlation
- `payload` -- type-specific request data
- `future` -- the `asyncio.Future` awaiting resolution

`AgentState.pending_tool` holds the raw `asyncio.Future` for the currently
blocked MCP call on that agent (not the `PendingInteraction` object itself).

### Constraints

- **Global FIFO queue** -- `AppState.interaction_queue` is a single queue
  shared across all agents. At most one interaction is active at a time; up to
  8 additional interactions may be queued (`interaction_queue_max = 8`). A
  call that would exceed the cap (9 total: 1 active + 8 queued) raises
  `interaction_queue_full`.
- **No polling** -- resolution is immediate when the external actor responds.
- **The subagent's LLM turn is blocked** while the Future is pending. The MCP
  HTTP connection is held open; the LLM cannot call other tools until the
  response arrives.

---

## Ask Flow

```
subagent calls koan_ask_question({ questions: [...] })
  -> MCP endpoint checks permissions
  -> creates asyncio.Future, stores in AgentState.pending_tool
  -> enqueues PendingInteraction { type: "ask" } on AppState
  -> if no active interaction: promotes to active, pushes SSE `questions_asked` event to browsers
  -> awaits Future

user sees question form in web UI
  -> fills form, clicks Submit
  -> POST /api/answer -> resolves Future with user's selection

MCP handler receives resolved value
  -> clears AgentState.pending_tool
  -> activates next queued interaction (if any)
  -> formats answer as structured text
  -> returns as MCP tool result to subagent
```

The "Other" option is appended server-side -- the LLM never includes it.

---

## Scout Flow

```
subagent calls koan_request_scouts({ questions: [...] })
  -> MCP endpoint checks permissions
  -> no PendingInteraction created

  handler runs inline via asyncio.gather (semaphore-bounded concurrency):
    -> for each scout task:
        -> assign scout agent_id
        -> ensure subagent directory
        -> spawn scout CLI process via spawn_subagent()
        -> scout connects to /mcp?agent_id={scout_id}
        -> scout calls koan_complete_step, does work, completes
        -> SubagentResult collected (exit_code, final_response)
    -> all scouts run concurrently up to scout_concurrency limit
    -> asyncio.gather returns list of results

MCP handler processes results
  -> collects non-None final_response values as findings
  -> returns concatenated findings as MCP tool result to subagent
  (HTTP connection was held open by await asyncio.gather for the duration)
```

### Scout pool behavior

All scouts are submitted concurrently with a configurable concurrency limit
(default: 4). The pool:

- **Runs all items to completion** regardless of individual failures
- **Reports progress** via SSE events (`scout_queued` emitted before gather)
- **Does not implement timeouts** -- timeout logic belongs in the caller

### Scout success determination

Scout success is derived from the subagent's exit code and final response, not
file existence:

```python
result = await spawn_subagent(scout_task, _app_state)
succeeded = result.exit_code == 0
findings = result.final_response or None
```

### Failed scouts are non-fatal

Scouts that exit non-zero return `None` from `run_scout()` and are omitted from
findings. The tool result notes any missing scouts:

`"No findings returned."` (if all fail) or silently omits failed scouts from
the concatenated output.

---

## Artifact Review Flow

```
subagent calls koan_review_artifact({ path: ".../brief.md" })
  -> MCP endpoint checks permissions
  -> reads file content from path
  -> creates asyncio.Future, stores in AgentState.pending_tool
  -> enqueues PendingInteraction { type: "artifact-review" } on AppState
  -> if no active interaction: promotes to active, pushes SSE `artifact_review_requested`
     event to browsers (with rendered content)
  -> awaits Future

user sees rendered markdown in web UI
  -> clicks "Accept" or types feedback and clicks "Send Feedback"
  -> POST /api/artifact-review -> resolves Future with feedback string

MCP handler receives resolved value
  -> clears AgentState.pending_tool
  -> activates next queued interaction (if any)
  -> sets AgentState.phase_ctx.last_review_accepted
  -> returns "ACCEPTED" or "REVISION REQUESTED: {feedback}" as MCP tool result

if feedback == "Accept":
  LLM calls koan_complete_step -> phase advances
else:
  LLM revises artifact, calls koan_review_artifact again
  (loop repeats with fresh PendingInteraction)
```

See [artifact-review.md](./artifact-review.md) for the full protocol.

---

## Workflow Decision Flow

```
subagent calls koan_propose_workflow({ status: "...", phases: [...] })
  -> MCP endpoint checks permissions
  -> normalises phases list to list[dict]
  -> creates asyncio.Future, stores in AgentState.pending_tool
  -> enqueues PendingInteraction { type: "workflow-decision" } on AppState
  -> if no active interaction: promotes to active, pushes SSE
     `workflow_decision_requested` event to browsers (with phase proposals)
  -> awaits Future

user sees workflow proposal in web UI
  -> selects a phase (or types custom input), clicks Confirm
  -> POST /api/workflow-decision -> resolves Future with { phase, context }

MCP handler receives resolved value
  -> clears AgentState.pending_tool
  -> activates next queued interaction (if any)
  -> sets AgentState.phase_ctx.proposal_made = True
  -> returns "Selected: {phase}\n{context}" as MCP tool result to subagent

subagent then calls koan_set_next_phase({ phase: "..." }) to commit the choice
```

---

## Sequence Diagrams

### Scout flow (inline blocking, no PendingInteraction)

```
Driver                         Scout CLI              Web UI
  |                                |                     |
  |<--koan_request_scouts---------|                     |
  |  emit scout_queued events     |                     |
  |  asyncio.gather (semaphore)   |                     |
  |  spawn scout processes------->|                     |
  |                               |--koan_complete_step->|
  |                               |<-step 1 guidance----|
  |                               |  (does work)        |
  |                               |--koan_complete_step->|
  |                               |<-"Phase complete."--|
  |  scout exits (exit_code 0)    |                     |
  |  gather collects results      |                     |
  |--tool result (findings)------>|                     |
```

### User interaction flow (blocking via PendingInteraction queue)

```
Subagent                      Driver                    Web UI
  |                              |                        |
  |--koan_ask_question---------->|                        |
  |                              |  create Future         |
  |                              |  enqueue interaction   |
  |                              |--SSE "ask" event------>|
  |                              |                        | user sees form
  |                              |                        | user submits
  |                              |<-POST /api/answer------|
  |                              |  resolve Future        |
  |                              |  activate next queued  |
  |<-tool result (answer)--------|                        |
```
