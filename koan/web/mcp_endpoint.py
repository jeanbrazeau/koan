# MCP endpoint -- fastmcp server with permission-fenced tool handlers.
#
# Exposes build_mcp_asgi_app() which returns an ASGI sub-app that:
#   1. Validates agent_id from query params before reaching fastmcp.
#   2. Runs check_permission() on every tool call via AgentResolutionMiddleware.
#   3. Implements koan_complete_step, koan_yield, koan_request_scouts,
#      koan_ask_question, koan_set_phase, koan_set_workflow, koan_request_executor,
#      and story management tools.
#
# Phase boundary flow:
#   koan_complete_step (last step) -> invoke_after from terminal_invoke() tells the
#   orchestrator to call koan_set_phase (auto-advance) or koan_yield (full yield).
#   If the orchestrator accidentally calls koan_complete_step instead, a defensive
#   fallback nudges it back to the right path.
#   -> koan_yield blocks on AppState.interactions.yield_future until POST /api/chat resolves it
#   -> orchestrator converses, then calls koan_set_phase(phase) or koan_set_phase("done")
#      (or koan_set_workflow(workflow) for a mid-run workflow switch)
#
# koan_yield is phase-agnostic -- it works wherever the orchestrator needs to
# pause for user input, not only at phase boundaries.
#
# koan_set_phase("done") is a tombstone: sets AppState.run.workflow_done = True,
# emits workflow_completed, and causes the next koan_complete_step to return
# an exit signal so the orchestrator process terminates cleanly.

from __future__ import annotations

import asyncio
import json
import os
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Awaitable, Callable, Literal
from urllib.parse import parse_qs

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.middleware.middleware import Middleware, MiddlewareContext
from fastmcp.server.dependencies import get_http_request
from mcp.types import ContentBlock, TextContent

from ..run_state import (
    atomic_write_json,
    ensure_subagent_directory,
    load_story_state,
    save_run_state,
    save_story_state,
    load_run_state,
)
from ..lib.permissions import check_permission
from ..lib.task_json import make_workflow_history_entry
from ..lib.workflows import WORKFLOWS, get_workflow, is_valid_transition as wf_is_valid
from ..logger import get_logger, truncate_payload
from ..memory import MEMORY_TYPES, MemoryStore
from ..memory.timestamps import iso_to_ms as _iso_to_ms
from ..phases import PhaseContext
from ..phases.format_step import (
    format_user_messages,
    steering_envelope_open,
    steering_envelope_close,
    steering_message_block,
)
from .interactions import activate_next_interaction, enqueue_interaction
from ..projections import (
    ActiveCurationBatch, MemoryEntrySummary, Proposal,
    BaseToolEntry, TextEntry, ThinkingEntry, YieldEntry,
)

if TYPE_CHECKING:
    from ..state import AgentState, AppState

log = get_logger("mcp")


# -- Module-level pure helpers (no app_state dependency) ----------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text_block(s: str) -> TextContent:
    """Wrap a plain string as a TextContent block.

    Single-text-block returns are wire-identical to plain string tool returns
    in fastmcp; this helper keeps the wrap site uniform across ~20 handlers
    so a future annotation change (e.g. adding metadata) touches one place.
    """
    return TextContent(type="text", text=s)




def _compose_rag_anchor(
    task_description: str,
    run_dir: str | None,
) -> str:
    """Compose the anchor string fed to rag.generate_queries().

    Order: task -> artifacts (mtime ascending). Chronological artifact ordering
    puts the most recent artifact closest to the end (where attention is
    strongest). brief.md (written by intake) is the de facto initiative anchor;
    it appears among the run-dir markdown sorted by mtime.
    """
    sections: list[str] = []
    if task_description:
        sections.append(f"# Task description\n\n{task_description}")

    if run_dir:
        run_dir_path = Path(run_dir)
        if run_dir_path.is_dir():
            md_files = sorted(
                (p for p in run_dir_path.glob("*.md") if p.is_file()),
                key=lambda p: p.stat().st_mtime,
            )
            for p in md_files:
                try:
                    body = p.read_text(encoding="utf-8")
                except OSError:
                    continue
                sections.append(f"# Artifact: {p.name}\n\n{body}")

    return "\n\n".join(sections)


def _yolo_yield_response(suggestions: list[dict] | None) -> str:
    """Return the auto-response text for koan_yield when running in yolo mode.

    Priority: first recommended non-done suggestion's command
              -> first non-done suggestion's command
              -> "proceed"

    Driving by suggestion command keeps the orchestrator on the workflow's
    intended path without hardcoding any phase names here.
    """
    if not suggestions:
        return "proceed"
    for s in suggestions:
        if s.get("recommended") and s.get("id") != "done":
            return s.get("command", "proceed")
    for s in suggestions:
        if s.get("id") != "done":
            return s.get("command", "proceed")
    return "proceed"


def _yolo_ask_answer(questions: list[dict]) -> dict:
    """Return a synthetic answer dict for koan_ask_question when running in yolo mode.

    For each question, selects the option marked recommended: true (using its
    label). Falls back to "use your best judgement" when no option is
    recommended, giving the orchestrator latitude to decide.

    Returns a dict matching the shape expected by the existing answer-formatting
    loop: {"answers": [{"answer": "..."}]}.
    """
    answers = []
    for q in questions:
        options = q.get("options") or []
        recommended = next((o for o in options if o.get("recommended")), None)
        if recommended:
            answers.append({"answer": recommended.get("label", recommended.get("value", ""))})
        else:
            answers.append({"answer": "use your best judgement"})
    return {"answers": answers}


def _directed_yolo_response(directed_phases: list[str], current_phase: str) -> str:
    """Build the auto-response text when directed_phases is set.

    Finds current_phase in directed_phases and returns a command that steers
    the orchestrator toward the next phase in the list. Returns "proceed" when
    current_phase is not found or is already the last entry.

    Pure function -- keeps AppState out of the helper, consistent with the
    _yolo_yield_response pattern and easy to unit-test independently.
    """
    try:
        idx = directed_phases.index(current_phase)
    except ValueError:
        return "proceed"
    if idx + 1 >= len(directed_phases):
        return "proceed"
    next_phase = directed_phases[idx + 1]
    if next_phase == "done":
        return 'The workflow is complete. Call koan_set_phase("done") to end.'
    return f"Proceed to the {next_phase} phase."


# -- Artifact tool helpers (pure, no app_state) --------------------------------

_FILENAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*\.md$")


def _validate_artifact_filename(filename: str) -> str | None:
    """Return an error message if the filename is invalid, else None."""
    if not isinstance(filename, str) or not filename:
        return "filename is required"
    if "/" in filename or "\\" in filename:
        return "filename must be a root basename, no slashes"
    if not _FILENAME_PATTERN.fullmatch(filename):
        return (
            "filename must match [a-z0-9][a-z0-9_-]*.md "
            f"(got {filename!r})"
        )
    return None


def _render_curation_payload(
    batch: ActiveCurationBatch,
    decisions: list[dict],
    uploads: "UploadState",
    run_dir: str,
    runner_type: str,
) -> tuple[list[ContentBlock], list[dict]]:
    """Render a curation payload into MCP content blocks and an audit manifest.

    Block 0 is always the JSON blob (preserves json.loads(result[0].text) parse
    in the orchestrator). Per-decision attachment sections follow as separate
    blocks so the orchestrator receives file content adjacent to each decision.

    Moved from app.py so uploads and runner_type are in scope. Callers in
    app.py now set future.set_result(decisions) (raw list); koan_memory_propose
    calls this function after the future resolves.
    """
    from .uploads import upload_ids_to_blocks

    by_id = {p.id: p for p in batch.proposals}
    items = []
    for d in decisions:
        pid = d.get("proposal_id", "")
        p = by_id.get(pid)
        if p is None:
            continue
        items.append({
            "proposal_id": pid,
            "op": p.op,
            "seq": p.seq,
            "type": p.type,
            "title": p.title,
            "decision": d.get("decision", "rejected"),
            "feedback": d.get("feedback", ""),
        })
    payload_json = {"batch_id": batch.batch_id, "decisions": items}

    blocks: list[ContentBlock] = [_text_block(json.dumps(payload_json, indent=2))]
    manifest: list[dict] = []

    # Append per-decision attachment sections after the JSON blob.
    # The label block preserves adjacency between context and attachments
    # so the orchestrator can correlate files with the decision they annotate.
    for d in decisions:
        attach_ids = d.get("attachments") or []
        if attach_ids:
            pid = d.get("proposal_id", "?")
            blocks.append(_text_block(f"-- Attachments for proposal {pid} --"))
            bs, ms = upload_ids_to_blocks(uploads, run_dir, attach_ids, runner_type)
            blocks.extend(bs)
            manifest.extend(ms)

    return blocks, manifest


def _yolo_memory_propose_response(batch: ActiveCurationBatch) -> str:
    """Return a synthetic curation payload for yolo mode -- all proposals approved.

    Mirrors _render_curation_payload output so the orchestrator sees identical
    structure in yolo and interactive runs.
    """
    items = [
        {
            "proposal_id": p.id,
            "op": p.op,
            "seq": p.seq,
            "type": p.type,
            "title": p.title,
            "decision": "approved",
            "feedback": "",
        }
        for p in batch.proposals
    ]
    payload = {"batch_id": batch.batch_id, "decisions": items}
    return json.dumps(payload, indent=2)


# -- Permission check (module-level so test_mcp_check_or_raise.py can import it directly) --

def _check_or_raise(
    agent: AgentState,
    app_state: AppState,
    tool_name: str,
    tool_args: dict | None = None,
) -> None:
    """Enforce permission fence. Raises ToolError on denial."""
    phase_ctx = agent.phase_ctx
    resolved_run_dir = (
        phase_ctx.run_dir if phase_ctx is not None and phase_ctx.run_dir
        else agent.run_dir or None
    )
    current_phase = app_state.run.phase if app_state is not None else None
    result = check_permission(
        role=agent.role,
        tool_name=tool_name,
        run_dir=resolved_run_dir,
        tool_args=tool_args,
        current_step=agent.step,
        current_phase=current_phase,
    )
    if not result["allowed"]:
        raise ToolError(
            json.dumps({"error": "permission_denied", "message": result["reason"]})
        )


# -- Memory ops imports (module-level; referenced from closures inside factory) --

from ..memory import ops as memory_ops
from ..memory.ops import EntryNotFoundError, TypeMismatchError
from ..memory.types import MEMORY_TYPES
from ..memory.retrieval import RetrievalIndex, search as retrieval_search
from ..memory.retrieval import (
    IterationCapExceeded,
    ReflectResult,
    ReflectTraceEvent,
    run_reflect_agent,
)


# -- Handlers dataclass -------------------------------------------------------

@dataclass
class Handlers:
    """Record of every tool handler closure returned by build_mcp_server.

    Used by tests to invoke handlers directly without going through fastmcp's
    HTTP dispatch. Each field is the raw async closure that the factory defined
    and registered with mcp.tool().
    """
    koan_complete_step: Callable[..., Awaitable[str]]
    koan_set_phase: Callable[..., Awaitable[str]]
    koan_set_workflow: Callable[..., Awaitable[str]]
    koan_request_scouts: Callable[..., Awaitable[str]]
    koan_ask_question: Callable[..., Awaitable[str]]
    koan_request_executor: Callable[..., Awaitable[str]]
    koan_select_story: Callable[..., Awaitable[str]]
    koan_complete_story: Callable[..., Awaitable[str]]
    koan_retry_story: Callable[..., Awaitable[str]]
    koan_skip_story: Callable[..., Awaitable[str]]
    koan_memorize: Callable[..., Awaitable[str]]
    koan_forget: Callable[..., Awaitable[str]]
    koan_memory_status: Callable[..., Awaitable[str]]
    koan_search: Callable[..., Awaitable[str]]
    koan_reflect: Callable[..., Awaitable[str]]
    koan_artifact_write: Callable[..., Awaitable[str]]
    koan_artifact_edit: Callable[..., Awaitable[str]]
    koan_memory_propose: Callable[..., Awaitable[str]]
    koan_artifact_list: Callable[..., Awaitable[str]]
    koan_artifact_view: Callable[..., Awaitable[str]]


# -- AgentResolutionMiddleware ------------------------------------------------

class AgentResolutionMiddleware(Middleware):
    """Resolve the per-request AgentState from the HTTP query string and stash
    it on the fastmcp Context state-bag before the tool handler runs.

    Using request-scoped state (serializable=False) ensures the agent object
    lives only for the duration of the tool call, matching the ContextVar
    lifetime it replaces. Tool handlers read it via ctx.get_state("agent").
    """

    def __init__(self, app_state: AppState) -> None:
        self._app_state = app_state

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        ctx = context.fastmcp_context
        if ctx is None:
            # Defensive: fastmcp_context is typed Optional. In the HTTP
            # tool-call path it is always set, but we guard here so a future
            # fastmcp refactor does not silently break us.
            raise ToolError(json.dumps({
                "error": "internal_error",
                "message": "fastmcp_context not attached to tool-call middleware",
            }))
        req = get_http_request()
        agent_id = req.query_params.get("agent_id")
        agent = self._app_state.agents.get(agent_id) if agent_id else None
        if agent is None:
            raise ToolError(json.dumps({
                "error": "permission_denied",
                "message": "Unknown or inactive agent",
            }))
        await ctx.set_state("agent", agent, serializable=False)
        return await call_next(context)


# -- Factory ------------------------------------------------------------------

def build_mcp_server(app_state: AppState) -> tuple[FastMCP, Handlers]:
    """Build a fully-wired FastMCP server instance bound to app_state.

    All tool handlers are closures that capture app_state lexically.
    The factory is called exactly once per live server from build_mcp_asgi_app().
    Returns (mcp, handlers) where handlers exposes every closure for tests.
    """
    mcp = FastMCP(name="koan")
    mcp.add_middleware(AgentResolutionMiddleware(app_state))

    # -- Agent resolution helper ----------------------------------------------

    async def _get_agent(ctx: Context) -> AgentState:
        agent = await ctx.get_state("agent")
        if agent is None:
            raise ToolError(json.dumps({
                "error": "permission_denied", "message": "No agent context",
            }))
        return agent

    # -- Block utility helpers ------------------------------------------------

    def _text_of(blocks: list[ContentBlock] | None) -> str:
        """Concatenate the text of all TextContent blocks in a list.

        Used to derive a loggable/auditable string from a block list without
        reimplementing the join logic in each call site.
        """
        if not blocks:
            return ""
        return "\n\n".join(b.text for b in blocks if isinstance(b, TextContent))

    # -- Logging / projection helpers (capture app_state) ---------------------

    def _log_tool_call(agent: AgentState, tool: str, summary: str) -> None:
        phase = app_state.run.phase
        log.info(
            "tool %s | agent=%s role=%s phase=%s | %s",
            tool, agent.agent_id[:8], agent.role, phase, summary,
        )

    def begin_tool_call(
        agent: AgentState,
        tool: str,
        args: dict | str,
        summary: str = "",
    ) -> str:
        """Log the start of a tool call. Returns call_id for audit correlation.

        # tool_called/tool_completed projection emission removed in M1: the
        # streaming stdout path is the single source of truth for tool lifecycle
        # events. begin_tool_call/end_tool_call retain audit-logging duties only.
        """
        call_id = str(uuid.uuid4())
        _log_tool_call(agent, tool, summary)
        return call_id

    def end_tool_call(
        agent: AgentState,
        call_id: str,
        tool: str,
        result: list[ContentBlock] | None = None,
        attachments: list[dict] | None = None,
    ) -> None:
        """Log the end of a tool call (audit only -- no projection event emitted).

        # tool_called/tool_completed projection emission removed in M1: the
        # streaming stdout path is the single source of truth for tool lifecycle
        # events. The call_id returned by begin_tool_call is a logging tag only.
        """
        text_portion: str | None = None
        if result is not None:
            text_parts: list[str] = [
                block.text
                for block in result
                if isinstance(block, TextContent)
            ]
            text_portion = "\n\n".join(text_parts) if text_parts else ""
        if text_portion:
            log.debug("tool %s call_id=%s result_len=%d", tool, call_id, len(text_portion))

    def _push_tool_attachments(manifest: list[dict], agent: AgentState) -> None:
        """Push tool_attachments domain event if manifest is non-empty.

        M3 tool_attachments: koan-side full manifests (with upload_id and path)
        flow to the projection through this dedicated domain event, separate from
        the runner-extracted partial manifest on tool_result content blocks. Fold
        targets the in-flight tool entry by agent_id. See plan-milestone-3.md
        decision 4.
        """
        if not manifest:
            return
        from ..events import build_tool_attachments
        app_state.projection_store.push_event(
            "tool_attachments",
            build_tool_attachments(manifest),
            agent_id=agent.agent_id,
        )

    def _resolve_run_dir(agent: AgentState) -> str | None:
        phase_ctx = agent.phase_ctx
        if phase_ctx is not None and phase_ctx.run_dir:
            return phase_ctx.run_dir
        if agent.run_dir:
            return agent.run_dir
        if app_state.run.run_dir:
            return app_state.run.run_dir
        return None

    def _drain_and_append_steering(
        blocks: list[ContentBlock],
        agent: AgentState | None = None,
    ) -> tuple[list[ContentBlock], list[dict]]:
        """Drain queued steering messages and append to a block list, for
        codex/gemini agents only.

        Claude agents receive steering via the ClaudeSDKAgent PostToolUse hook
        (koan/agents/claude.py) and bypass this path. Returning blocks unchanged
        for Claude leaves the steering queue intact for the hook to drain -- the
        two paths are mutually exclusive per agent, so there is no race.

        Returns (new_blocks, manifest); does not mutate the input so callers
        with aliased references stay consistent.

        DEBUG logs are emitted on each early-return gate so operators can audit
        why steering was skipped for a given agent under KOAN_LOG_LEVEL=DEBUG.
        The not-primary log (7b) covers the same observability gap that
        drain_for_primary intentionally leaves open (see steering.py docstring).
        """
        # Gate 1: only primary agents (orchestrators) receive steering.
        # 7b: log the not-primary skip so operators can correlate with agent roles.
        if agent is not None and not agent.is_primary:
            log.debug(
                "drain skipped (not primary) | agent_id=%s",
                agent.agent_id if agent else "?",
            )
            return blocks, []
        # Gate 2: Claude receives steering via the SDK PostToolUse hook; the
        # MCP-handler path is a no-op for Claude to prevent double-delivery.
        # 7a: log the claude bypass so operators can confirm the gate is active.
        if agent is not None and agent.runner_type == "claude":
            log.debug("drain skipped (claude bypass) | agent_id=%s", agent.agent_id)
            return blocks, []
        from ..agents.steering import drain_for_primary, render_blocks
        messages = drain_for_primary(app_state, agent)
        if not messages:
            return blocks, []
        previews = [m.content[:80] for m in messages]
        log.info(
            "steering delivered via MCP handler | %d message(s): %s",
            len(messages), previews,
        )
        # 7c: capture per-message enqueue timestamps and delivery wall-clock time.
        # Latency for message i: delivery_ts_ms - enqueue_ts_ms_list[i].
        enqueue_ts_ms_list = [m.timestamp_ms for m in messages]
        delivery_ts_ms = int(time.time() * 1000)
        from ..events import build_steering_delivered
        app_state.projection_store.push_event(
            "steering_delivered",
            build_steering_delivered(len(messages), enqueue_ts_ms_list, delivery_ts_ms),
        )
        steering_blocks, steer_manifest = render_blocks(messages, app_state, agent)
        new_blocks: list[ContentBlock] = list(blocks) + steering_blocks
        return new_blocks, steer_manifest

    # -- Tool handlers (async closures capturing app_state) -------------------
    # _compute_memory_injection removed: logic now lives in
    # koan/tools/koan_tools.py:_compute_memory_injection_core, called from
    # advance_step. koan_tools.py re-imports _compose_rag_anchor from here
    # to keep anchor composition single-sourced until M9.
    # koan_complete_step and koan_set_phase delegate their core logic to
    # koan/tools/koan_tools.py (advance_step / apply_set_phase) so the step
    # machine has a single home. The MCP handlers add HTTP-only concerns:
    # start-run attachment delivery (koan_complete_step) and steering drain.

    async def koan_complete_step(ctx: Context, thoughts: str = "") -> list[ContentBlock]:
        agent = await _get_agent(ctx)
        _check_or_raise(agent, app_state, "koan_complete_step", {"thoughts": thoughts})

        call_id = begin_tool_call(agent, "koan_complete_step", {"thoughts": thoughts}, f"step {agent.step} -> next")
        result_blocks: list[ContentBlock] | None = None
        steer_manifest: list[dict] = []
        # Capture before advance_step mutates agent.step (step 0 -> 1 on handshake).
        was_step_zero = agent.step == 0
        try:
            # Delegate to the shared core; the MCP wrapper handles the HTTP-only
            # concerns (start-run attachments, steering drain) around the result.
            from ..tools.koan_tools import ToolDeps, advance_step
            try:
                result_text = await advance_step(ToolDeps(app_state=app_state, agent=agent), thoughts)
            except ValueError as e:
                # advance_step raises ValueError for step validation failures;
                # convert to ToolError for the fastmcp wire protocol.
                raise ToolError(
                    json.dumps({"error": "step_validation_failed", "message": str(e)})
                )
            result_blocks = [_text_block(result_text)]

            # Inject start-run attachments on the primary agent's very first
            # step-0 call. Guard on was_step_zero (captured before the handshake
            # advanced the counter) and is_primary so scouts/executors never see
            # boot-time attachments. Clear after delivery so phase re-entries
            # (each koan_set_phase resets step to 0) do not re-emit them.
            if was_step_zero and agent.is_primary and app_state.run.start_attachments:
                from .uploads import upload_ids_to_blocks
                attach_blocks, attach_manifest = upload_ids_to_blocks(
                    app_state.uploads,
                    "",  # run_dir is vestigial in upload_ids_to_blocks (M3)
                    app_state.run.start_attachments,
                    agent.runner_type,
                )
                result_blocks.extend(attach_blocks)
                steer_manifest.extend(attach_manifest)
                app_state.run.start_attachments = []
                log.info(
                    "start-run attachments delivered: agent=%s count=%d",
                    agent.agent_id[:8], len(attach_blocks),
                )

            result_blocks, drain_manifest = _drain_and_append_steering(result_blocks, agent)
            steer_manifest.extend(drain_manifest)
            _push_tool_attachments(steer_manifest, agent)
            return result_blocks

        finally:
            end_tool_call(agent, call_id, "koan_complete_step", result_blocks, steer_manifest or None)

    # koan_yield is removed in M5.  The multi-turn loop in koan/agents/loop.py
    # owns the hand-back: a terminal-text turn (no tool calls) is the signal
    # for the loop to park on yield_future and wait for the next user message.
    # Deleting this handler keeps the MCP vocabulary free of a tool the model
    # would otherwise waste a turn calling before the in-process path lands.

    async def koan_set_phase(ctx: Context, phase: str) -> list[ContentBlock]:
        """Commit transition to the next workflow phase.

        Call this after the user has confirmed what to do next. The next
        koan_complete_step call will return step 1 guidance for the new
        phase, including the role context for that phase.

        The available phases and their descriptions are listed in the
        koan_complete_step response when a phase completes. Any phase in
        the current workflow is a valid target (not just the suggested ones).

        Args:
            phase: Target phase name from the current workflow's available
                   phases. The phase boundary response from koan_complete_step
                   lists suggested phases with descriptions.
        """
        agent = await _get_agent(ctx)
        _check_or_raise(agent, app_state, "koan_set_phase", {"phase": phase})

        call_id = begin_tool_call(agent, "koan_set_phase", {"phase": phase}, phase)
        result_blocks: list[ContentBlock] | None = None
        steer_manifest: list[dict] = []
        try:
            # Delegate to the shared core; the MCP wrapper handles the HTTP-only
            # concern (steering drain) around the result.
            from ..tools.koan_tools import ToolDeps, apply_set_phase
            try:
                result_text = await apply_set_phase(ToolDeps(app_state=app_state, agent=agent), phase)
            except ValueError as e:
                # apply_set_phase raises ValueError for invalid transitions;
                # parse error prefix to emit structured ToolError JSON.
                msg = str(e)
                if msg.startswith("invalid_transition:"):
                    error_key = "invalid_transition"
                    error_msg = msg[len("invalid_transition:"):].strip()
                elif msg.startswith("unknown_phase:"):
                    error_key = "unknown_phase"
                    error_msg = msg[len("unknown_phase:"):].strip()
                else:
                    error_key = "phase_error"
                    error_msg = msg
                raise ToolError(json.dumps({"error": error_key, "message": error_msg}))
            result_blocks = [_text_block(result_text)]
            result_blocks, steer_manifest = _drain_and_append_steering(result_blocks, agent)
            _push_tool_attachments(steer_manifest, agent)
            return result_blocks
        finally:
            end_tool_call(agent, call_id, "koan_set_phase", result_blocks, steer_manifest or None)

    async def koan_set_workflow(ctx: Context, workflow: str) -> list[ContentBlock]:
        """Switch the active workflow mid-run, preserving the orchestrator
        process and all run-directory context.

        Delegates all state mutation and projection to apply_set_workflow in
        koan/tools/koan_tools.py (single logic home shared with the in-process
        PydanticAI tool). The MCP wrapper adds permission check, audit logging,
        and steering drain.

        Args:
            workflow: Target workflow name registered in
                      koan/lib/workflows.py:WORKFLOWS.
        """
        agent = await _get_agent(ctx)
        _check_or_raise(agent, app_state, "koan_set_workflow", {"workflow": workflow})

        call_id = begin_tool_call(agent, "koan_set_workflow", {"workflow": workflow}, workflow)
        result_blocks: list[ContentBlock] | None = None
        steer_manifest: list[dict] = []
        try:
            from ..tools.koan_tools import ToolDeps, apply_set_workflow
            try:
                result_text = await apply_set_workflow(
                    ToolDeps(app_state=app_state, agent=agent), workflow
                )
            except ValueError as e:
                msg = str(e)
                colon = msg.find(": ")
                err_key = msg[:colon] if colon != -1 else "error"
                err_msg = msg[colon + 2:] if colon != -1 else msg
                raise ToolError(json.dumps({"error": err_key, "message": err_msg}))
            result_blocks = [_text_block(result_text)]
            result_blocks, steer_manifest = _drain_and_append_steering(result_blocks, agent)
            _push_tool_attachments(steer_manifest, agent)
            return result_blocks
        finally:
            end_tool_call(agent, call_id, "koan_set_workflow", result_blocks, steer_manifest or None)

    async def koan_request_scouts(ctx: Context, questions: list[dict] | None = None) -> list[ContentBlock]:
        agent = await _get_agent(ctx)
        _check_or_raise(agent, app_state, "koan_request_scouts", {"questions": questions})

        call_id = begin_tool_call(
            agent, "koan_request_scouts", {"questions": questions or []},
            f"{len(questions or [])} scouts",
        )
        result_blocks: list[ContentBlock] | None = None
        steer_manifest: list[dict] = []
        try:
            # Delegate to the shared core (one spawn logic home across the MCP
            # path and the in-process koan toolset).
            from ..tools.koan_tools import ToolDeps, request_scouts_core
            findings_text = await request_scouts_core(
                ToolDeps(app_state=app_state, agent=agent), questions
            )
            result_blocks = [_text_block(findings_text)]
            result_blocks, steer_manifest = _drain_and_append_steering(result_blocks, agent)
            _push_tool_attachments(steer_manifest, agent)
            return result_blocks
        finally:
            end_tool_call(agent, call_id, "koan_request_scouts", result_blocks, steer_manifest or None)

    async def koan_ask_question(ctx: Context, questions: list[dict] | None = None) -> list[ContentBlock]:
        """Ask the user one or more clarifying questions.

        The UI renders a split-panel card for each question:
          - LEFT PANEL ("Context"): reference material the user reads while
            deciding. Write markdown here -- code snippets, bullet lists, bold
            terms, file references. This is your chance to show the user what
            you found and why the question matters. Think of it as an
            illustration panel, not a preamble.
          - RIGHT PANEL ("Decision"): the question text and selectable options.
            This is the action side -- keep the question crisp.

        When context is omitted, the card renders as a single column with
        just the question and options.

        Each dict in `questions` must have:
          - question (str): The decision question (rendered as markdown).
          - options (list[dict]): Choices. Each option has:
              - value (str): Machine key returned in the answer.
              - label (str): Human-readable label shown in the UI.
              - recommended (bool, optional): Pre-select this option.

        Optional fields:
          - context (str): Background shown in the left reference panel
            (markdown). Include codebase findings, tradeoff summaries,
            or relevant code snippets that inform the decision.
          - multi (bool): Allow selecting multiple options (default false).

        Format rules for options:
          - Labels are plain descriptions. Do NOT prefix with letters, numbers,
            or bullets -- the UI adds its own selection controls.
              WRONG:  "(a) Stateless wrapper"  /  "A: Stateless wrapper"
              RIGHT:  "Stateless wrapper -- compile per request, optimize later"
          - Do NOT include an "Other" or "None of the above" option.
            The UI always provides a free-text alternative automatically.
          - Keep labels concise (one line). Put rationale in `context`, not
            in the label.
        """
        agent = await _get_agent(ctx)
        _check_or_raise(agent, app_state, "koan_ask_question", {"questions": questions})

        call_id = begin_tool_call(
            agent, "koan_ask_question", {"questions": questions or []},
            f"{len(questions or [])} questions",
        )
        result_blocks: list[ContentBlock] | None = None
        steer_manifest: list[dict] = []
        try:
            # Delegate the blocking interaction to the shared core; the MCP wrapper
            # adds only fastmcp-specific concerns (ToolError conversion, steering drain).
            from ..tools.koan_tools import ToolDeps, ask_question_core
            try:
                qa_text = await ask_question_core(
                    ToolDeps(app_state=app_state, agent=agent), questions or []
                )
            except RuntimeError as exc:
                raise ToolError(json.dumps({"error": "ask_question_failed", "message": str(exc)}))
            log.info(
                "koan_ask_question answered: agent=%s count=%d",
                agent.agent_id[:8], len(questions or []),
            )
            result_blocks = [_text_block(qa_text)]
            result_blocks, steer_manifest = _drain_and_append_steering(result_blocks, agent)
            _push_tool_attachments(steer_manifest, agent)
            return result_blocks
        finally:
            end_tool_call(agent, call_id, "koan_ask_question", result_blocks, steer_manifest or None)

    async def koan_request_executor(
        ctx: Context,
        artifacts: list[str] | None = None,
        instructions: str = "",
    ) -> list[ContentBlock]:
        """Spawn a coding agent to implement changes.

        The executor reads the listed artifacts from the run directory,
        plans its approach internally, then implements. Blocks until
        the executor exits and returns a result summary.

        Args:
            artifacts: File paths relative to run directory that the
                       executor must read before coding.
                       Example: ["plan.md"]
            instructions: Free-form context for the executor -- key
                          decisions, constraints, or user direction
                          not captured in the artifact files.
        """
        agent = await _get_agent(ctx)
        _check_or_raise(agent, app_state, "koan_request_executor", {"artifacts": artifacts, "instructions": instructions})

        call_id = begin_tool_call(
            agent, "koan_request_executor",
            {"artifacts": artifacts or [], "instructions": instructions},
            f"{len(artifacts or [])} artifact(s)",
        )
        result_blocks: list[ContentBlock] | None = None
        steer_manifest: list[dict] = []
        try:
            # Delegate to the shared core; convert the core's ValueError
            # (no run dir) into the fastmcp ToolError wire shape.
            from ..tools.koan_tools import ToolDeps, request_executor_core
            try:
                payload_text = await request_executor_core(
                    ToolDeps(app_state=app_state, agent=agent), artifacts, instructions
                )
            except ValueError as e:
                msg = str(e)
                key = msg.split(":", 1)[0] if ":" in msg else "executor_error"
                raise ToolError(json.dumps({"error": key, "message": msg}))
            result_blocks = [_text_block(payload_text)]
            result_blocks, steer_manifest = _drain_and_append_steering(result_blocks, agent)
            _push_tool_attachments(steer_manifest, agent)
            return result_blocks
        finally:
            end_tool_call(agent, call_id, "koan_request_executor", result_blocks, steer_manifest or None)

    async def koan_select_story(ctx: Context, story_id: str) -> list[ContentBlock]:
        """Select the next story for execution.

        Delegates to select_story core in koan/tools/koan_tools.py.
        """
        agent = await _get_agent(ctx)
        _check_or_raise(agent, app_state, "koan_select_story", {"story_id": story_id})

        call_id = begin_tool_call(agent, "koan_select_story", {"story_id": story_id}, story_id)
        result_blocks: list[ContentBlock] | None = None
        steer_manifest: list[dict] = []
        try:
            from ..tools.koan_tools import ToolDeps, select_story
            try:
                result_text = await select_story(ToolDeps(app_state=app_state, agent=agent), story_id)
            except ValueError as e:
                raise ToolError(json.dumps({"error": "no_run_dir", "message": str(e)}))
            result_blocks = [_text_block(result_text)]
            result_blocks, steer_manifest = _drain_and_append_steering(result_blocks, agent)
            _push_tool_attachments(steer_manifest, agent)
            return result_blocks
        finally:
            end_tool_call(agent, call_id, "koan_select_story", result_blocks, steer_manifest or None)

    async def koan_complete_story(ctx: Context, story_id: str) -> list[ContentBlock]:
        """Mark a story as successfully verified and completed.

        Delegates to complete_story core in koan/tools/koan_tools.py.
        """
        agent = await _get_agent(ctx)
        _check_or_raise(agent, app_state, "koan_complete_story", {"story_id": story_id})

        call_id = begin_tool_call(agent, "koan_complete_story", {"story_id": story_id}, story_id)
        result_blocks: list[ContentBlock] | None = None
        steer_manifest: list[dict] = []
        try:
            from ..tools.koan_tools import ToolDeps, complete_story
            try:
                result_text = await complete_story(ToolDeps(app_state=app_state, agent=agent), story_id)
            except ValueError as e:
                raise ToolError(json.dumps({"error": "no_run_dir", "message": str(e)}))
            result_blocks = [_text_block(result_text)]
            result_blocks, steer_manifest = _drain_and_append_steering(result_blocks, agent)
            _push_tool_attachments(steer_manifest, agent)
            return result_blocks
        finally:
            end_tool_call(agent, call_id, "koan_complete_story", result_blocks, steer_manifest or None)

    async def koan_retry_story(ctx: Context, story_id: str, failure_summary: str) -> list[ContentBlock]:
        """Send a story back for retry with a detailed failure summary.

        Delegates to retry_story core in koan/tools/koan_tools.py.
        """
        agent = await _get_agent(ctx)
        _check_or_raise(agent, app_state, "koan_retry_story", {"story_id": story_id, "failure_summary": failure_summary})

        call_id = begin_tool_call(agent, "koan_retry_story", {"story_id": story_id}, story_id)
        result_blocks: list[ContentBlock] | None = None
        steer_manifest: list[dict] = []
        try:
            from ..tools.koan_tools import ToolDeps, retry_story
            try:
                result_text = await retry_story(
                    ToolDeps(app_state=app_state, agent=agent), story_id, failure_summary
                )
            except ValueError as e:
                raise ToolError(json.dumps({"error": "no_run_dir", "message": str(e)}))
            result_blocks = [_text_block(result_text)]
            result_blocks, steer_manifest = _drain_and_append_steering(result_blocks, agent)
            _push_tool_attachments(steer_manifest, agent)
            return result_blocks
        finally:
            end_tool_call(agent, call_id, "koan_retry_story", result_blocks, steer_manifest or None)

    async def koan_skip_story(ctx: Context, story_id: str, reason: str = "") -> list[ContentBlock]:
        """Skip a story that is superseded or no longer needed.

        Delegates to skip_story core in koan/tools/koan_tools.py.
        """
        agent = await _get_agent(ctx)
        _check_or_raise(agent, app_state, "koan_skip_story", {"story_id": story_id, "reason": reason})

        call_id = begin_tool_call(agent, "koan_skip_story", {"story_id": story_id}, story_id)
        result_blocks: list[ContentBlock] | None = None
        steer_manifest: list[dict] = []
        try:
            from ..tools.koan_tools import ToolDeps, skip_story
            try:
                result_text = await skip_story(
                    ToolDeps(app_state=app_state, agent=agent), story_id, reason
                )
            except ValueError as e:
                raise ToolError(json.dumps({"error": "no_run_dir", "message": str(e)}))
            result_blocks = [_text_block(result_text)]
            result_blocks, steer_manifest = _drain_and_append_steering(result_blocks, agent)
            _push_tool_attachments(steer_manifest, agent)
            return result_blocks
        finally:
            end_tool_call(agent, call_id, "koan_skip_story", result_blocks, steer_manifest or None)

    async def koan_memorize(
        ctx: Context,
        type: str,
        title: str,
        body: str,
        related: list[str] | None = None,
        entry_id: int | None = None,
    ) -> list[ContentBlock]:
        """Write a memory entry.

        Delegates to memorize_core in koan/tools/koan_tools.py (single logic
        home shared with the in-process PydanticAI tool).

        Args:
            type: Memory type (decision, context, lesson, procedure)
            title: Short descriptive name
            body: Prose content (100-500 tokens)
            related: Filenames of related entries (optional)
            entry_id: Sequence number for updates (omit for creates)
        """
        agent = await _get_agent(ctx)
        _check_or_raise(agent, app_state, "koan_memorize", {
            "type": type, "title": title, "entry_id": entry_id,
        })
        call_id = begin_tool_call(
            agent, "koan_memorize",
            {"type": type, "title": title, "entry_id": entry_id},
            f"{type}: {title}",
        )
        result_blocks: list[ContentBlock] | None = None
        steer_manifest: list[dict] = []
        try:
            from ..memory.ops import EntryNotFoundError, TypeMismatchError
            from ..tools.koan_tools import ToolDeps, memorize_core
            try:
                result_text = await memorize_core(
                    ToolDeps(app_state=app_state, agent=agent),
                    type, title, body, related, entry_id,
                )
            except EntryNotFoundError as e:
                raise ToolError(json.dumps({"error": "entry_not_found", "message": str(e)}))
            except TypeMismatchError as e:
                raise ToolError(json.dumps({"error": "type_mismatch", "message": str(e)}))
            except ValueError as e:
                raise ToolError(json.dumps({"error": "invalid_type", "message": str(e)}))
            result_blocks = [_text_block(result_text)]
            result_blocks, steer_manifest = _drain_and_append_steering(result_blocks, agent)
            _push_tool_attachments(steer_manifest, agent)
            return result_blocks
        finally:
            end_tool_call(agent, call_id, "koan_memorize", result_blocks, steer_manifest or None)

    async def koan_forget(ctx: Context, entry_id: int, type: str | None = None) -> list[ContentBlock]:
        """Remove a memory entry.

        Delegates to forget_core in koan/tools/koan_tools.py.

        Args:
            entry_id: Sequence number (NNNN prefix from filename)
            type: Memory type (optional). When provided, the found entry's
                  type must match or a type_mismatch error is raised.
        """
        agent = await _get_agent(ctx)
        _check_or_raise(agent, app_state, "koan_forget", {"type": type, "entry_id": entry_id})
        call_id = begin_tool_call(
            agent, "koan_forget",
            {"type": type, "entry_id": entry_id},
            f"{type or '*'}/{entry_id}",
        )
        result_blocks: list[ContentBlock] | None = None
        steer_manifest: list[dict] = []
        try:
            from ..memory.ops import EntryNotFoundError, TypeMismatchError
            from ..tools.koan_tools import ToolDeps, forget_core
            try:
                result_text = await forget_core(
                    ToolDeps(app_state=app_state, agent=agent), entry_id, type
                )
            except EntryNotFoundError as e:
                raise ToolError(json.dumps({"error": "entry_not_found", "message": str(e)}))
            except TypeMismatchError as e:
                raise ToolError(json.dumps({"error": "type_mismatch", "message": str(e)}))
            except ValueError as e:
                raise ToolError(json.dumps({"error": "invalid_type", "message": str(e)}))
            result_blocks = [_text_block(result_text)]
            result_blocks, steer_manifest = _drain_and_append_steering(result_blocks, agent)
            _push_tool_attachments(steer_manifest, agent)
            return result_blocks
        finally:
            end_tool_call(agent, call_id, "koan_forget", result_blocks, steer_manifest or None)

    async def koan_memory_status(ctx: Context, type: str | None = None) -> list[ContentBlock]:
        """Get an orientation view of project memory.

        Delegates to memory_status_core in koan/tools/koan_tools.py.

        Args:
            type: Filter listing to a specific memory type (optional).
        """
        agent = await _get_agent(ctx)
        _check_or_raise(agent, app_state, "koan_memory_status", {"type": type})
        call_id = begin_tool_call(
            agent, "koan_memory_status", {"type": type}, type or "all",
        )
        result_blocks: list[ContentBlock] | None = None
        steer_manifest: list[dict] = []
        try:
            from ..tools.koan_tools import ToolDeps, memory_status_core
            try:
                result_text = await memory_status_core(
                    ToolDeps(app_state=app_state, agent=agent), type
                )
            except ValueError as e:
                raise ToolError(json.dumps({"error": "invalid_type", "message": str(e)}))
            result_blocks = [_text_block(result_text)]
            result_blocks, steer_manifest = _drain_and_append_steering(result_blocks, agent)
            _push_tool_attachments(steer_manifest, agent)
            return result_blocks
        finally:
            end_tool_call(agent, call_id, "koan_memory_status", result_blocks, steer_manifest or None)

    async def koan_search(
        ctx: Context,
        query: str,
        type: str | None = None,
        k: int = 5,
    ) -> list[ContentBlock]:
        """Search memory entries by semantic similarity.

        Delegates to search_core in koan/tools/koan_tools.py.

        Args:
            query: Search query string
            type: Filter results to a specific memory type (optional)
            k: Number of results to return (default: 5)
        """
        agent = await _get_agent(ctx)
        _check_or_raise(agent, app_state, "koan_search", {"type": type})
        call_id = begin_tool_call(
            agent, "koan_search",
            {"query": query, "type": type, "k": k},
            f"query={query!r} type={type or 'all'} k={k}",
        )
        result_blocks: list[ContentBlock] | None = None
        steer_manifest: list[dict] = []
        try:
            from ..tools.koan_tools import ToolDeps, search_core
            try:
                result_text = await search_core(
                    ToolDeps(app_state=app_state, agent=agent), query, type, k
                )
            except ValueError as e:
                raise ToolError(json.dumps({"error": "invalid_type", "message": str(e)}))
            except RuntimeError as e:
                raise ToolError(json.dumps({"error": "search_failed", "message": str(e)}))
            result_blocks = [_text_block(result_text)]
            result_blocks, steer_manifest = _drain_and_append_steering(result_blocks, agent)
            _push_tool_attachments(steer_manifest, agent)
            return result_blocks
        finally:
            end_tool_call(agent, call_id, "koan_search", result_blocks, steer_manifest or None)

    async def koan_reflect(
        ctx: Context,
        question: str,
        context: str | None = None,
    ) -> list[ContentBlock]:
        """Synthesize a cited briefing over project memory.

        Calls run_reflect_agent with a trace callback that emits reflect_delta
        projection events for text-kind deltas. ToolError wrapping is
        MCP-specific and stays here; the in-process path (reflect_core in
        koan/tools/koan_tools.py) raises plain exceptions instead.

        run_reflect_agent is called via the module-level import so test
        monkeypatches on mcp_endpoint.run_reflect_agent take effect -- the
        reflect_core delegation path uses a lazy import that would bypass them.

        Args:
            question: The broad question to answer.
            context: Optional caller-provided context.
        """
        agent = await _get_agent(ctx)
        _check_or_raise(agent, app_state, "koan_reflect", {})
        call_id = begin_tool_call(
            agent, "koan_reflect",
            {"question": question, "context": context},
            f"question={question!r}",
        )
        result_blocks: list[ContentBlock] | None = None
        steer_manifest: list[dict] = []
        try:
            from ..events import build_reflect_delta

            # Only text-kind deltas flow into the projection feed; other kinds
            # (search, done, thinking) are consumed by /api/memory/reflect.
            def _on_trace(ev: ReflectTraceEvent) -> None:
                if ev.kind != "text" or not ev.delta:
                    return
                app_state.projection_store.push_event(
                    "reflect_delta",
                    build_reflect_delta(ev.delta),
                    agent_id=agent.agent_id,
                )

            try:
                index = app_state.memory.retrieval_index
                result = await run_reflect_agent(
                    index, question, context=context, on_trace=_on_trace
                )
            except IterationCapExceeded as e:
                raise ToolError(json.dumps({
                    "error": "iteration_cap_exceeded",
                    "message": str(e),
                    "iterations": e.iterations,
                }))
            except RuntimeError as e:
                raise ToolError(json.dumps({"error": "reflect_failed", "message": str(e)}))

            out = {
                "answer": result.answer,
                "citations": [
                    {
                        "id": c.id,
                        "title": c.title,
                        "type": c.type,
                        "modifiedMs": c.modified_ms,
                    }
                    for c in result.citations
                ],
                "iterations": result.iterations,
            }
            result_blocks = [_text_block(json.dumps(out))]
            result_blocks, steer_manifest = _drain_and_append_steering(result_blocks, agent)
            _push_tool_attachments(steer_manifest, agent)
            return result_blocks
        finally:
            end_tool_call(agent, call_id, "koan_reflect", result_blocks, steer_manifest or None)

    async def koan_artifact_write(
        ctx: Context,
        filename: str,
        content: str,
    ) -> list[ContentBlock]:
        """Write or update an artifact file. Non-blocking; full-rewrite semantics.

        Delegates to artifact_write_core in koan/tools/koan_tools.py (single
        logic home shared with the in-process PydanticAI tool).

        Args:
            filename: Root-only basename, must match [a-z0-9][a-z0-9_-]*.md
            content: Full markdown body (no frontmatter; the driver writes it).
        """
        agent = await _get_agent(ctx)
        _check_or_raise(agent, app_state, "koan_artifact_write",
                        {"filename": filename})

        call_id = begin_tool_call(
            agent, "koan_artifact_write",
            {"filename": filename, "content_len": len(content or "")},
            f"write {filename}",
        )
        result_blocks: list[ContentBlock] | None = None
        steer_manifest: list[dict] = []
        try:
            from ..tools.koan_tools import ToolDeps, artifact_write_core
            try:
                result_text = await artifact_write_core(
                    ToolDeps(app_state=app_state, agent=agent), filename, content
                )
            except ValueError as e:
                msg = str(e)
                colon = msg.find(": ")
                err_key = msg[:colon] if colon != -1 else "error"
                err_msg = msg[colon + 2:] if colon != -1 else msg
                raise ToolError(json.dumps({"error": err_key, "message": err_msg}))
            result_blocks = [_text_block(result_text)]
            result_blocks, steer_manifest = _drain_and_append_steering(result_blocks, agent)
            _push_tool_attachments(steer_manifest, agent)
            return result_blocks
        finally:
            end_tool_call(agent, call_id, "koan_artifact_write", result_blocks, steer_manifest or None)

    async def koan_artifact_edit(
        ctx: Context,
        filename: str,
        old_string: str,
        new_string: str,
    ) -> list[ContentBlock]:
        """Surgical in-place edit of an artifact's body. Single-unique-match semantics.

        Delegates to artifact_edit_core in koan/tools/koan_tools.py (single
        logic home shared with the in-process PydanticAI tool).

        Returns {"ok": true, "filename": ...} on success. Emits artifact_diff
        so the sidebar refreshes, matching koan_artifact_write behavior.
        """
        agent = await _get_agent(ctx)
        _check_or_raise(agent, app_state, "koan_artifact_edit",
                        {"filename": filename})

        call_id = begin_tool_call(
            agent, "koan_artifact_edit",
            {"filename": filename},
            f"edit {filename}",
        )
        result_blocks: list[ContentBlock] | None = None
        steer_manifest: list[dict] = []
        try:
            from ..tools.koan_tools import ToolDeps, artifact_edit_core
            try:
                result_text = await artifact_edit_core(
                    ToolDeps(app_state=app_state, agent=agent), filename, old_string, new_string
                )
            except ValueError as e:
                msg = str(e)
                colon = msg.find(": ")
                err_key = msg[:colon] if colon != -1 else "error"
                err_msg = msg[colon + 2:] if colon != -1 else msg
                raise ToolError(json.dumps({"error": err_key, "message": err_msg}))
            result_blocks = [_text_block(result_text)]
            result_blocks, steer_manifest = _drain_and_append_steering(result_blocks, agent)
            _push_tool_attachments(steer_manifest, agent)
            return result_blocks
        finally:
            end_tool_call(agent, call_id, "koan_artifact_edit", result_blocks, steer_manifest or None)

    async def koan_memory_propose(
        ctx: Context,
        proposals: list[dict],
        context_note: str = "",
    ) -> list[ContentBlock]:
        """Propose one or more memory entries to the user for approval; block until
        they submit decisions.

        Returns a structured JSON payload the orchestrator reads to decide which
        proposals to apply via koan_memorize / koan_forget, which to revise and
        re-propose, and which to drop.

        Args:
            proposals: List of proposal dicts matching the Proposal wire schema.
            context_note: Optional free-form note shown above the proposal list.
        """
        agent = await _get_agent(ctx)
        _check_or_raise(agent, app_state, "koan_memory_propose", {})

        call_id = begin_tool_call(
            agent, "koan_memory_propose",
            {"proposal_count": len(proposals or []), "context_note": context_note},
            f"{len(proposals or [])} proposal(s)",
        )
        result_blocks: list[ContentBlock] | None = None
        steer_manifest: list[dict] = []
        curation_manifest: list[dict] = []
        try:
            # Delegate the full interaction lifecycle to the shared core.  The MCP
            # wrapper adds per-decision attachment interleaving (which needs uploads
            # and runner_type in scope) plus fastmcp ToolError conversion.
            from ..tools.koan_tools import ToolDeps, propose_memory_core
            try:
                json_text, decisions = await propose_memory_core(
                    ToolDeps(app_state=app_state, agent=agent), proposals or [], context_note
                )
            except (ValueError, RuntimeError) as exc:
                msg = str(exc)
                colon = msg.find(":")
                err_key = msg[:colon].strip() if colon != -1 else "propose_error"
                err_msg = msg[colon + 1:].strip() if colon != -1 else msg
                raise ToolError(json.dumps({"error": err_key, "message": err_msg}))

            result_blocks = [_text_block(json_text)]

            # Append per-decision attachment sections so the orchestrator receives
            # file content adjacent to the decision it annotates.
            if decisions:
                from .uploads import upload_ids_to_blocks
                run_dir_for_curation = _resolve_run_dir(agent) or ""
                for d in decisions:
                    attach_ids = d.get("attachments") or []
                    if attach_ids:
                        pid = d.get("proposal_id", "?")
                        result_blocks.append(_text_block(f"-- Attachments for proposal {pid} --"))
                        bs, ms = upload_ids_to_blocks(
                            app_state.uploads, run_dir_for_curation,
                            attach_ids, agent.runner_type,
                        )
                        result_blocks.extend(bs)
                        curation_manifest.extend(ms)

            result_blocks, steer_manifest = _drain_and_append_steering(result_blocks, agent)
            _push_tool_attachments(curation_manifest + steer_manifest, agent)
            return result_blocks
        finally:
            total_manifest = curation_manifest + steer_manifest
            end_tool_call(agent, call_id, "koan_memory_propose", result_blocks, total_manifest or None)

    async def koan_artifact_list(ctx: Context) -> list[ContentBlock]:
        """List artifacts in the run directory.

        Delegates to artifact_list_core in koan/tools/koan_tools.py.
        """
        agent = await _get_agent(ctx)
        _check_or_raise(agent, app_state, "koan_artifact_list", {})
        call_id = begin_tool_call(agent, "koan_artifact_list", {}, "list")
        result_blocks: list[ContentBlock] | None = None
        steer_manifest: list[dict] = []
        try:
            from ..tools.koan_tools import ToolDeps, artifact_list_core
            result_text = await artifact_list_core(ToolDeps(app_state=app_state, agent=agent))
            result_blocks = [_text_block(result_text)]
            result_blocks, steer_manifest = _drain_and_append_steering(result_blocks, agent)
            _push_tool_attachments(steer_manifest, agent)
            return result_blocks
        finally:
            end_tool_call(agent, call_id, "koan_artifact_list", result_blocks, steer_manifest or None)

    async def koan_artifact_view(ctx: Context, filename: str) -> list[ContentBlock]:
        """Return the full text content of an artifact.

        Delegates to artifact_view_core in koan/tools/koan_tools.py.
        """
        agent = await _get_agent(ctx)
        _check_or_raise(agent, app_state, "koan_artifact_view",
                        {"filename": filename})
        call_id = begin_tool_call(agent, "koan_artifact_view",
                                  {"filename": filename}, filename)
        result_blocks: list[ContentBlock] | None = None
        steer_manifest: list[dict] = []
        try:
            from ..tools.koan_tools import ToolDeps, artifact_view_core
            try:
                result_text = await artifact_view_core(
                    ToolDeps(app_state=app_state, agent=agent), filename
                )
            except ValueError as e:
                msg = str(e)
                colon = msg.find(": ")
                err_key = msg[:colon] if colon != -1 else "error"
                err_msg = msg[colon + 2:] if colon != -1 else msg
                raise ToolError(json.dumps({"error": err_key, "message": err_msg}))
            result_blocks = [_text_block(result_text)]
            result_blocks, steer_manifest = _drain_and_append_steering(result_blocks, agent)
            _push_tool_attachments(steer_manifest, agent)
            return result_blocks
        finally:
            end_tool_call(agent, call_id, "koan_artifact_view", result_blocks, steer_manifest or None)

    # -- fastmcp registration (lockstep with Handlers fields) -----------------

    mcp.tool(name="koan_complete_step")(koan_complete_step)
    mcp.tool(name="koan_set_phase")(koan_set_phase)
    mcp.tool(name="koan_set_workflow")(koan_set_workflow)
    mcp.tool(name="koan_request_scouts")(koan_request_scouts)
    mcp.tool(name="koan_ask_question")(koan_ask_question)
    mcp.tool(name="koan_request_executor")(koan_request_executor)
    mcp.tool(name="koan_select_story")(koan_select_story)
    mcp.tool(name="koan_complete_story")(koan_complete_story)
    mcp.tool(name="koan_retry_story")(koan_retry_story)
    mcp.tool(name="koan_skip_story")(koan_skip_story)
    mcp.tool(name="koan_memorize")(koan_memorize)
    mcp.tool(name="koan_forget")(koan_forget)
    mcp.tool(name="koan_memory_status")(koan_memory_status)
    mcp.tool(name="koan_search")(koan_search)
    mcp.tool(name="koan_reflect")(koan_reflect)
    mcp.tool(name="koan_artifact_write")(koan_artifact_write)
    mcp.tool(name="koan_artifact_edit")(koan_artifact_edit)
    mcp.tool(name="koan_memory_propose")(koan_memory_propose)
    mcp.tool(name="koan_artifact_list")(koan_artifact_list)
    mcp.tool(name="koan_artifact_view")(koan_artifact_view)

    handlers = Handlers(
        koan_complete_step=koan_complete_step,
        koan_set_phase=koan_set_phase,
        koan_set_workflow=koan_set_workflow,
        koan_request_scouts=koan_request_scouts,
        koan_ask_question=koan_ask_question,
        koan_request_executor=koan_request_executor,
        koan_select_story=koan_select_story,
        koan_complete_story=koan_complete_story,
        koan_retry_story=koan_retry_story,
        koan_skip_story=koan_skip_story,
        koan_memorize=koan_memorize,
        koan_forget=koan_forget,
        koan_memory_status=koan_memory_status,
        koan_search=koan_search,
        koan_reflect=koan_reflect,
        koan_artifact_write=koan_artifact_write,
        koan_artifact_edit=koan_artifact_edit,
        koan_memory_propose=koan_memory_propose,
        koan_artifact_list=koan_artifact_list,
        koan_artifact_view=koan_artifact_view,
    )
    return mcp, handlers


# -- ASGI wrapper -------------------------------------------------------------

def build_mcp_asgi_app(app_state: AppState):
    """Return an ASGI app that validates agent_id then delegates to fastmcp.

    The ASGI wrapper provides a cheap pre-reject (403) for unknown agent IDs
    before the request reaches fastmcp. The actual per-request agent resolution
    happens inside AgentResolutionMiddleware.on_call_tool.
    """
    mcp, _handlers = build_mcp_server(app_state)
    inner = mcp.http_app(path="/")

    async def asgi_wrapper(scope, receive, send):
        if scope["type"] == "http":
            qs = parse_qs(scope.get("query_string", b"").decode())
            agent_id = (qs.get("agent_id") or [None])[0]

            agent = app_state.agents.get(agent_id) if agent_id else None
            if agent is None:
                log.warning("Unknown agent_id %s", agent_id)
                body = json.dumps({
                    "error": "permission_denied",
                    "message": "Unknown or inactive agent",
                }).encode()
                await send({
                    "type": "http.response.start",
                    "status": 403,
                    "headers": [
                        [b"content-type", b"application/json"],
                        [b"content-length", str(len(body)).encode()],
                    ],
                })
                await send({"type": "http.response.body", "body": body})
                return
            await inner(scope, receive, send)
        else:
            await inner(scope, receive, send)

    return asgi_wrapper, inner
