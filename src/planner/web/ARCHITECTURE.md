# Web UI Architecture

Single-page dashboard served by `server.ts`. Pushes state via SSE; receives
user input via POST. Built with Preact + Zustand — see
`plans/2026-03-16-preact-zustand-rewrite.md` for the full decision record.

---

## Directory layout

```
server.ts          HTTP server, SSE push, WebServerHandle API
server-types.ts    Shared TypeScript types
html/index.html    Shell — <div id="app"> + module script, no static skeleton
css/               Four stylesheets (variables, layout, components, animations)
dist/app.js        Compiled bundle — generated, not committed
js/
  app.jsx          Entry: render(<App>), connectSSE(), heartbeat interval
  store.js         Zustand store (single source of truth)
  sse.js           SSE connection + store updates
  lib/utils.js     formatTokens, formatElapsed, shortenModel
  lib/api.js       submitAnswers, submitReview (fetch wrappers)
  components/      Preact component tree (see §Component tree below)
```

---

## Build pipeline

esbuild compiles `js/app.jsx` and all imports into `dist/app.js` (single ESM
bundle, ~44KB raw / ~16KB gzip).

**The alias flags are mandatory.** zustand v4 imports from `react` internally.
Without aliasing, esbuild bundles the full React 19 runtime alongside Preact —
two competing VDOM reconcilers that cannot share a hook dispatcher. The aliases
redirect those imports to `preact/compat`:

```
--alias:react=preact/compat --alias:react-dom=preact/compat
```

These appear in both the npm script (`build:web`) and in the `esbuild.build()`
call inside `ensureBundle()` in `server.ts`. If you add them to one, add them
to both.

**On-demand build:** `ensureBundle()` in `server.ts` runs at the top of
`startWebServer()`. It stats `dist/app.js` against the newest file in `js/`
and rebuilds only when stale. Adds ~100ms on first start; skips on subsequent
starts. No manual build step is needed during development.

**CI/test path:** `npm run build` runs `build:web` then `tsc`. The tsc step
does not process JSX; it type-checks the TypeScript source only.

**zustand version:** Pinned to v4 (`^4.5.7`). zustand v5 moved its default
export to `zustand/react`, which imports React at module level and breaks
the esbuild bundle even with the alias.

---

## Data flow

```
server.ts  ──SSE──►  sse.js  ──setState──►  Zustand store  ──selector──►  components
                                                                  │
user action  ◄──fetch──  lib/api.js  ◄──────────────────────────┘
```

1. `server.ts` pushes SSE events on a 50ms polling tick.
2. `sse.js` registers one `addEventListener` per event type. Each handler
   calls `useStore.setState()` — the static method, callable outside
   component context.
3. Components subscribe via `useStore(s => s.slice)`. Zustand shallow-merges
   `setState` calls and notifies only subscribers whose selected slice changed.
4. User actions (form submit, heartbeat) call `lib/api.js` fetch wrappers
   which POST to `/api/answer`, `/api/review`, or `/api/heartbeat`.

`pendingInput` is cleared by the server: a phase transition out of `intake`
clears it in the `phase` handler; `ask-cancelled` / `review-cancelled` clear
it by request ID. `intakeProgress` is cleared when the phase transitions away
from intake or when the pipeline ends.

---

## Component tree

```
App
├── Header
│   ├── PillStrip        reads phase for active/done pill state
│   └── ⚙ settings btn
│
├── (isInteractive) main.main-panel
│   └── PhaseContent     dispatch hub (see below)
│
├── (live) div.live-layout          ← sidebar + feed row
│   ├── StatusSidebar               agent identity + phase status + summary
│   └── div.live-main
│       └── main.main-panel
│           └── ActivityFeed        reads logs, currentToolCallId
│
├── AgentMonitor         reads agents (hides when none active)
└── Notifications        reads notifications; auto-dismisses via useEffect
```

**App layout modes:**

`isInteractive = !phase || pendingInput || showSettings || phase === 'completed'`

- **Interactive mode** — `PhaseContent` fills the scrollable area. Used for forms,
  loading screen, settings overlay, and completion.
- **Live mode** — `StatusSidebar` sits in the left column (`clamp(240px, 20vw, 300px)`),
  `ActivityFeed` fills the right column. The parent `.app` container handles
  centering — no per-mode centering needed.

**PhaseContent dispatch order:**

1. `showSettings` → `<ModelConfig isGate={false}>`
2. `pending.type === 'model-config'` → `<ModelConfig isGate={true}>`
3. `!phase` → `<Loading topic>`
4. `pending.type === 'ask'` → `<QuestionForm key={requestId}>`
5. `pending.type === 'review'` → `<ReviewForm key={requestId}>`
6. `phase === 'completed'` → `<Completion>`
7. default → `null` (live mode renders the ActivityFeed instead)

`key={requestId}` on forms forces a full remount when a new request arrives,
resetting local selection state without any explicit cleanup.

---

## StatusSidebar

The `StatusSidebar` renders phase-specific context in the left column during
live mode. It reads four store slices: `phase` (visibility gate and content
dispatch), `subagent` (agent identity section), `intakeProgress`
(intake-specific data), and `stories` (decomposition and execution progress).

**Visibility:** The sidebar renders whenever `phase` is non-null — not gated on
`subagent`. This means phase status (story progress, etc.) remains visible
during brief gaps between subagent spawns. The agent identity section is
omitted when `subagent` is null.

**Agent identity section** (top, when `subagent` is non-null):
- Role (uppercase, blue, mono) + shortened model name (muted) on one line
- Step label from `subagent.stepName` or `Step N/M` on the next line
- Token counts (↑sent ↓recv) + elapsed timer on the third line
- Elapsed time is computed inline via `useState` + `useEffect` 1-second
  interval from `subagent.startedAt`, using `formatElapsed` from `lib/utils.js`

**Phase-specific sections** (middle):

- **intake** + `intakeProgress` → `IntakeStatus`: confidence meter (5 segments),
  iteration dots (4 rounds), sub-phase label, summary text per sub-phase
- **brief** → `BriefStatus`: static "Drafting epic brief…" label
- **decomposition** → `DecomposeStatus`: story count from `stories` slice
- **executing** → `ExecuteStatus`: `done`/total complete count plus active count
  (stories in `selected`, `planning`, `executing`, or `verifying` states)
- **fallback** → `GenericStatus`: phase label + "Phase in progress…"

**Summary section** (bottom, below divider): static contextual message per phase.

---

## intake-progress SSE event

`IntakeProgressEvent { subPhase, intakeDone, confidence, iteration }` is pushed
from the server's 50ms agent-polling tick whenever the intake agent's projection
changes. The full pipeline:

```
LLM calls koan_set_confidence
  → ctx.intakeConfidence set
  → confidence_change appended to events.jsonl
  → fold() updates state.json projection
  → server polls state.json (50ms) → detects change
  → pushes intake-progress SSE event
  → sse.js: set({ intakeProgress: d })
  → StatusSidebar re-renders with new confidence/iteration
```

The event is replayed in `replayState()` on SSE reconnect so the sidebar
recovers its state after a network drop.

---

## Server-side changes

**`ensureBundle()`** — async function before `startWebServer()` body. Uses
esbuild JS API via dynamic `await import("esbuild")`. `STATIC_ASSETS` is
constructed inside `startWebServer()` after this call completes.

---

## Conventions

| Convention | Rule |
|---|---|
| JSX attribute | `class`, not `className` (Preact uses HTML attribute names) |
| Hook imports | `import { useState, useEffect } from 'preact/hooks'` |
| Render import | `import { render } from 'preact'` (not `preact/compat`) |
| External setState | `useStore.setState(...)` — static method, works outside components |
| Fragment syntax | `<>…</>` — works because build uses `--jsx=automatic` |
| Zustand merge | `setState` merges shallowly; always replace the full slice, never mutate nested objects |
