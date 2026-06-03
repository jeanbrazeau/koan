# PydanticAI Migration -- Status Assessment

**Date:** 2026-06-03
**Source run:** `~/.koan/runs/1780450413-662fc093` (initiative workflow,
"native PydanticAI for all agents")
**Source plan:** `plans/2026-06-03-llm-api.md`

## What this migration is

Migrate koan's entire agent layer off the Claude Agent SDK and the codex/gemini
CLIs onto native PydanticAI (pinned `pydantic-ai-slim==2.0.0b5`). The core shift:
koan owns the ReAct loop **in-process** rather than driving CLI subprocesses over
HTTP MCP. Consequences:

- `koan_yield` is removed -- a terminal-text turn (no tool calls) becomes the
  hand-back-to-user signal.
- koan tools and subagents (executor/scout) run in-process as PydanticAI
  toolsets and `asyncio` tasks instead of over HTTP MCP.
- The built-in tools the SDK provided (read/write/edit/glob/grep/bash, plus
  web search/fetch) are reimplemented natively.
- koan directly owns and manipulates message history -- unlocking prompt
  caching, real usage/cost tracking (`genai-prices`), just-in-time
  AGENTS.md/CLAUDE.md context-file injection, and a seam for later
  interrupts/compaction.
- A new provider+model+settings config schema replaces CLI-binary detection,
  targeting Anthropic, OpenAI, Gemini, and AWS Bedrock.

What stays: the phase/step machine, projections, and (transitionally) the
permission tables. What gets deleted at the end: the SDK agent, CLI runners,
the HTTP MCP endpoint, and the `claude-agent-sdk` / `fastmcp` dependencies.

Decomposition is **Gemini-first** (the only live-testable provider) and ends in
a **hard cutover** -- the old path is not maintained in parallel. `main` is
accepted to be non-shippable between M2 and M9.

## Current state in one line

**The build does not compile.** Milestones 1 through 5a are complete and present
in the working tree (uncommitted); milestone 5b is partially done and left
`koan/web/mcp_endpoint.py` with an `IndentationError` at line 636. Milestones
5c, 6, 7, 8, and 9 have not started.

The run did not crash -- the orchestrator exited cleanly (`exit_code=0`) at the
`plan-spec` phase while planning M5b, then stopped.

## Milestone status

| Milestone | Title                                                      | Status          |
| --------- | ---------------------------------------------------------- | --------------- |
| M1        | Config schema + Gemini provider adapter + v2 pin           | **done**        |
| M2        | In-process loop + agent + StreamEvent translation (Gemini) | **done**        |
| M3        | Full koan toolset + ToolPolicy + toolset composer          | **done**        |
| M4        | Built-in toolset + context-file injection + path-scope     | **done**        |
| M5a       | In-process multi-turn loop (loop spine)                    | **done**        |
| M5b       | koan_yield removal cascade + build repair                  | **in-progress** |
| M5c       | In-process koan_ask_question + koan_memory_propose + tests | pending         |
| M6        | Subagents as in-process asyncio tasks                      | pending         |
| M7        | Provider fan-out (Anthropic/OpenAI/Bedrock) + caching      | pending         |
| M8        | Settings UI rework + profiles                              | pending         |
| M9        | Rip-out (delete SDK, CLI runners, MCP endpoint, deps)      | pending         |

> Numbering note: M5 was re-decomposed into M5a/M5b/M5c after two oversized M5
> runs stalled. This phase's milestone numbers do not track the source plan's
> M0-M6.

## What has been done (M1-M5a)

### M1 -- Config schema + Gemini adapter + v2 pin

- `koan/types.py`: new `ModelSpec`, `ProviderAuth`, `CachingPolicy` dataclasses;
  `ProfileTier` is now `{model: ModelSpec}`.
- `koan/config.py`: `KoanConfig.provider_auth: list[ProviderAuth]` (replaces
  `agent_installations`); camelCase parse/save for `providerAuth` and the
  `ModelSpec` profile tiers.
- `koan/agents/registry.py`: `resolve_model_spec(role, config, builtin_profiles)
-> ModelSpec` replaces `resolve_agent_config`; `compute_builtin_profiles`
  returns static Gemini profiles.
- `koan/agents/adapter.py` (NEW): the single per-provider dialect seam --
  `resolve_credentials`, `map_thinking`, `build_model_settings`, `build_model`.
  Gemini implemented via `google-gla:{model}`; **non-Gemini providers raise
  `NotImplementedError("...M7")`**.
- `pyproject.toml`: pinned `pydantic-ai-slim==2.0.0b5` with provider extras
  (`anthropic,bedrock,google,openai,duckduckgo`). Installs cleanly.
- Memory module (`koan/memory/llm.py`, `koan/memory/retrieval/reflect.py`)
  confirmed to import and run under v2 -- the adaptation was minimal (~12 lines).

### M2 -- In-process agent spine on Gemini

- `koan/agents/pydantic_ai.py` (NEW): `PydanticAIAgent` implements the `Agent`
  protocol, drives one `agent.iter()` run on Gemini, and translates the streamed
  graph events into the unchanged 8-type `StreamEvent` vocabulary.
- `koan/tools/koan_tools.py` (NEW): `ToolDeps`; Context-free step cores
  (`advance_step`, `apply_set_phase`); `build_minimal_koan_toolset()`.
- `koan/tools/builtin_tools.py` (NEW): `read_tool` + `build_builtin_toolset()`.
- `koan/runners/base.py`: `StreamEvent.usage` (`RequestUsage`) carries real
  per-request usage/cost; surfaced to the frontend footer.
- `koan/web/mcp_endpoint.py`: `koan_complete_step` / `koan_set_phase` handlers
  now delegate to the shared in-process cores.
- `tests/conftest.py` (NEW): async-test fixture infra.

### M3 -- Full koan toolset + ToolPolicy

- `koan/tools/koan_tools.py`: all 16 implemented koan tools ported in-process as
  a `FunctionToolset` (the 5 interaction/subagent tools remain deferred to
  M5/M6).
- `koan/tools/tool_policy.py` (NEW): `ToolPolicy` + `build_tool_policy()` +
  `compose_toolset(role, phase)` -- the fence replacement. Cross-checked against
  the legacy `check_permission` in `tests/test_tool_policy.py`.
- `run()` registers `compose_toolset(role, phase)` intersected with implemented
  tools, so disallowed tools are never registered.

### M4 -- Built-in toolset complete + context-file injection

- `koan/tools/builtin_tools.py`: `write`/`edit`/`glob`/`grep`/`bash` added (all
  6 built-ins), each emitting the metrics-bearing output the projection fold
  expects. `write`/`edit` self-validate path-scope tool-internally.
- `koan/tools/context_files.py` (NEW): just-in-time AGENTS.md/CLAUDE.md
  discovery and `<project_instructions>` injection via a history-processor.
- `koan/state.py`: `AgentState.injected_context_files` + `pending_context_files`.
- `web_search` / `web_fetch` deferred to M7 (their native-or-local selection is
  per-provider).

### M5a -- Multi-turn loop spine

- `koan/agents/loop.py` (NEW): `run_agent_loop` -- owns
  `AgentState.message_history`, runs `agent.iter` per turn, parks on the
  loop-owned `yield_future` at the terminal-text hand-back, resumes on the next
  user message.
- `koan/state.py`: `AgentState.message_history` (driver-owned conversation
  across turns).
- `koan/agents/pydantic_ai.py`: `run()` wired to `run_agent_loop` (multi-turn).

## What is left to do

### M5b -- koan_yield removal cascade + build repair (IN PROGRESS, build broken)

**This is the immediate blocker.** M5 run 2 left a half-deleted `koan_yield`
handler. Concretely:

1. **Build repair (do first):** `koan/web/mcp_endpoint.py:636` has an
   `IndentationError` -- the `koan_yield` handler body was replaced with a
   comment block but `async def koan_set_phase` below it is now dangling. The
   module does not compile, so `koan` does not import and the test suite cannot
   collect.
2. **Finish the removal cascade.** `koan_yield` is still referenced in:
   - `koan/web/mcp_endpoint.py` -- the `mcp.tool(name="koan_yield")(koan_yield)`
     registration (line ~1486), the `Handlers.koan_yield` field (line ~343), the
     `koan_yield=koan_yield` wiring (line ~1509), and the yolo auto-response
     helper (line ~130).
   - `koan/runners/base.py` -- `KOAN_MCP_TOOLS`.
   - `koan/lib/permissions.py` -- `ROLE_PERMISSIONS`.
   - `koan/phases/format_step.py` -- `terminal_invoke`.
   - Guidance wording in `curation.py`, `frame.py`, `milestone_review.py`,
     `plan_review.py`, `tech_plan_review.py`, `koan/prompts/orchestrator.py`
     (edit wording, not phase logic).
   - `koan/tools/koan_tools.py:288` and the comments in `koan/state.py` /
     `koan/projections.py` (review for staleness).
3. Add a `koan_yield` negative-presence test + the eval-consumer sweep
   (`evals/`, `scripts/`, non-fixture `tests/`; exclude the pinned `koan-1`
   fixture).
4. Restore a green suite.

### M5c -- In-process interaction tools + tests (pending)

Port the two blocking interaction tools in-process to
`koan/tools/koan_tools.py`: `koan_ask_question` (via `enqueue_interaction`) and
`koan_memory_propose` (via `memory_propose_future`), preserving reentry guards
and yolo auto-answer; register in `build_koan_toolset`; MCP handlers delegate to
the cores. Wire steering injection between graph nodes (drain user messages to a
user message before the next model request, never between a tool call and its
result). Add `tests/test_loop.py` (multi-turn park/resume, yolo/directed
hand-back, steering, terminate on `workflow_done`) and update
`tests/test_attachments_delivery.py` + `tests/test_phase_guidance.py`. After
this, **single-agent phases run end-to-end on Gemini with full interaction
parity.**

### M6 -- Subagents as in-process asyncio tasks (pending)

Replace subagent subprocess spawning with in-process `asyncio` tasks:
`koan_request_executor` (single) and `koan_request_scouts` (bounded by
`scout_concurrency`), each running its own loop/history/toolset/directory (the
`task.json` contract and per-subagent audit log retained). Add the task registry
(`AppState._active_tasks`), shutdown cancellation, and crash containment
(subagent exception -> failed result, not workflow crash). Slim the `Agent`
protocol in `koan/agents/base.py` (drop `register_process` / `exit_code` /
`stderr_output`, which `PydanticAIAgent` currently implements as no-ops). After
this, **multi-agent workflows run end-to-end on Gemini.**

### M7 -- Provider fan-out + caching (pending)

Extend the adapter to Anthropic, OpenAI, and Bedrock (Claude and OpenAI on
Bedrock) -- remove the `NotImplementedError("...M7")` guards. Map each
provider's thinking knob; resolve `CachingPolicy` per provider (Anthropic
explicit flags, OpenAI/Gemini automatic, Bedrock marker/fallback); select web
search native-or-`duckduckgo` (this lands `web_search`/`web_fetch`, deferred
from M4). Extend cost pricing and the footer's cache/cost/context-window gauges.
Non-Gemini providers validated manually.

### M8 -- Settings UI rework + profiles (pending)

Rework the settings surface from CLI-binary detection to API-credential entry
and validation: settings endpoints in `koan/web/app.py` and the frontend
`SettingsOverlay` (respecting the protected design system), plus refreshed
built-in profiles for the new schema. The probe/binary-detection endpoints
become credential entry + validation.

> Frontend note: any work here must follow `frontend/AGENTS.md` and
> `frontend/src/components/AGENTS.md` (token discipline, protected files), and
> run `tsc --noEmit` after TS/TSX changes.

### M9 -- Rip-out (pending)

Delete the superseded agent layer: `koan/agents/claude.py` (`ClaudeSDKAgent`),
`koan/agents/command_line.py`, `koan/runners/` (move `StreamEvent` to a
surviving module), the `koan/web/mcp_endpoint.py` HTTP wrapper +
`AgentResolutionMiddleware` + the `/mcp` route, the residual `check_permission`
gate and `koan/probe.py`, the dead `mcp_url` / tool-whitelist plumbing, and the
`claude-agent-sdk` + `fastmcp` dependencies. PydanticAI becomes the only path.

## Risks and notes for whoever resumes

- **Nothing is committed.** All of M1-M5a (and the broken M5b state) lives in the
  working tree as uncommitted changes (10 modified tracked files + new
  `koan/agents/{adapter,loop,pydantic_ai}.py`, `koan/tools/`, and 6 new test
  files). A first step should be to repair the build and commit the
  known-good M1-M5a slice before continuing, so progress is not lost.
- **koan is dog-fooded on itself.** This migration is being run _by_ koan, which
  still runs on the SDK path. Breaking the SDK path mid-flight (M5b-M8) means the
  tool building the replacement is degraded until M9. The hard-cutover brief
  accepts a non-shippable `main` between M2 and M9.
- **Gemini-only until M7.** Live testing currently requires `GOOGLE_API_KEY`;
  the adapter raises `NotImplementedError` for the other three providers.
- **A follow-up koan run was already started** (20:26 on 2026-06-03, workflow
  `milestones`) with the task "find the most recent run... analyze the progress,
  re-map the remaining milestones into a new brief/plan." If that run produced
  artifacts, reconcile them with this assessment before resuming.
- **Tests are marked, not deleted.** Legacy-path breakage from the config
  reshape is marked `pytest.mark.xfail(strict=False)` (67 xfailed as of M4). M9
  removes the legacy paths; the xfail markers should be cleaned up as their
  subjects are deleted, so a real regression is not masked.

## Resumption order

1. Repair `koan/web/mcp_endpoint.py` so the build compiles (M5b step 1).
2. Finish the `koan_yield` removal cascade; restore a green suite (M5b).
3. Commit the M1-M5b slice.
4. M5c -> M6 -> M7 -> M8 -> M9 in order (each milestone is dependency-ordered).
