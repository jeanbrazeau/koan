# Plan: Subagent Ask Questions via File-Based IPC

## Context

### Problem

Subagents run as headless `pi -p` child processes with no UI access (`ctx.hasUI = false`). When a subagent needs user input during planning — choosing between architectural alternatives, clarifying scope — it has no mechanism to pause, ask the user, and resume with the answer.

### Design Decisions

**Single `ipc.json` file per subagent directory.** Both request and response live in one file with `request` and `response` keys. Temporal ownership is safe: the subagent creates the file and then blocks (only reads during the wait), so the parent is the sole writer during the response window. A two-file model (request.json + response.json) provides structural ownership at the cost of cleanup complexity and an extra file per interaction. The single-file model is simpler and sufficient because the subagent's blocking poll guarantees no concurrent writes.

**Tool schema mirrors pi-ask-tool-extension exactly.** The `koan_ask_question` tool accepts the same `{ questions: [{ id, question, options, multi?, recommended? }] }` schema as the existing `ask` tool. LLMs trained on the ask tool schema produce correct calls without schema-specific prompt engineering.

**Ask UI code copied from pi-ask-tool-extension, not imported.** The pi-ask-tool-extension package is globally installed as a pi extension — it is not in koan's `node_modules` and cannot be imported. The four source files (~1133 lines) are copied into `src/planner/ui/ask/`. All external dependencies (`@mariozechner/pi-coding-agent`, `@mariozechner/pi-tui`) are already available in koan's node_modules.

**Permission gating via existing PHASE_PERMISSIONS, not conditional registration.** Pi snapshots all tools at init time (`_buildRuntime()`). Tools cannot be added or removed after init. The existing default-deny `PHASE_PERMISSIONS` map in `permissions.ts` controls runtime access. Adding `koan_ask_question` to the three work-phase Sets (`plan-design`, `plan-code`, `plan-docs`) grants access to subagents in those phases. In parent mode, no phase is active, so the tool is blocked automatically.

**SubagentRef pattern mirrors PlanRef.** Tool registration happens at init when the subagent directory is unknown. A mutable `SubagentRef = { dir: string | null }` created at init is populated at `before_agent_start` when CLI flags are available. The tool reads `subagentRef.dir` at execute time. This matches the established `PlanRef` indirection pattern in `dispatch.ts`.

**Non-error returns for cancellation and abort.** When the user cancels (Escape) or the signal aborts, the tool returns a descriptive non-error message ("The user declined to answer. Proceed with your best judgment."). Error returns cause LLMs to halt or retry; non-error returns guide the LLM to continue productively.

**Parent detects requests inside existing setInterval poll loops.** The parent's 2-second poll callback in `session.ts` already reads `state.json` for widget updates. Adding an `ipc.json` read to the same callback avoids a separate polling mechanism. A `pendingRequestId` guard variable prevents re-entrant handling — JavaScript's `setInterval` fires regardless of whether the previous async callback completed, so without the guard, every 2-second tick during the user's think-time would re-detect the same request.

### Constraints

- Pi snapshots tools at init; all tools must be registered unconditionally before `_buildRuntime()`.
- Subagents run in `-p` mode (print mode) with stdin ignored and stdout/stderr piped to log files — no interactive I/O.
- The parent orchestrator has `ctx.ui` access (confirmed: `session.ts` creates `WidgetController` from `ctx.ui`).
- Atomic file writes use the established tmp+rename pattern (`writeFile(tmp) → rename(tmp, target)`).
- The EventLog heartbeat (10-second `setInterval`) continues during the subagent's blocking poll because `await sleep(500)` yields to the Node.js event loop. `state.json` keeps updating, so the parent sees the subagent as alive.

### Out of Scope (Deferred)

- Timeout for parent crash detection — the user is at the terminal and will notice; adding a configurable timeout is a follow-up.
- Process liveness check before showing ask UI — low severity edge case (subagent exits between writing request and parent detecting it).
- Multi-subagent concurrent questions — work phases run sequentially; QR phases are excluded from permissions.

## Implementation

### ipc.json Schema

```typescript
// Types live in src/planner/lib/ipc.ts.
// The schema is general-purpose: `type` discriminant supports future request
// types beyond "ask-question" without envelope changes.

interface IpcFile {
  request: IpcRequest;
  response: IpcResponse | null; // null while awaiting parent response
}

interface IpcRequest {
  id: string;             // crypto.randomUUID() — correlates request to response
  type: "ask-question";   // discriminant for routing; extensible to future types
  createdAt: string;      // ISO 8601 timestamp
  payload: AskQuestionPayload;
}

interface AskQuestionPayload {
  questions: Array<{
    id: string;
    question: string;
    options: Array<{ label: string }>;
    multi?: boolean;
    recommended?: number;  // 0-indexed
  }>;
}

interface IpcResponse {
  id: string;             // must match request.id
  respondedAt: string;    // ISO 8601 timestamp
  cancelled: boolean;     // true when user presses Escape
  payload: AskAnswerPayload | null; // null when cancelled
}

interface AskAnswerPayload {
  answers: Array<{
    id: string;             // matches question id
    selectedOptions: string[];
    customInput?: string;   // populated when user selects "Other"
  }>;
}
```

### NEW: `src/planner/lib/ipc.ts` — IPC File I/O Primitives

Atomic read/write/delete helpers for `ipc.json`. Both the subagent tool and the parent session use these functions. The atomic write pattern (tmp file → rename) matches `EventLog.writeState()` in `audit.ts`.

**Functions:**
- `writeIpcFile(dir, data)` — atomic write via `.ipc.tmp.json` → `ipc.json` rename
- `readIpcFile(dir)` → `IpcFile | null` — returns null on missing file or parse error (treat parse error as "not ready" to handle partial writes on non-POSIX systems)
- `ipcFileExists(dir)` → `boolean` — fast `fs.access` check without parsing
- `deleteIpcFile(dir)` — removes `ipc.json` and any lingering `.ipc.tmp.json`; swallows ENOENT
- `createAskRequest(payload)` → `IpcFile` — creates file structure with `crypto.randomUUID()` id and `response: null`
- `createAskResponse(requestId, payload)` → `IpcResponse` — response with `cancelled: false`
- `createCancelledResponse(requestId)` → `IpcResponse` — response with `cancelled: true`, `payload: null`

All types are exported for use by both subagent-side (`tools/ask.ts`) and parent-side (`session.ts`).

### NEW: `src/planner/tools/ask.ts` — koan_ask_question Tool

Registers `koan_ask_question` with the pi extension API. The tool schema uses TypeBox definitions identical to pi-ask-tool-extension. Imports `SubagentRef` from `../lib/dispatch.js` (not defined here — it lives in `dispatch.ts` alongside `PlanRef`).

**Tool execute flow:**

The entire poll loop is wrapped in a single `try/finally` that calls `deleteIpcFile(dir)`. This guarantees cleanup on all exit paths — success, cancellation, abort, and file disappearance — without requiring per-path deletion logic.

1. Guard: if `subagentRef.dir` is null, return error (not in subagent context).
2. Guard: if `ipc.json` already exists, return error (one request at a time).
3. Create `IpcFile` via `createAskRequest(payload)`, write atomically.
4. Register `signal.addEventListener("abort", onAbort, { once: true })` for instant abort response.
5. Enter poll loop inside `try`: `while (!aborted) { await sleep(500); check signal; read ipc.json; if response !== null && response.id matches: break }`.
6. On response with `cancelled: false`: build `QuestionResult[]`, format via `buildSessionContent()`, return as tool result. (`finally` handles cleanup.)
7. On response with `cancelled: true`: return "The user declined to answer." (`finally` handles cleanup.)
8. On abort: return "The question was aborted." (`finally` handles cleanup.)
9. On file disappearing mid-poll (deleted externally): return "The question was cancelled." (`finally` handles cleanup, swallows ENOENT.)

**Result formatting** mirrors pi-ask-tool-extension's `buildAskSessionContent()`:
```
User answers:
auth: JWT

Answer context:
Question 1 (auth)
Prompt: Which authentication model?
Options:
  1. JWT
  2. Session-based
Response:
  Selected: JWT
```

### NEW: `src/planner/ui/ask/` — Copied Ask UI Components (4 files)

Copy these files from `pi-ask-tool-extension/src/` (at `/Users/lmergen/.npm-global/lib/node_modules/pi-ask-tool-extension/src/`):

1. **`ask-logic.ts`** (~98 lines) — `AskQuestion`, `AskOption`, `AskSelection` types; `OTHER_OPTION` constant; `buildSingleSelectionResult()`, `buildMultiSelectionResult()`, `appendRecommendedTagToOptionLabels()`.
2. **`ask-inline-note.ts`** (~65 lines) — Inline note rendering helpers. Uses `wrapTextWithAnsi` from `@mariozechner/pi-tui`.
3. **`ask-inline-ui.ts`** (~221 lines) — Single-question single-select UI. Renders cursor navigation (↑↓), inline note editing (Tab), submit (Enter) via `ui.custom()`.
4. **`ask-tabs-ui.ts`** (~512 lines) — Multi-question/multi-select tabbed UI. Tab bar (← Q1 Q2 ... ✓ Submit →), per-question option lists, Submit review tab via `ui.custom()`.

**Import path requirements:**
- Relative import extensions use `.js` suffix: `"./ask-logic"` → `"./ask-logic.js"` (Node16 module resolution requires `.js` extensions in TypeScript source).
- Same for `"./ask-inline-note"` → `"./ask-inline-note.js"`.
- External dependencies (`@mariozechner/pi-coding-agent`, `@mariozechner/pi-tui`) resolve from koan's node_modules.

### MODIFY: `src/planner/lib/dispatch.ts` — Add SubagentRef

`SubagentRef` and `createSubagentRef()` live alongside `PlanRef` and `createPlanRef()` — both are mutable-ref infrastructure primitives that decouple static tool registration from runtime directory resolution.

```diff
+// Decouples tool registration (init-time) from subagent directory
+// resolution (runtime, after flags available). Same indirection
+// pattern as PlanRef.
+export interface SubagentRef {
+  dir: string | null;
+}
+
+export function createSubagentRef(): SubagentRef {
+  return { dir: null };
+}
```

### MODIFY: `src/planner/tools/index.ts` — Thread SubagentRef

```diff
+import { registerAskTools } from "./ask.js";
+import type { SubagentRef } from "../lib/dispatch.js";
+export type { SubagentRef } from "../lib/dispatch.js";
+export { createSubagentRef } from "../lib/dispatch.js";

 export function registerAllTools(
   pi: ExtensionAPI,
   planRef: PlanRef,
   dispatch: WorkflowDispatch,
+  subagentRef: SubagentRef,
 ): void {
   registerWorkflowTools(pi, dispatch);
   registerPlanGetterTools(pi, planRef);
   registerPlanSetterTools(pi, planRef);
   registerPlanDesignEntityTools(pi, planRef);
   registerPlanCodeEntityTools(pi, planRef);
   registerPlanStructureEntityTools(pi, planRef);
   registerQRTools(pi, planRef);
+  registerAskTools(pi, subagentRef);
 }
```

Note: `SubagentRef` is defined in `lib/dispatch.ts` (alongside `PlanRef`), not in `tools/ask.ts`. `tools/index.ts` re-exports it for convenience, matching the existing re-export pattern for `PlanRef`.

### MODIFY: `extensions/koan.ts` — Create and Wire SubagentRef

```diff
-import { registerAllTools, createDispatch, createPlanRef } from "../src/planner/tools/index.js";
+import { registerAllTools, createDispatch, createPlanRef, createSubagentRef } from "../src/planner/tools/index.js";

   const dispatch = createDispatch();
   const planRef = createPlanRef();
+  const subagentRef = createSubagentRef();

-  registerAllTools(pi, planRef, dispatch);
+  registerAllTools(pi, planRef, dispatch, subagentRef);

   // In before_agent_start, inside `if (config.subagentDir)`:
+      subagentRef.dir = config.subagentDir;
```

The `subagentRef.dir = config.subagentDir` assignment goes immediately after the existing `eventLog = new EventLog(...)` line (L88), inside the same `if (config.subagentDir)` block. In parent mode, `subagentRef.dir` remains null, and the tool's execute returns an error.

### MODIFY: `src/planner/lib/permissions.ts` — Grant Access to Work Phases

```diff
     [
       "plan-design",
       new Set([
         "koan_complete_step",
+        "koan_ask_question",
         ...PLAN_GETTER_TOOLS_LIST,
         ...PLAN_SETTER_TOOLS_LIST,
         ...PLAN_DESIGN_ENTITY_TOOLS,
       ]),
     ],
     [
       "plan-code",
       new Set([
         "koan_complete_step",
+        "koan_ask_question",
         ...PLAN_GETTER_TOOLS_LIST,
         ...PLAN_CHANGE_TOOLS_LIST,
         "koan_set_intent",
       ]),
     ],
     [
       "plan-docs",
       new Set([
         "koan_complete_step",
+        "koan_ask_question",
         ...PLAN_GETTER_TOOLS_LIST,
         "koan_set_change_doc_diff",
         "koan_set_change_comments",
```

QR phases (`qr-plan-design`, `qr-plan-code`, `qr-plan-docs`) omit `koan_ask_question` — reviewers do not ask questions.

### MODIFY: `src/planner/session.ts` — Parent-Side Request Detection

**A. New imports:**
```typescript
import type { ExtensionUIContext } from "@mariozechner/pi-coding-agent";
import { readIpcFile, writeIpcFile, createAskResponse, createCancelledResponse, type IpcFile } from "./lib/ipc.js";
import { askSingleQuestionWithInlineNote } from "./ui/ask/ask-inline-ui.js";
import { askQuestionsWithTabs } from "./ui/ask/ask-tabs-ui.js";
import type { AskQuestion } from "./ui/ask/ask-logic.js";
```

**B. New `handleAskRequest()` function** (module-level, alongside `runPlanningPhase`):

Receives the parent's `ExtensionUIContext` and the parsed `IpcFile`. Routes to the appropriate ask UI based on question count and multi-select:
- Single question, single-select → `askSingleQuestionWithInlineNote(ui, question)`
- Single question, multi-select → `askQuestionsWithTabs(ui, [question])`
- Multiple questions → `askQuestionsWithTabs(ui, questions)`

Returns an `IpcResponse` (either answered or cancelled). On any exception from the UI layer, returns a cancelled response so the subagent unblocks.

**C. New `pollWithIpcDetection()` helper** (extracts the common poll-with-request-detection pattern):

Both the work poll (~L335) and the fix poll (~L737) share the same request detection logic. A shared helper avoids duplication:

```typescript
import type { LogLine } from "./lib/audit.js";

// Encapsulates the poll-with-request-detection pattern used by both
// the work poll loop and the fix poll loop. Returns a setInterval ID.
function pollWithIpcDetection(
  subagentDir: string,
  widget: WidgetController | null,
  ui: ExtensionUIContext | null,
  stepPrefix: string,
  updateFromProjection: (p: Projection, logs: LogLine[]) => void,
): ReturnType<typeof setInterval> {
  let pendingRequestId: string | null = null;

  return setInterval(async () => {
    // Existing: read projection and update widget
    const [projection, logs] = await Promise.all([
      readProjection(subagentDir),
      readRecentLogs(subagentDir),
    ]);
    if (projection) {
      updateFromProjection(projection, logs);
    }

    // IPC request detection — skip if already handling a request or no UI
    if (pendingRequestId || !ui) return;

    const ipc = await readIpcFile(subagentDir);
    if (!ipc || !ipc.request || ipc.response !== null) return;

    pendingRequestId = ipc.request.id;
    try {
      widget?.update({
        step: `${stepPrefix}: waiting for user input...`,
        activity: ipc.request.payload.questions[0]?.question ?? "",
      });

      const response = await handleAskRequest(ui, ipc);
      const updated: IpcFile = { request: ipc.request, response };
      await writeIpcFile(subagentDir, updated);
    } catch {
      // On error, write cancelled response so subagent unblocks.
      // The inner try-catch guards against I/O failures during error
      // recovery — an unguarded throw here would propagate as an
      // unhandled async rejection in the setInterval callback,
      // crashing the parent process (Node.js ≥15 default behavior).
      try {
        const cancelled = createCancelledResponse(ipc.request.id);
        await writeIpcFile(subagentDir, { request: ipc.request, response: cancelled });
      } catch {
        // I/O failed during error recovery; subagent remains blocked
        // until parent terminates. No further action possible.
      }
    } finally {
      pendingRequestId = null;
    }
  }, 2000);
}
```

**D. Thread `ui` through function signatures:**

- `runPlanningPhase(phase, planDir, cwd, extensionPath, state, log, widget)` → add `ui: ExtensionUIContext | null`
- `runPhaseWithQR(phase, planDir, cwd, extensionPath, state, log, widget)` → add `ui: ExtensionUIContext | null`
- Call site in `plan()`: pass `ctx.hasUI ? ctx.ui : null`

**E. Work poll loop (~L335):**
The work poll uses `pollWithIpcDetection(subagentDir, widget, ui, phase.key, ...)`.

**F. Fix poll loop (~L737):**
The fix poll uses `pollWithIpcDetection(fixDir, widget, ui, \`${phase.key} fix ${fixIndex}/${MAX_FIX_ITERATIONS}\`, ...)`.

### MODIFY: `src/planner/lib/audit.ts` — Log Formatting

Add `koan_ask_question` to the `KOAN_SHAPES` object for audit log display:

```typescript
koan_ask_question: { keys: ["questions"], arrays: ["questions"], highValue: true },
```

## Quality Checklist

- [ ] 01-naming-and-types (design-mode): `SubagentRef` mirrors `PlanRef` naming; `IpcFile`/`IpcRequest`/`IpcResponse` model the domain; `handleAskRequest` describes behavior
- [ ] 02-structure-and-composition (design-mode): `pollWithIpcDetection` extracts shared logic from two poll loops; `handleAskRequest` is single-responsibility; error handling wraps UI calls with cancelled-response fallback
- [ ] 06-module-and-dependencies (design-mode): `lib/ipc.ts` is a pure I/O module with no UI dependencies; `tools/ask.ts` depends on `lib/ipc.ts` and `lib/dispatch.ts` (downward); `session.ts` depends on both `lib/ipc.ts` and `ui/ask/` (same level); no circular deps; `SubagentRef` lives in `lib/dispatch.ts` not in tools layer
- [ ] 07-cross-file-consistency (design-mode): Atomic write pattern matches `EventLog.writeState()`; mutable ref pattern matches `PlanRef`/`WorkflowDispatch` in `lib/dispatch.ts`; permission gating matches existing `PHASE_PERMISSIONS` entries; tool description style matches existing koan tools; error recovery in setInterval callbacks matches `verifyStatsPoll` guarded-catch pattern

## Execution Protocol

```
1. delegate @agent-developer: implement per this plan file
2. delegate @agent-quality-reviewer: verify against plan + ~/.claude/conventions/code-quality/ (code-mode)

When delegating, pass this plan file path. Supplement only with:
- rationale for decisions not captured in plan
- business constraints
- technical prerequisites the agent cannot infer
```
