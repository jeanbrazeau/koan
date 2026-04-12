# Koan

Koan is a workflow system for coding tasks. A single Python process hosts a web
dashboard and MCP tool endpoint; the user selects a workflow type, describes a
task, and the system runs a sequence of LLM subagents to plan and implement it.

## Setup

```bash
uv sync
uv run koan
```

## How it works

At startup, the user selects a workflow type and describes the task. Koan spawns
a long-lived orchestrator LLM process that runs the entire workflow via MCP tool
calls. At each phase boundary, the orchestrator pauses, summarizes progress, and
asks the user where to go next.

### Plan workflow

```
intake       — explore codebase, ask clarifying questions, write landscape.md
plan-spec    — read landscape.md, write plan.md (technical implementation plan)
plan-review  — read landscape.md + plan.md, evaluate quality, report findings
execute      — spawn executor agent with plan.md; implements the changes
```

### Milestones workflow

Stub — runs intake only, then reports the workflow is not yet fully implemented.

---

A single Python process (`koan/driver.py`) runs a Starlette HTTP server that
hosts both the web dashboard and an MCP tool endpoint. Subagents are CLI
processes (`claude`, `codex`, or `gemini`) that connect to
`http://localhost:{port}/mcp?agent_id={id}` to receive step guidance and call
koan tools. The driver reads JSON state and exit codes; it never parses LLM
output.

## Roles

| Role | What it does |
|------|-------------|
| **orchestrator** | Runs the entire workflow in one long-lived process. Calls `koan_set_phase` to advance phases. |
| **scout** | Narrow codebase investigator. Spawned in parallel via `koan_request_scouts`. Writes `findings.md`. |
| **executor** | Reads artifacts and instructions from `task.json`, implements code changes in one pass. |

## Web Dashboard

Koan serves a local web dashboard at `http://localhost:{port}` during pipeline
execution. The dashboard provides:

- **Activity feed** -- real-time tool calls, scout dispatches, thinking traces
- **Agent monitor** -- status, token counts, and recent actions for each
  running subagent
- **Artifacts panel** -- markdown files written during the run (landscape.md, plan.md)
- **User interaction** -- question forms (clarifications), chat for phase-boundary direction

The dashboard uses Server-Sent Events for real-time updates. SSE events are
pushed directly from in-process state transitions and tool handlers.

## Key Concepts

**Step-first workflow.** Every subagent's first action is calling
`koan_complete_step`. This forces a tool call before any text output. Task
instructions are delivered as the return value of that first call.

**Directory-as-contract.** Each subagent gets a directory with `task.json`
(input), `state.json` (live projection), and `events.jsonl` (audit log). The
spawn command carries the directory path and the MCP endpoint URL.

**Default-deny permissions.** Every tool call passes through a permission
fence. Roles cannot use tools outside their scope. Planning roles can only
write inside the run directory.

**Driver determinism.** The driver reads JSON and exit codes, validates phase
transitions against the active workflow, and spawns subagents. It never parses
markdown or adapts to LLM behavior. Routing decisions are deterministic.

**HTTP MCP.** Subagents connect to the driver's MCP endpoint at
`/mcp?agent_id={id}`. Tool calls arrive as HTTP requests; the driver looks up
the agent's state by `agent_id` in an in-process registry and handles the call
directly. No separate MCP server processes, no file-based IPC polling.

**Workflow-based phase transitions.** Phase transitions are validated against
the active workflow's `available_phases`. Any phase in the workflow is reachable
from any other. Suggested transitions guide the orchestrator's boundary response
but do not restrict the user.

## Configuration

Model tiers and scout concurrency are configured via the web UI at pipeline
start, then saved to `~/.koan/config.json`:

```json
{
  "agentInstallations": [
    { "alias": "claude-sonnet", "runnerType": "claude", "binary": "claude", "extraArgs": [] }
  ],
  "profiles": [
    {
      "name": "balanced",
      "tiers": {
        "strong":   { "runnerType": "claude", "model": "claude-sonnet-4-5", "thinking": "disabled" },
        "standard": { "runnerType": "claude", "model": "claude-sonnet-4-5", "thinking": "disabled" },
        "cheap":    { "runnerType": "claude", "model": "claude-haiku-4-5",  "thinking": "disabled" }
      }
    }
  ],
  "activeProfile": "balanced",
  "scoutConcurrency": 8
}
```

Roles map to tiers: orchestrator → strong, executor → standard, scout → cheap.

## Architecture Documentation

- **[docs/architecture.md](./docs/architecture.md)** -- core invariants,
  design principles, workflow system, pitfalls
- **[docs/subagents.md](./docs/subagents.md)** -- spawn lifecycle, step-first
  workflow, permissions, model tiers
- **[docs/ipc.md](./docs/ipc.md)** -- HTTP MCP inter-process communication,
  blocking tool calls
- **[docs/state.md](./docs/state.md)** -- run state, driver state, routing
- **[docs/intake-loop.md](./docs/intake-loop.md)** -- two-step intake design,
  prompt engineering principles
- **[docs/projections.md](./docs/projections.md)** -- versioned event log,
  fold function, SSE protocol
- **[docs/token-streaming.md](./docs/token-streaming.md)** -- runner stdout
  parsing, SSE delta path
