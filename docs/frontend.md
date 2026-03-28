# Frontend

React 19 + Zustand 5 + Vite 6 SPA. Python serves the built bundle as static
files — no Node.js in production.

> Parent doc: [architecture.md](./architecture.md)

---

## Directory Layout

```
frontend/                   # source tree (alongside koan/ Python package)
├── package.json
├── tsconfig.json
├── vite.config.ts          # proxies /api/*, /events, /mcp/* to Python in dev
├── index.html              # Vite entry point
├── src/
│   ├── main.tsx            # mounts <App /> into #root; imports global CSS
│   ├── App.tsx             # top-level layout; owns SSE connection lifecycle
│   ├── store/
│   │   ├── index.ts        # single Zustand store (the app-db equivalent)
│   │   └── selectors.ts    # derived state computed from store slices
│   ├── sse/
│   │   └── connect.ts      # EventSource wrapper: event dispatch + store writes
│   ├── api/
│   │   └── client.ts       # typed fetch wrappers for POST/PUT endpoints
│   ├── components/         # one file per UI component (see Component Mapping)
│   ├── hooks/
│   │   ├── useElapsed.ts   # replaces manual setInterval + DOM attribute scanning
│   │   └── useAutoScroll.ts
│   └── styles/
│       ├── variables.css   # CSS custom properties (ported verbatim)
│       ├── layout.css
│       └── components.css  # components.css + animations.css merged
└── dist/                   # Vite build output (gitignored)

koan/web/static/app/        # Vite build target (committed build artifacts)
```

---

## Dev vs Production

**Development:** Vite dev server proxies all backend traffic.

```
vite (:5173)  →  /api/*, /events, /mcp/*  →  python (:8000)
```

SSE requires buffering disabled in the proxy — `vite.config.ts` sets
`x-accel-buffering: no` on the `/events` proxy response. Without this, SSE
events arrive in batches rather than incrementally.

**Production:** `uv run koan` only. Python serves the built bundle.

```
python (:8000)  →  /static/app/*          →  frontend/dist/ (Vite build)
                →  /api/*, /events, /mcp/* →  existing routes (unchanged)
                →  /* (catch-all)          →  index.html (SPA fallback)
```

Build command: `cd frontend && npm run build`  
Output: `koan/web/static/app/` (matches `base: '/static/app/'` in `vite.config.ts`)

**Starlette route order** in `create_app()` is significant — first match wins:

```
/mcp            → MCP endpoint
/api/*          → API handlers
/events         → SSE stream
/static/app     → StaticFiles (frontend/dist/)
/static         → other static assets
/{path:path}    → spa_fallback (index.html) — MUST be last
```

---

## State Model

Single Zustand store mirrors backend `AppState`. All live state enters through
the SSE bridge — nothing else writes to the store from outside the component
tree.

Key slices:

| Slice | Type | Source SSE event |
|---|---|---|
| `connected` | `boolean` | EventSource open/error |
| `runStarted` | `boolean` | derived from first `phase` event |
| `phase` / `donePhases` | `string` / `string[]` | `phase` |
| `primaryAgent` | `AgentInfo \| null` | `subagent`, `subagent-idle` |
| `scouts` | `Record<string, AgentInfo>` | `agents` (full replace) |
| `activityLog` | `ActivityEntry[]` | `logs` (append-only) |
| `streamBuffer` | `string` | `token-delta` / `token-clear` |
| `activeInteraction` | `Interaction \| null` | `interaction` |
| `artifacts` | `ArtifactFile[]` | `artifacts` |
| `completion` | `CompletionInfo \| null` | `pipeline-end` |
| `notifications` | `NotificationEntry[]` | `notification` |

`runStarted` gates top-level view (landing vs live). No router library — a
conditional render covers the binary choice.

---

## SSE Bridge

`connectSSE(store)` in `sse/connect.ts` opens an `EventSource('/events')` and
wires every event type to a store action. Returns the `EventSource`; `App.tsx`
owns the reconnect lifecycle (exponential backoff, capped at 5 s).

**snake_case → camelCase mapping** happens at the bridge boundary for all agent
payloads (`agent_id` → `agentId`, `started_at_ms` → `startedAt`, etc.).

**`phase` event side effect:** `setPhase()` also sets `runStarted = true` and
derives `donePhases`. This ensures a mid-run page reload (which replays the
buffered `phase` event) restores the live view without a full reload.

Stateful events (`phase`, `subagent`, `agents`, `artifacts`, `intake-progress`,
`pipeline-end`) are cached server-side and replayed to reconnecting clients.

---

## Backend Contract

`push_sse()` emits raw JSON — no `html` or `target` fields. `_render_fragment()`
and all Jinja2 templates are deleted. Three builder functions produce the
JSON payloads:

| Function | Event | Notes |
|---|---|---|
| `_build_subagent_json(app_state)` | `subagent` | Returns `{"agent_id": None}` when idle |
| `_build_agents_json(app_state)` | `agents` | Scout list; full replace on each event |
| `_build_artifacts_json(app_state)` | `artifacts` | Flat list; client groups into tree |

All time values are UTC epoch milliseconds (`started_at_ms`). All token counts
are raw integers. Formatting is done client-side (`useElapsed`, `formatTokens`).

`app_state.phase` assignment — previously a side effect inside
`_render_fragment()` — is preserved in `push_sse()` for the `phase` event
branch.

Settings endpoints (`/api/settings/body`, `/api/settings/profile-form`,
`/api/settings/installation-form`) return JSON. `SettingsOverlay.tsx` owns
form state and cascade dropdown logic.

---

## Component Mapping

| Jinja2 template | React component | Primary store subscription |
|---|---|---|
| `live.html` | `App.tsx` | `runStarted` |
| `landing.html` | `LandingPage.tsx` | `runStarted` (negated) |
| `status_sidebar.html` | `StatusSidebar.tsx` | `primaryAgent`, `phase`, `intakeProgress` |
| `monitor.html` | `AgentMonitor.tsx` | `scouts` |
| `artifacts_sidebar.html` | `ArtifactsSidebar.tsx` | `artifacts` |
| `interaction_ask.html` | `AskWizard.tsx` | `activeInteraction` |
| `interaction_workflow.html` | `WorkflowDecision.tsx` | `activeInteraction` |
| `interaction_artifact_review.html` | `ArtifactReview.tsx` | `activeInteraction` |
| `completion.html` | `Completion.tsx` | `completion` |
| `settings_body.html` | `SettingsOverlay.tsx` | `settingsOpen` + local state |
| Toast JS in `koan.js` | `Notification.tsx` | `notifications` |

---

## Known Gaps (v1)

**`story` events** — emitted during execution phase with story lifecycle status.
Not implemented in v1: execution phase shows only primary agent status and
activity feed. Add a `stories` store slice and `StoryProgress` component when
designing the execution phase UI.

**`frozen-logs` events** — snapshot of activity log before orchestrator spawn.
Ignored in v1; the activity feed is append-only. Add a log boundary marker in
a follow-up if needed.

**`intake-progress` events** — the SSE bridge and `StatusSidebar` are wired to
display intake sub-phase, confidence, and summary. However, no Python code
currently emits `push_sse(app_state, "intake-progress", ...)`. The `push_sse()`
handler and `STATEFUL_EVENTS` entry exist but are unreachable. When adding the
emission call, use camelCase field names (`subPhase`, not `sub_phase`) since the
bridge passes through without renaming.

---

## Dependencies

```json
{
  "dependencies":    { "react": "^19", "react-dom": "^19", "zustand": "^5" },
  "devDependencies": { "typescript": "^5.7", "vite": "^6", "@vitejs/plugin-react": "^4" }
}
```

No router (two views, conditional render). No fetch library (typed `fetch`
wrappers in `api/client.ts`). No CSS framework (existing design tokens port
directly via CSS custom properties).
