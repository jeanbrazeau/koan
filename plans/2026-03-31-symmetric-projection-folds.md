# Server-Authoritative State with JSON Patch

**Date:** 2026-03-31
**Status:** Draft
**Goal:** Single fold in Python, server-computed diffs via JSON Patch, frontend as a dumb renderer with zero business logic.

---

## Motivation

Two user-visible bugs on page refresh exposed a deeper architectural problem:

**Bug 1 — Fragmented thinking cards:** After refresh, thinking was displayed as dozens of tiny cards ("The", "user wants", "me to call"…) instead of one merged block. The live path accumulated deltas in a buffer; the snapshot path created one card per raw event.

**Bug 2 — Scout events in the primary feed:** After refresh, scout step headers and thinking blocks appeared in the primary agent's activity feed. The live path filtered by agent; the snapshot path did not.

**Root cause:** The backend's `activity_log` stored raw events, not materialized state. The frontend re-folded this raw log on snapshot recovery — duplicating fold logic inconsistently. But the deeper question is: **why does the frontend run fold logic at all?**

The answer: it shouldn't. The fold exists in one place (Python). The frontend applies server-computed state changes mechanically. This is how Google Docs, Figma, Linear, and Phoenix LiveView work — server computes, client renders.

---

## Architecture

### Core principle: server computes, client applies

The fold runs **only in Python**. The frontend has **zero business logic** — no event interpretation, no buffer management, no agent filtering, no in-flight tracking. It receives state and renders it.

### Protocol: snapshot + JSON Patch + streaming deltas

The server sends three types of SSE messages:

| SSE event | When | Payload | Client action |
|-----------|------|---------|---------------|
| `snapshot` | First connect, reconnect | `{version, state}` — full materialized projection (camelCase) | Replace entire store |
| `patch` | After each event (except deltas) | `{version, patch}` — RFC 6902 JSON Patch operations (camelCase paths) | `applyPatch(store, patch)` |
| `delta` | `thinking` / `stream_delta` events | `{version, path, delta}` — string append (camelCase path) | `store[path] += delta` |

**Why three types, not just patches?**

JSON Patch's `replace` operation for a growing string buffer is O(buffer_size) per delta. A `thinking_buffer` at 10KB with 20 deltas/second produces 200KB/s of patches — vs 600B/s for raw deltas. Streaming buffers are special-cased for bandwidth efficiency. Everything else goes through standard JSON Patch.

### Connection lifecycle

```
First connect:     GET /events?since=0
                   ← snapshot {version: N, state: <Projection>}      (camelCase keys)
                   ← patch {version: N+1, patch: [...]}              (camelCase paths)
                   ← delta {version: N+2, path: "thinkingBuffer", delta: "The user"}
                   ← delta {version: N+3, path: "thinkingBuffer", delta: " wants me"}
                   ← patch {version: N+4, patch: [...]}
                   ...

Reconnect:         GET /events?since=N+4
                   ← snapshot {version: M, state: <Projection>}
                   (always a fresh snapshot — no patch replay)

Server restart:    GET /events?since=N+4
                   ← snapshot {version: 0, state: <empty projection>}
                   (client detects version < lastVersion, resets UI)
```

**Catch-up always uses snapshots.** Storing patches for replay is expensive (200K–500K events over a full epic, thinking patches are large). On reconnect, the server sends a fresh snapshot at the current version. The `since` parameter is a version check: if it matches the server's version, skip the snapshot and go straight to live events. Otherwise, send a snapshot.

This eliminates `events_since()` and the catch-up replay code path entirely. It also **eliminates `fatal_error`**: the current code sends `fatal_error` when `since > store.version` (after server restart), requiring the user to manually reload. The new design always sends a snapshot instead — the client detects the version regression (`snapshot.version < lastVersion`) and resets its UI automatically. One code path for all reconnects.

### What the server stores

| Store | Purpose | Lifetime |
|-------|---------|----------|
| `self.events: list[VersionedEvent]` | Audit log, debugging | Session (in-memory) |
| `self.projection: Projection` | Materialized state for snapshots + diff computation | Session |
| `self.prev_state: dict` | Previous `to_wire()` for computing patches | Overwritten each event |

No stored patches. No catch-up replay buffer.

### Server-side push_event flow

```python
def push_event(self, event_type, payload, agent_id=None):
    self.version += 1
    event = VersionedEvent(version=self.version, ...)
    self.events.append(event)                          # audit log

    old_state = self.prev_state
    self.projection = fold(self.projection, event)
    new_state = self.projection.to_wire()              # camelCase via alias_generator
    self.prev_state = new_state

    # Streaming deltas: bypass JSON Patch, send raw delta
    if event_type in ("thinking", "stream_delta"):
        msg = {"type": "delta", "version": self.version,
               "path": "thinkingBuffer" if event_type == "thinking" else "streamBuffer",
               "delta": payload["delta"]}
    else:
        patch = jsonpatch.make_patch(old_state, new_state)
        if not patch:
            return  # no-op event (e.g. koan MCP tool filtered by fold)
        msg = {"type": "patch", "version": self.version,
               "patch": patch.to_string()}

    # Broadcast to all subscribers as a plain dict
    for q in list(self.subscribers):
        q.put_nowait(msg)
```

Subscriber queues carry **plain dicts**, not `VersionedEvent` objects. The dict shape matches the SSE JSON payload directly — the `sse_stream()` consumer just serializes and sends. This is a deliberate simplification: the raw event is for the audit log, the dict message is for the wire.

### Wire format: camelCase via Pydantic aliases

The server emits camelCase JSON. The frontend applies it directly — no field renaming, no shadow state, no mapping function.

Pydantic's `alias_generator` handles the conversion at serialization boundaries. Python fold code still uses snake_case attributes (`projection.thinking_buffer`). Only `to_wire()` output is camelCase:

```python
from pydantic import ConfigDict
from pydantic.alias_generators import to_camel

class KoanBaseModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    def to_wire(self) -> dict:
        """Serialize for snapshots and patch computation. Always camelCase."""
        return self.model_dump(by_alias=True)
```

All projection models (`Projection`, `AgentProjection`, `ConversationEntry` types, etc.) inherit from `KoanBaseModel`. Snapshot JSON, patch paths, and delta paths are all camelCase. The frontend receives `thinkingBuffer`, `primaryAgent`, `configActiveProfile` — matching JavaScript conventions natively.

**Why not keep snake_case on the wire and rename in the frontend?** Because that requires a `mapProjectionToStore()` function that renames every field, a `projectionState` shadow variable holding the snake_case dict for patch application (separate from the Zustand store), and maintenance of both in sync with the Projection model. Every new field needs a rename entry. That mapping layer *is* business logic — it contradicts the "frontend has zero business logic" principle. Emitting camelCase from the server eliminates the layer entirely: patches apply directly to the store, snapshots spread directly into the store, and adding a field to the Projection requires zero frontend changes.

### Frontend event handling — complete implementation

```typescript
let storeState: Record<string, unknown> = {}  // raw state for patch application

es.addEventListener('snapshot', (e) => {
  const { version, state } = JSON.parse(e.data)
  storeState = state
  set({ lastVersion: version, ...state })
})

es.addEventListener('patch', (e) => {
  const { version, patch } = JSON.parse(e.data)
  storeState = applyPatch(storeState, patch).newDocument
  set({ lastVersion: version, ...storeState })
})

es.addEventListener('delta', (e) => {
  const { version, path, delta } = JSON.parse(e.data)
  set(s => {
    if (path === 'thinkingBuffer')
      return { lastVersion: version, thinkingBuffer: s.thinkingBuffer + delta, isThinking: true }
    if (path === 'streamBuffer')
      return { lastVersion: version, streamBuffer: s.streamBuffer + delta, isThinking: false }
    return { lastVersion: version }
  })
})
```

That is the **entire** frontend sync implementation. No `applyEvent`. No 33-case switch. No fold logic. No buffer flushing. No agent filtering. No `completedCallIds` sets. No `mapProjectionToStore`. No field renaming.

**`storeState`** is a module-level variable in `connect.ts` that holds the current raw projection dict for patch application. It must be a plain JS object (not Zustand state) because `fast-json-patch`'s `applyPatch` operates on plain objects. On snapshot, it is replaced wholesale. On patch, `applyPatch` returns a `newDocument` (the immutable variant — avoids mutating the previous state in case Zustand still references it). The Zustand store is updated by spreading `storeState` into it.

**`isThinking` is a stored field, not derived.** The `delta` handler for `thinkingBuffer` sets `isThinking: true`. When the fold flushes `thinking_buffer` into a `ThinkingEntry` (on transition to a tool call or text output), the patch clears `thinkingBuffer` to `""` and the spread into the store updates it. The `patch` handler implicitly sets `isThinking` to `false` when the snapshot state has an empty `thinkingBuffer`. Components read a definitive boolean, not a derived check.

**Error handling:** If `applyPatch` throws (malformed patch, path mismatch, or stale state), the client cannot safely continue — its local state may be inconsistent. The correct recovery is to force a reconnect with `since=0` to get a fresh snapshot. The error handler should: log the error, close the EventSource, reset `lastVersion` to 0, and reconnect.

**Ordering guarantee:** SSE messages are delivered in order over a single HTTP connection. Patches cannot arrive out of order. If the connection drops, the client reconnects and receives a fresh snapshot — there is no partial patch replay to misorder. The `version` field in each message is for diagnostics only; the client does not need to reorder messages.

---

## Why not dual folds?

The initial design considered symmetric folds: identical fold logic in Python and TypeScript. This was rejected:

| Concern | Dual folds | JSON Patch |
|---------|-----------|------------|
| Fold implementations | 2 (Python + TypeScript) — must stay in sync forever | **1 (Python only)** |
| New event type cost | Python fold + TS fold + TS snapshot reconstruction | **Python fold only** — frontend unchanged |
| Bug surface | Proportional to event_type_count × 2 | Proportional to event_type_count × 1 |
| Frontend complexity | 33-case switch + buffer management + agent filtering | **3 event listeners, zero business logic** |
| Correctness guarantee | Requires "symmetric fold invariant" — manual discipline | **Correct by construction** — frontend cannot diverge |

The dual-fold approach is *complected* in the Rich Hickey sense: fold logic interleaved with two language runtimes. The "symmetric fold invariant" is an admission that the architecture requires discipline to maintain. JSON Patch eliminates the problem: there is no invariant to enforce because the logic exists in one place.

### Why not WASM shared fold?

Compile fold to WASM, run in both Python and browser. Eliminates duplication but adds WASM toolchain, FFI boundaries, and build complexity. Over-engineered for a single-user local tool.

### Why not server-rendered HTML (LiveView)?

Server renders the full UI, sends DOM diffs. Zero client logic. But koan's UI has rich interactivity — question wizards, settings overlays, artifact browsing, drag interactions. LiveView fights against client-side interactivity.

---

## Projection Model

The projection is the single materialized view of all state. The backend fold produces it, `get_snapshot()` serializes it, patches express incremental changes to it, the frontend renders it.

### ConversationEntry — discriminated union of distinct types

The primary agent's activity is a timeline: reasoning blocks, text output, tool calls, step transitions. Each entry type has exactly the fields it needs — no optional fields that only apply to other variants.

```python
class ThinkingEntry(KoanBaseModel):
    type: Literal["thinking"] = "thinking"
    content: str                          # full accumulated thinking text

class TextEntry(KoanBaseModel):
    type: Literal["text"] = "text"
    text: str                             # full accumulated stream text

class StepEntry(KoanBaseModel):
    type: Literal["step"] = "step"
    step: int
    step_name: str                        # wire: "stepName"
    total_steps: int | None = None        # wire: "totalSteps"

class BaseToolEntry(KoanBaseModel):
    """Shared fields for all tool conversation entries."""
    call_id: str                          # wire: "callId"
    in_flight: bool                       # wire: "inFlight"

class ToolReadEntry(BaseToolEntry):
    type: Literal["tool_read"] = "tool_read"
    file: str
    lines: str = ""

class ToolWriteEntry(BaseToolEntry):
    type: Literal["tool_write"] = "tool_write"
    file: str

class ToolEditEntry(BaseToolEntry):
    type: Literal["tool_edit"] = "tool_edit"
    file: str

class ToolBashEntry(BaseToolEntry):
    type: Literal["tool_bash"] = "tool_bash"
    command: str

class ToolGrepEntry(BaseToolEntry):
    type: Literal["tool_grep"] = "tool_grep"
    pattern: str

class ToolLsEntry(BaseToolEntry):
    type: Literal["tool_ls"] = "tool_ls"
    path: str

class ToolGenericEntry(BaseToolEntry):
    type: Literal["tool_generic"] = "tool_generic"
    tool_name: str
    summary: str = ""

ConversationEntry = Annotated[
    ThinkingEntry | TextEntry | StepEntry |
    ToolReadEntry | ToolWriteEntry | ToolEditEntry |
    ToolBashEntry | ToolGrepEntry | ToolLsEntry | ToolGenericEntry,
    Field(discriminator="type"),
]
```

**Why one type per variant:** Invalid states are unrepresentable. You cannot access `.command` on a `ThinkingEntry`. The type system enforces valid field combinations. Each type maps 1:1 to a frontend rendering component.

**`tool_completed` handling:** All tool types inherit `BaseToolEntry` with `call_id` and `in_flight`. The fold scans `conversation` for `isinstance(entry, BaseToolEntry) and entry.call_id == target`, sets `in_flight = False`.

**Extensibility:** Adding `ToolWebFetchEntry` means: define the Pydantic model, add to the union, add a fold case. The frontend is unchanged — JSON Patch carries the new entry structure automatically.

### Fold rules

The fold maintains `conversation: list[ConversationEntry]` plus two transient buffers (`thinking_buffer`, `stream_buffer`). Buffers accumulate deltas; they flush to completed entries on transitions.

| Event | Action |
|-------|--------|
| `thinking` (primary only) | Flush `stream_buffer` → TextEntry. Append delta to `thinking_buffer`. |
| `stream_delta` (primary only) | Flush `thinking_buffer` → ThinkingEntry. Append delta to `stream_buffer`. |
| `tool_*` (primary, non-koan) | Flush both buffers. Append typed tool entry (`in_flight=True`). |
| `tool_called` (koan MCP — `koan_*`) | Ignore for conversation. |
| `tool_completed` (primary only) | Set `in_flight=False` on matching `call_id`. |
| `agent_step_advanced` (primary) | Flush both buffers. Append StepEntry if `step >= 1`. Update agent step/tokens. |
| `agent_step_advanced` (scout) | Update scout step/tokens only. |
| `stream_cleared` (primary only) | Flush both buffers. |
| Tool events (scout) | Update scout's `last_tool`. |
| `agent_exited` | Set `status`, `error` on agent. Move to `completed_agents`. |

**Why primary-agent filtering is in the fold:** The fold owns the semantics of what belongs in the conversation. A single authoritative filter prevents the inconsistency bugs that triggered this plan.

**Why koan MCP tools are filtered:** `koan_complete_step` et al. are infrastructure — their effects are captured by `agent_step_advanced`, `questions_asked`, etc. Showing them as tool lines is noise.

### Full projection

```python
class Projection(KoanBaseModel):    # inherits alias_generator=to_camel
    run_started: bool = False
    phase: str = ""

    primary_agent: AgentProjection | None = None
    scouts: dict[str, AgentProjection] = {}
    queued_scouts: list[QueuedScout] = []
    completed_agents: list[AgentProjection] = []

    conversation: list[ConversationEntry] = []
    thinking_buffer: str = ""                # partial thinking in progress
    stream_buffer: str = ""                  # partial text output in progress
    # NOTE: stream_buffer already exists in the current Projection.
    # thinking_buffer is new. Both are required for the delta SSE path.

    active_interaction: InteractionState | None = None
    artifacts: dict[str, ArtifactInfo] = {}
    notifications: list[NotificationEntry] = []
    completion: CompletionInfo | None = None

    config_runners: list[RunnerInfo] = []
    config_profiles: list[ProfileInfo] = []
    config_installations: list[InstallationInfo] = []
    config_active_profile: str = "balanced"
    config_scout_concurrency: int = 8
```

### Agent model

```python
class AgentProjection(KoanBaseModel):
    agent_id: str
    role: str
    label: str = ""                 # NEW — scout identifier (e.g. "engine-methods")
    model: str | None = None
    step: int = 0
    step_name: str = ""
    started_at_ms: int = 0          # existing field
    input_tokens: int = 0
    output_tokens: int = 0
    status: Literal["running", "done", "failed"] = "running"  # NEW
    error: str | None = None        # NEW
    last_tool: str = ""             # NEW — last tool summary for scout monitor
```

`label`, `status`, `error`, `last_tool` are the four additions. The frontend's `transformAgent()` already reads these fields from the snapshot — they are expected but not yet emitted by the backend's `AgentProjection`. This plan closes that gap.

---

## Event Types (36 total)

### Lifecycle (7)

| Event | Payload |
|-------|---------|
| `phase_started` | `{phase}` |
| `agent_spawned` | `{agent_id, role, label, model, is_primary, started_at_ms}` |
| `agent_spawn_failed` | `{role, error_code, message, details?}` |
| `agent_step_advanced` | `{step, step_name, usage?, total_steps?}` |
| `agent_exited` | `{exit_code, error?, usage?}` |
| `workflow_completed` | `{success, summary?, error?}` |
| `scout_queued` | `{scout_id, label, model?}` |

### Activity (11)

| Event | Payload |
|-------|---------|
| `tool_called` | `{call_id, tool, args, summary}` |
| `tool_read` | `{call_id, tool:"read", file, lines}` |
| `tool_write` | `{call_id, tool:"write", file}` |
| `tool_edit` | `{call_id, tool:"edit", file}` |
| `tool_bash` | `{call_id, tool:"bash", command}` |
| `tool_grep` | `{call_id, tool:"grep", pattern}` |
| `tool_ls` | `{call_id, tool:"ls", path}` |
| `tool_completed` | `{call_id, tool, result?}` |
| `thinking` | `{delta}` |
| `stream_delta` | `{delta}` |
| `stream_cleared` | `{}` |

### Interactions (6)

| Event | Payload |
|-------|---------|
| `questions_asked` | `{token, questions}` |
| `questions_answered` | `{token, cancelled, answers?}` |
| `artifact_review_requested` | `{token, path, description, content}` |
| `artifact_reviewed` | `{token, cancelled, accepted?, response?}` |
| `workflow_decision_requested` | `{token, chat_turns}` |
| `workflow_decided` | `{token, cancelled, decision?}` |

### Resources (3)

| Event | Payload |
|-------|---------|
| `artifact_created` | `{path, size, modified_at}` |
| `artifact_modified` | `{path, size, modified_at}` |
| `artifact_removed` | `{path}` |

### Configuration (9)

| Event | Payload |
|-------|---------|
| `probe_completed` | `{runners}` |
| `installation_created` | `{alias, runner_type, binary, extra_args}` |
| `installation_modified` | `{alias, runner_type, binary, extra_args}` |
| `installation_removed` | `{alias}` |
| `profile_created` | `{name, read_only, tiers}` |
| `profile_modified` | `{name, read_only, tiers}` |
| `profile_removed` | `{name}` |
| `active_profile_changed` | `{name}` |
| `scout_concurrency_changed` | `{value}` |

---

## Scale considerations

**Projected state over a full epic:**
- 20 markdown documents × 10 tickets = 200 artifacts (~2MB of content references)
- 5 agent sessions per ticket × 10 tickets = 50 primary agent runs
- 5 batches of 10 scouts = 250 scout sessions
- Each scout: ~50 tool calls, ~20 thinking blocks
- Primary agents: ~200 tool calls, ~100 thinking blocks per session
- Total events: ~200K–500K over the epic

**Why JSON Patch works at this scale:**
- Tool call patches: ~100 bytes each (add entry to conversation array)
- Step advance patches: ~200 bytes (flush + add)
- `tool_completed`: ~80 bytes (replace one `in_flight` field)
- Thinking/stream deltas: bypassed entirely (raw delta events)
- Snapshot size at peak: ~50MB (dominated by artifact content references)
- Snapshot sent only on connect/reconnect — not per-event

**Why patch replay was rejected for catch-up:** 500K events × variable patch size = unbounded memory. A fresh snapshot (50MB once) is cheaper and simpler than replaying patches.

---

## Implementation Plan

### Phase 1: Backend — materialized projection with JSON Patch

1. `pip install jsonpatch` — add to dependencies
2. Define `KoanBaseModel` with `alias_generator=to_camel, populate_by_name=True` and `to_wire()` method
3. Define `ConversationEntry` union and all entry types inheriting `KoanBaseModel`
4. Migrate `Projection`, `AgentProjection`, and all sub-models to inherit `KoanBaseModel`
5. Add `conversation`, `thinking_buffer` to `Projection`; remove `activity_log`
6. Add `label`, `status`, `error`, `last_tool` to `AgentProjection`
7. Rewrite fold cases for all 36 event types
8. Update `ProjectionStore.push_event()`:
   - Use `projection.to_wire()` (not `model_dump()`) for camelCase dicts
   - Compute JSON Patch between old and new `to_wire()` output
   - For `thinking`/`stream_delta`: broadcast `delta` message with camelCase path
   - For all others: broadcast `patch` message (paths are automatically camelCase)
   - Store `prev_state` for next diff computation
9. Update `sse_stream()`:
   - `since=0`: send snapshot via `to_wire()`, then live
   - `since=N` where N == server version: skip snapshot, go straight to live
   - `since=N` where N != server version: send fresh snapshot (not event replay)
   - Remove `events_since()` — no longer used for catch-up
   - Remove `fatal_error` path — replaced by always-snapshot (client auto-recovers from version regression)
10. Update `get_snapshot()` to use `to_wire()` — output is camelCase, frontend reads it directly

### Phase 2: Frontend — dumb renderer

1. `npm install fast-json-patch`
2. Define TypeScript `ConversationEntry` union matching the wire format (camelCase)
3. Replace `connect.ts`:
   - 3 event listeners: `snapshot`, `patch`, `delta`
   - Module-level `storeState` variable for patch application
   - Remove KNOWN_EVENTS list and per-event-type listeners
   - Remove `fatal_error` listener (no longer emitted)
4. Delete `applySnapshot` and `applyEvent` entirely — snapshot spreads directly into store
5. Delete `mapProjectionToStore()` — no field renaming needed (server emits camelCase)
6. Update Zustand store field names to match wire format where they diverge
7. Update `ActivityFeed` and components to read `ConversationEntry` camelCase field names (`callId`, `inFlight`, `stepName`, `toolName`)

### Phase 3: Tests

1. Backend fold tests: assert `conversation` entries, `thinking_buffer`, `in_flight` state
2. JSON Patch tests: fold event → verify patch operations are correct
3. Delta bypass tests: `thinking`/`stream_delta` produce delta messages, not patches
4. Snapshot round-trip: fold events → snapshot → verify frontend can read it directly
5. Reconnect test: client with stale version gets fresh snapshot
6. **Delete `events_since()` tests:** `test_projections.py` has tests that call `store.events_since()` directly (currently lines ~360–373). These must be deleted, not updated — the method no longer exists. Replace with tests that verify the snapshot contains the correct materialized state after N events.

### Phase 4: Cleanup & docs

1. Remove dead frontend code: `applyEvent`, `applySnapshot`, `mapProjectionToStore`, `transformAgent`, `transformArtifact`, `ActivityEntry` type, buffer flush helpers, KNOWN_EVENTS
2. Remove `events_since()` from `ProjectionStore`
3. Update `docs/projections.md`:
   - Replace `activity_log` with `conversation` model
   - Document JSON Patch protocol
   - Document delta bypass for streaming buffers
   - Update fold rules table
4. Update `docs/architecture.md`:
   - Add invariant: "The fold runs only in Python. The frontend applies server-computed patches. It has no business logic."
5. Code comments on `ProjectionStore.push_event()` explaining the patch computation flow

---

## Risks

**JSON Patch array diffing:** `make_patch` uses positional indices for arrays. Conversation is append-only (entries are never reordered or removed), so patches are clean `add` operations at the end. The one mutation is `tool_completed` setting `in_flight=False` on an existing entry, which produces a targeted `replace` at `/conversation/N/in_flight`.

**Patch computation cost:** `make_patch` diffs two dicts. At 50MB state, this could be expensive. Mitigation: most events change a small part of state; the diff is proportional to what changed, not total state. For the dominant case (thinking delta), the diff is bypassed entirely.

**Library trust:** `jsonpatch` (Python, 10+ years, well-maintained) and `fast-json-patch` (JavaScript, RFC 6902 compliant, widely used). Both are mature.

**Snapshot size:** At 50MB, the initial snapshot takes ~1 second on localhost. This is acceptable for a local tool. If it becomes a problem, the snapshot can be gzip-compressed (SSE supports `Content-Encoding: gzip`).

---

## Documentation Updates

These changes require corresponding updates to existing docs. Do not defer — out-of-date docs create invisible knowledge debt.

### `docs/projections.md`

1. **Projection model:** Replace `activity_log: list[dict]` with `conversation: list[ConversationEntry]` and `thinking_buffer: str`. Add the full `ConversationEntry` union definition with all 10 entry types.
2. **SSE protocol section:** Replace the current "snapshot + raw events" description with the new three-message protocol (`snapshot`, `patch`, `delta`). Include the connection lifecycle diagram from this plan.
3. **Fold rules table:** Rewrite the activity section — replace "append raw event to activity_log" with the actual fold rules (buffer accumulation, flush triggers, in-flight tracking, agent filtering, koan MCP filtering).
4. **"Why catch-up uses snapshots":** Document the bandwidth analysis: thinking delta patches at 200KB/s vs 600B/s for raw deltas. Document the memory cost of storing 500K patches. This decision must be visible, not inferred.
5. **Event types:** Add `scout_queued` and the 6 typed tool events (`tool_read` through `tool_ls`) which are currently missing.
6. **`AgentProjection`:** Add `status`, `error`, `last_tool`, `label` fields.
7. **Remove:** The "Why activity_log stores raw events" section — that rationale is obsolete.

### `docs/architecture.md`

Add a principle to the projection invariant section:

> **The fold runs only in Python.** The frontend applies server-computed JSON Patches mechanically. It has no fold logic, no event interpretation, and no business rules. When the frontend's view of state differs from the backend's, the bug is in the fold or the patch computation — not in the frontend.

This replaces any "symmetric fold invariant" language, which implied two folds that needed to stay in sync.

### `koan/projections.py`

Add module-level docstring:
```
ProjectionStore maintains:
  - events: append-only audit log of all VersionedEvents
  - projection: materialized view produced by fold() — the source of truth
  - prev_state: to_wire() of the previous projection, used for JSON Patch computation

push_event() folds the event, computes a JSON Patch between prev_state and
the new to_wire() output, and broadcasts either a patch or a delta message.
All wire output is camelCase via KoanBaseModel.to_wire() (alias_generator).
The fold is the only place where business logic runs. The frontend applies
patches mechanically with no field renaming.
```

### `frontend/src/sse/connect.ts`

After the change, the file should have a comment explaining:
```
State sync protocol:
  snapshot  → replace storeState + spread into Zustand
  patch     → apply RFC 6902 patch to storeState + spread into Zustand
  delta     → append string delta to thinkingBuffer or streamBuffer

Server emits camelCase JSON (via Pydantic alias_generator). No field
renaming needed — wire keys match store keys. storeState is a plain JS
object for fast-json-patch; Zustand state is updated by spreading it.
The frontend has no fold logic — all business rules live in the Python fold.
```

### `AGENTS.md` — no changes required

The six core invariants are unchanged. The new architecture is a refinement of how Invariant 5 (projections) is implemented, not a change to the invariant itself.

---

## Migration

**Breaking change.** The SSE protocol changes from per-event-type messages to `snapshot`/`patch`/`delta`. Old clients cannot connect to new servers (they'd receive unknown event types). Old servers cannot serve new clients (missing `patch` event).

**No on-disk migration.** All state is in-memory. Server restart already forces a full reload.

**Deployment:** Single-user local tool. The user runs `pip install --upgrade koan` and restarts. No coordinated rollout needed.
