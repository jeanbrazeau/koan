# In-process step-machine tool cores: advance_step and apply_set_phase.
#
# These functions extract the business logic from koan/web/mcp_endpoint.py's
# koan_complete_step and koan_set_phase handlers so the logic has a single
# home. Both the MCP handlers (HTTP path) and the PydanticAI in-process tools
# call these cores. The MCP handlers are deleted at M9.
#
# Circular-import discipline: this module imports from koan.phases, koan.events,
# koan.driver, and koan.run_state -- all stable, non-circular. It does NOT import
# from koan.web.* at module load (that would be circular via subagent.py). The
# _compute_memory_injection_core helper imports from koan.web.mcp_endpoint lazily
# to reuse _compose_rag_anchor; this deferred import is safe at call time.

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..state import AgentState, AppState


@dataclass
class ToolDeps:
    """Per-run dependency object passed to pydantic-ai agent.iter(deps=...).

    Carries the live app state and the calling agent's state so in-process
    tools can read and mutate driver state without an HTTP transport.
    Both fields are typed Any at module load to avoid circular imports;
    the actual types are AgentState and AppState from koan.state.
    """

    app_state: Any  # AppState -- Any avoids a circular import at module load
    agent: Any      # AgentState -- same reasoning


# -- Private helpers -----------------------------------------------------------


def _resolve_run_dir_core(agent: AgentState, app_state: AppState) -> str | None:
    """Resolve run_dir from agent phase_ctx, agent.run_dir, or app_state.run.run_dir.

    Extracted from mcp_endpoint.py's _resolve_run_dir closure so apply_set_phase
    can call it without going through the HTTP MCP path.
    """
    phase_ctx = agent.phase_ctx
    if phase_ctx is not None and phase_ctx.run_dir:
        return phase_ctx.run_dir
    if agent.run_dir:
        return agent.run_dir
    if app_state.run.run_dir:
        return app_state.run.run_dir
    return None


async def _compute_memory_injection_core(app_state: AppState, agent: AgentState) -> str:
    """Run the mechanical RAG injection pipeline for the current phase.

    Returns a rendered markdown block, or "" when the phase has no retrieval
    directive, memory is unavailable, or retrieval fails. Retrieval is
    best-effort: failure must never block the phase handshake.

    Mirrors mcp_endpoint.py's _compute_memory_injection closure; extracting it
    here allows advance_step to call it from the in-process path without the
    HTTP layer.
    """
    workflow = app_state.run.workflow
    if workflow is None:
        return ""
    binding = workflow.get_binding(app_state.run.phase)
    if binding is None or not binding.retrieval_directive:
        return ""

    # Reuse _compose_rag_anchor from mcp_endpoint to keep the anchor logic
    # single-sourced until M9 deletes the MCP path entirely.
    from ..web.mcp_endpoint import _compose_rag_anchor
    anchor = _compose_rag_anchor(
        task_description=app_state.run.task_description or "",
        run_dir=(
            (agent.phase_ctx.run_dir if agent.phase_ctx else None)
            or app_state.run.run_dir
        ),
    )

    try:
        from ..memory.retrieval.rag import inject, render_injection_block
        index = app_state.memory.retrieval_index
        results = await inject(
            index=index,
            directive=binding.retrieval_directive,
            anchor=anchor,
            k=5,
        )
        return render_injection_block(results)
    except Exception:
        from ..logger import get_logger
        get_logger("koan_tools").warning(
            "mechanical memory injection failed for phase %r; continuing without injection",
            app_state.run.phase,
            exc_info=True,
        )
        return ""


async def _step_phase_handshake_core(agent: AgentState, app_state: AppState) -> str:
    """Handle step 0 -> 1: deliver step 1 guidance prepended with phase role context.

    Mirrors mcp_endpoint.py's _step_phase_handshake nested function; the
    difference is that app_state is passed explicitly rather than captured via
    closure. Called by advance_step for the initial step of every phase.
    """
    from ..events import build_step_advanced
    from ..lib.workflows import get_suggested_phases
    from ..phases import StepGuidance
    from ..phases.format_step import format_step

    phase_module = agent.phase_module
    ctx = agent.phase_ctx

    step_names = getattr(phase_module, "STEP_NAMES", {})
    step_name = step_names.get(1, "")

    # Audit log
    if agent.event_log is not None:
        await agent.event_log.emit_step_transition(1, step_name, phase_module.TOTAL_STEPS)

    # Projection event
    app_state.projection_store.push_event(
        "agent_step_advanced",
        build_step_advanced(1, step_name, total_steps=phase_module.TOTAL_STEPS),
        agent_id=agent.agent_id,
    )

    # Mechanical memory injection runs once per phase, at the step 0 -> 1 handshake.
    ctx.memory_injection = await _compute_memory_injection_core(app_state, agent)

    # Populate auto-advance context for the last-step invoke_after.
    workflow = app_state.run.workflow
    if workflow:
        binding = workflow.get_binding(app_state.run.phase)
        ctx.next_phase = binding.next_phase if binding else None
        ctx.suggested_phases = get_suggested_phases(workflow, app_state.run.phase)
    else:
        ctx.next_phase = None
        ctx.suggested_phases = []

    agent.step = 1
    guidance = phase_module.step_guidance(1, ctx)

    # Prepend PHASE_ROLE_CONTEXT so the orchestrator receives phase role context.
    role_context = getattr(phase_module, "PHASE_ROLE_CONTEXT", "") or ""
    if role_context:
        guidance = StepGuidance(
            title=guidance.title,
            instructions=[role_context, ""] + list(guidance.instructions),
            invoke_after=guidance.invoke_after,
        )

    result = format_step(guidance)

    if app_state.server.debug:
        app_state.projection_store.push_event(
            "debug_step_guidance",
            {"content": result},
            agent_id=agent.agent_id,
        )

    return result


async def _step_within_phase_core(
    agent: AgentState,
    app_state: AppState,
    phase_module: Any,
    ctx: Any,
    next_step: int,
) -> str:
    """Handle normal within-phase step advancement.

    Mirrors mcp_endpoint.py's _step_within_phase nested function; app_state
    is passed explicitly rather than captured via closure.
    """
    from ..driver import _push_artifact_diff
    from ..events import build_step_advanced
    from ..phases.format_step import format_step

    current_step = agent.step

    # Loop-back handling
    if next_step <= current_step:
        await phase_module.on_loop_back(current_step, next_step, ctx)

    agent.step = next_step

    step_names = getattr(phase_module, "STEP_NAMES", {})
    step_name = step_names.get(next_step, "")

    # Audit log
    if agent.event_log is not None:
        await agent.event_log.emit_step_transition(next_step, step_name, phase_module.TOTAL_STEPS)

    # Projection event
    app_state.projection_store.push_event(
        "agent_step_advanced",
        build_step_advanced(next_step, step_name, total_steps=phase_module.TOTAL_STEPS),
        agent_id=agent.agent_id,
    )

    # Scan for artifacts between steps (e.g. after a write step).
    _push_artifact_diff(app_state)

    guidance = phase_module.step_guidance(next_step, ctx)
    result = format_step(guidance)

    if app_state.server.debug:
        app_state.projection_store.push_event(
            "debug_step_guidance",
            {"content": result},
            agent_id=agent.agent_id,
        )

    return result


# -- Step-machine cores --------------------------------------------------------


async def advance_step(deps: ToolDeps, thoughts: str = "") -> str:
    """Core step-machine logic for koan_complete_step.

    Handles the step 0 -> 1 phase handshake (with memory injection and
    phase role context prepend), and normal within-phase step advancement.
    Returns the formatted step guidance string that the tool returns to the model.

    Raises ValueError on step validation failure so that both the MCP handler
    (which catches and re-raises as ToolError) and the PydanticAI tool (which
    lets pydantic-ai surface it as a model retry prompt) can handle it cleanly.

    Called by both the in-process koan_complete_step PydanticAI tool and
    by the MCP handler in koan/web/mcp_endpoint.py. The MCP handler adds
    steering drain and start-run attachment handling post-core; those are
    HTTP-transport-only concerns absent from the in-process path.
    """
    from ..events import build_step_advanced

    agent = deps.agent
    app_state = deps.app_state

    agent.handshake_observed = True

    # workflow_done tombstone: orchestrator called koan_set_phase("done") earlier.
    if app_state.run.workflow_done:
        return "All phases complete. You may now exit."

    phase_module = agent.phase_module
    ctx = agent.phase_ctx

    # Step 0: phase handshake (initial call or post-koan_set_phase).
    if agent.step == 0:
        return await _step_phase_handshake_core(agent, app_state)

    # Validate current step completion before advancing.
    err = phase_module.validate_step_completion(agent.step, ctx)
    if err:
        # Raise ValueError; the MCP handler catches this and converts to ToolError.
        # The PydanticAI tool lets it surface as a ModelRetry-style error message.
        raise ValueError(f"step_validation_failed: {err}")

    # Get next step from phase module (may return None at phase boundary).
    next_step = phase_module.get_next_step(agent.step, ctx)

    if next_step is None:
        if not agent.is_primary:
            # Non-primary agents (scouts/executors) are done.
            return "All steps complete. You may now exit."
        # Phase boundary defensive fallback: the prior step's invoke_after should
        # have directed the orchestrator to call koan_set_phase, not come here.
        app_state.projection_store.push_event(
            "agent_step_advanced",
            build_step_advanced(agent.step, "", total_steps=phase_module.TOTAL_STEPS),
            agent_id=agent.agent_id,
        )
        from ..driver import _push_artifact_diff
        _push_artifact_diff(app_state)
        return (
            "This phase has no further steps. The directive at the end of your"
            " prior step's guidance instructed you to call koan_set_phase or to"
            " end your turn (no tool call) to hand back to the user -- follow"
            " that directive now."
        )

    # Normal within-phase advancement.
    return await _step_within_phase_core(agent, app_state, phase_module, ctx, next_step)


async def apply_set_phase(deps: ToolDeps, phase: str) -> str:
    """Core phase-transition logic for koan_set_phase.

    Handles the "done" tombstone, validates the transition, updates driver
    state, emits projection events, and rebuilds PhaseContext. Returns a
    confirmation string for the model.

    Raises ValueError on invalid transitions so both the MCP handler (which
    converts to ToolError) and the PydanticAI tool (which surfaces it as an
    error message) can handle it without knowing about fastmcp.

    Called by both the in-process koan_set_phase PydanticAI tool and by the
    MCP handler in koan/web/mcp_endpoint.py (which adds steering drain post-core).
    """
    from ..driver import _push_artifact_diff
    from ..events import build_step_advanced
    from ..lib.workflows import is_valid_transition as wf_is_valid
    from ..logger import get_logger
    from ..phases import PhaseContext

    log = get_logger("koan_tools")

    agent = deps.agent
    app_state = deps.app_state

    current = app_state.run.phase
    workflow = app_state.run.workflow

    # "done" tombstone: cleanly ends the workflow without a phase transition.
    if phase == "done":
        app_state.run.workflow_done = True
        app_state.projection_store.push_event("yield_cleared", {})
        app_state.projection_store.push_event("workflow_completed", {
            "success": True,
            "phase": current,
            "summary": f"Workflow completed from phase '{current}'",
        })
        return "Workflow complete. Call koan_complete_step to finish."

    # Validate transition using workflow membership check.
    if workflow is None or not wf_is_valid(workflow, current, phase):
        phases = list(workflow.available_phases) if workflow else []
        raise ValueError(
            f"invalid_transition: '{phase}' is not available from '{current}' "
            f"in the current workflow. Available phases: {phases}"
        )

    # Look up new phase module from the workflow's bindings.
    new_module = workflow.get_module(phase) if workflow else None
    if new_module is None:
        raise ValueError(
            f"unknown_phase: Phase '{phase}' has no module in workflow "
            f"'{workflow.name if workflow else '?'}'"
        )

    log.info(
        "phase transition: agent=%s from=%s to=%s",
        agent.agent_id[:8], current, phase,
    )

    # Update driver state atomically.
    app_state.run.phase = phase
    run_dir = _resolve_run_dir_core(agent, app_state)
    if run_dir:
        from ..run_state import load_run_state, save_run_state
        run_state = await load_run_state(run_dir)
        await save_run_state(run_dir, {**run_state, "phase": phase})

    # Push artifact diff and projection events in the same order as the MCP handler.
    _push_artifact_diff(app_state)
    app_state.projection_store.push_event(
        "phase_started",
        {"phase": phase},
        agent_id=agent.agent_id,
    )
    app_state.projection_store.push_event("yield_cleared", {})

    # Step-advanced visual marker (mirrors mcp_endpoint.py L1007-L1013).
    phase_label = phase.replace("-", " ").title()
    app_state.projection_store.push_event(
        "agent_step_advanced",
        build_step_advanced(0, f"-> {phase_label}"),
        agent_id=agent.agent_id,
    )

    # Inject per-workflow phase guidance for the new phase.
    binding = workflow.get_binding(phase) if workflow else None
    phase_guidance = binding.guidance if binding else ""

    # Switch phase module and reset step counter (mirrors mcp_endpoint.py L1019-L1031).
    agent.phase_module = new_module
    agent.step = 0
    agent.phase_ctx = PhaseContext(
        run_dir=run_dir or "",
        subagent_dir=agent.subagent_dir,
        project_dir=app_state.run.project_dir,
        additional_dirs=app_state.run.additional_dirs,
        task_description=app_state.run.task_description,
        workflow_name=workflow.name if workflow else "",
        phase_instructions=phase_guidance,
        completed_phase=current,
    )

    return f"Phase set to '{phase}'. Call koan_complete_step to begin."


# -- Workflow core -------------------------------------------------------------


async def apply_set_workflow(deps: ToolDeps, workflow: str) -> str:
    """Core workflow-switch logic for koan_set_workflow.

    Validates the workflow name, swaps app_state.run.workflow/phase, appends
    the new entry to the orchestrator's task.json workflow_history, persists
    the phase to run-state.json, emits projection events (workflow_selected,
    phase_started, yield_cleared, agent_step_advanced), and rebuilds
    PhaseContext for the new phase.

    Raises ValueError("unknown_workflow: ...") for unregistered workflow names.
    Raises ValueError("internal_error: ...") when the initial-phase module is missing.

    Called by both the in-process koan_set_workflow PydanticAI tool and by
    the refactored MCP handler in koan/web/mcp_endpoint.py.
    """
    import json as _json
    from pathlib import Path

    import aiofiles

    from ..driver import _push_artifact_diff
    from ..events import build_step_advanced, build_workflow_selected
    from ..lib.task_json import make_workflow_history_entry
    from ..lib.workflows import WORKFLOWS, get_workflow
    from ..logger import get_logger
    from ..phases import PhaseContext
    from ..run_state import load_run_state, save_run_state
    from ..subagent import write_task_json

    log = get_logger("koan_tools")
    agent = deps.agent
    app_state = deps.app_state

    current_workflow_obj = app_state.run.workflow
    current_phase = app_state.run.phase

    try:
        new_workflow = get_workflow(workflow)
    except ValueError:
        raise ValueError(
            f"unknown_workflow: '{workflow}' is not a registered workflow. "
            f"Available workflows: {list(WORKFLOWS.keys())}"
        )

    new_initial_phase = new_workflow.initial_phase
    new_module = new_workflow.get_module(new_initial_phase)
    if new_module is None:
        raise ValueError(
            f"internal_error: Workflow '{workflow}' has no module for its "
            f"initial_phase '{new_initial_phase}'"
        )

    log.info(
        "workflow transition: agent=%s from=%s to=%s entering_phase=%s",
        agent.agent_id[:8],
        current_workflow_obj.name if current_workflow_obj else "?",
        workflow,
        new_initial_phase,
    )

    # Swap run state before emitting projection events so fold consumers see the
    # new workflow immediately.
    app_state.run.workflow = new_workflow
    app_state.run.phase = new_initial_phase

    # Append to orchestrator task.json's workflow_history.  The atomic write
    # helper is shared with the MCP path so both paths produce identical files.
    orchestrator_task_path = Path(agent.subagent_dir) / "task.json"
    async with aiofiles.open(orchestrator_task_path, "r") as _f:
        task_dict = _json.loads(await _f.read())
    history = list(task_dict.get("workflow_history", []))
    history.append(make_workflow_history_entry(workflow, new_initial_phase))
    task_dict["workflow_history"] = history
    await write_task_json(agent.subagent_dir, task_dict)

    # Persist phase to run-state.json (mirrors apply_set_phase's path).
    run_dir = _resolve_run_dir_core(agent, app_state)
    if run_dir:
        run_state = await load_run_state(run_dir)
        await save_run_state(run_dir, {**run_state, "phase": new_initial_phase})

    # Projection events in the same order as the MCP handler so the frontend
    # fold sees a consistent event stream regardless of which path is used.
    _push_artifact_diff(app_state)
    app_state.projection_store.push_event(
        "workflow_selected",
        build_workflow_selected(workflow),
    )
    app_state.projection_store.push_event(
        "phase_started",
        {"phase": new_initial_phase},
        agent_id=agent.agent_id,
    )
    app_state.projection_store.push_event("yield_cleared", {})
    phase_label = new_initial_phase.replace("-", " ").title()
    app_state.projection_store.push_event(
        "agent_step_advanced",
        build_step_advanced(0, f"-> {workflow}: {phase_label}"),
        agent_id=agent.agent_id,
    )

    # Rebuild PhaseContext for the new workflow's initial phase.
    binding = new_workflow.get_binding(new_initial_phase)
    phase_guidance = binding.guidance if binding else ""
    agent.phase_module = new_module
    agent.step = 0
    agent.phase_ctx = PhaseContext(
        run_dir=run_dir or "",
        subagent_dir=agent.subagent_dir,
        project_dir=app_state.run.project_dir,
        additional_dirs=app_state.run.additional_dirs,
        task_description=app_state.run.task_description,
        workflow_name=new_workflow.name,
        phase_instructions=phase_guidance,
        completed_phase=current_phase,
    )

    return (
        f"Workflow set to '{workflow}'. Now in phase "
        f"'{new_initial_phase}'. Call koan_complete_step to begin."
    )


# -- Story tool cores ----------------------------------------------------------


async def select_story(deps: ToolDeps, story_id: str) -> str:
    """Core logic for koan_select_story.

    Saves story state as "selected" and returns a confirmation string.
    Raises ValueError("no_run_dir: ...") when no run directory is available.
    """
    from datetime import datetime, timezone

    from ..run_state import save_story_state

    agent = deps.agent
    app_state = deps.app_state
    run_dir = _resolve_run_dir_core(agent, app_state)
    if not run_dir:
        raise ValueError("no_run_dir: No run directory available")

    now = datetime.now(timezone.utc).isoformat()
    await save_story_state(run_dir, story_id, {
        "storyId": story_id,
        "status": "selected",
        "updatedAt": now,
    })
    return f"Story '{story_id}' selected for execution."


async def complete_story(deps: ToolDeps, story_id: str) -> str:
    """Core logic for koan_complete_story.

    Saves story state as "done" and returns a confirmation string.
    Raises ValueError("no_run_dir: ...") when no run directory is available.
    """
    from datetime import datetime, timezone

    from ..run_state import save_story_state

    agent = deps.agent
    app_state = deps.app_state
    run_dir = _resolve_run_dir_core(agent, app_state)
    if not run_dir:
        raise ValueError("no_run_dir: No run directory available")

    now = datetime.now(timezone.utc).isoformat()
    await save_story_state(run_dir, story_id, {
        "storyId": story_id,
        "status": "done",
        "updatedAt": now,
    })
    return f"Story '{story_id}' marked as done."


async def retry_story(deps: ToolDeps, story_id: str, failure_summary: str) -> str:
    """Core logic for koan_retry_story.

    Increments retry_count, saves story state as "retry", and returns a
    confirmation string with the attempt number.
    Raises ValueError("no_run_dir: ...") when no run directory is available.
    """
    from datetime import datetime, timezone

    from ..run_state import load_story_state, save_story_state

    agent = deps.agent
    app_state = deps.app_state
    run_dir = _resolve_run_dir_core(agent, app_state)
    if not run_dir:
        raise ValueError("no_run_dir: No run directory available")

    existing = await load_story_state(run_dir, story_id)
    retry_count = existing.get("retryCount", 0) + 1
    now = datetime.now(timezone.utc).isoformat()
    await save_story_state(run_dir, story_id, {
        "storyId": story_id,
        "status": "retry",
        "failureSummary": failure_summary,
        "retryCount": retry_count,
        "updatedAt": now,
    })
    return f"Story '{story_id}' queued for retry (attempt {retry_count})."


async def skip_story(deps: ToolDeps, story_id: str, reason: str = "") -> str:
    """Core logic for koan_skip_story.

    Saves story state as "skipped" (with optional reason) and returns a
    confirmation string.
    Raises ValueError("no_run_dir: ...") when no run directory is available.
    """
    from datetime import datetime, timezone

    from ..run_state import save_story_state

    agent = deps.agent
    app_state = deps.app_state
    run_dir = _resolve_run_dir_core(agent, app_state)
    if not run_dir:
        raise ValueError("no_run_dir: No run directory available")

    now = datetime.now(timezone.utc).isoformat()
    state: dict = {
        "storyId": story_id,
        "status": "skipped",
        "updatedAt": now,
    }
    if reason:
        state["skipReason"] = reason

    await save_story_state(run_dir, story_id, state)
    return f"Story '{story_id}' skipped."


# -- Memory tool cores ---------------------------------------------------------


async def memorize_core(
    deps: ToolDeps,
    type: str,
    title: str,
    body: str,
    related: list[str] | None = None,
    entry_id: int | None = None,
) -> str:
    """Core logic for koan_memorize.

    Delegates to memory_ops.memorize and emits the appropriate projection
    event (memory_entry_created or memory_entry_updated). Returns a JSON
    string of the result dict.

    Re-raises EntryNotFoundError, TypeMismatchError, and ValueError so
    callers (MCP handler, in-process tool) can map them to their error shapes.
    """
    import json

    from ..events import build_memory_entry_created, build_memory_entry_updated
    from ..memory import ops as memory_ops
    from ..memory.timestamps import iso_to_ms as _iso_to_ms
    from ..projections import MemoryEntrySummary

    agent = deps.agent
    app_state = deps.app_state
    store = app_state.memory.memory_store

    result = memory_ops.memorize(store, type, title, body, related, entry_id)

    eid = result.get("entry_id")
    if eid is not None:
        seq = f"{eid:04d}"
        summary = MemoryEntrySummary(
            seq=seq,
            type=result.get("type", type),
            title=title,
            created_ms=_iso_to_ms(result.get("created", "")),
            modified_ms=_iso_to_ms(result.get("modified", "")),
        )
        builder = (
            build_memory_entry_created
            if result.get("op") == "created"
            else build_memory_entry_updated
        )
        app_state.projection_store.push_event(
            "memory_entry_created" if result.get("op") == "created" else "memory_entry_updated",
            builder(summary.to_wire()),
            agent_id=agent.agent_id,
        )

    return json.dumps(result)


async def forget_core(deps: ToolDeps, entry_id: int, type: str | None = None) -> str:
    """Core logic for koan_forget.

    Delegates to memory_ops.forget and emits memory_entry_deleted.
    Returns a JSON string of the result dict.

    Re-raises EntryNotFoundError, TypeMismatchError, and ValueError.
    """
    import json

    from ..events import build_memory_entry_deleted
    from ..memory import ops as memory_ops

    agent = deps.agent
    app_state = deps.app_state
    store = app_state.memory.memory_store

    result = memory_ops.forget(store, entry_id, type)

    seq = f"{result.get('entry_id', entry_id):04d}"
    app_state.projection_store.push_event(
        "memory_entry_deleted",
        build_memory_entry_deleted(seq),
        agent_id=agent.agent_id,
    )

    return json.dumps(result)


async def memory_status_core(deps: ToolDeps, type: str | None = None) -> str:
    """Core logic for koan_memory_status.

    Delegates to memory_ops.status (may regenerate summary.md just-in-time)
    and emits memory_summary_updated when regeneration occurred.
    Returns a JSON string of the result dict.

    Re-raises ValueError for invalid type values.
    """
    import json

    from ..events import build_memory_summary_updated
    from ..memory import ops as memory_ops

    agent = deps.agent
    app_state = deps.app_state
    store = app_state.memory.memory_store

    result = await memory_ops.status(store, type=type)

    if result.get("regenerated"):
        app_state.projection_store.push_event(
            "memory_summary_updated",
            build_memory_summary_updated(result.get("summary", "")),
            agent_id=agent.agent_id,
        )

    return json.dumps(result)


async def search_core(
    deps: ToolDeps,
    query: str,
    type: str | None = None,
    k: int = 5,
) -> str:
    """Core logic for koan_search.

    Validates the type filter, then delegates to retrieval_search.
    Returns a JSON string with a "results" list.

    Raises ValueError("invalid type: ...") for unknown memory type values.
    Re-raises RuntimeError on search failures.

    Imports retrieval_search via mcp_endpoint's module namespace so that
    monkeypatching mcp_endpoint.retrieval_search in tests is visible here.
    The lazy import inside the function body re-evaluates the module attribute
    on each call, picking up any active monkeypatch.
    """
    import json

    from ..memory.types import MEMORY_TYPES

    # Import via mcp_endpoint rather than directly from memory.retrieval so
    # that tests patching mcp_endpoint.retrieval_search see the mock here too.
    # The existing _compute_memory_injection_core uses the same pattern for
    # _compose_rag_anchor.
    from ..web.mcp_endpoint import retrieval_search

    app_state = deps.app_state

    if type is not None and type not in MEMORY_TYPES:
        raise ValueError(f"invalid type: {type!r}")

    index = app_state.memory.retrieval_index
    results = await retrieval_search(index, query, k=k, type_filter=type)
    out = {
        "results": [
            {
                "entry_id": r.entry_id,
                "title": r.entry.title,
                "type": r.entry.type,
                "score": r.score,
                "created": r.entry.created,
                "modified": r.entry.modified,
                "body": r.entry.body,
            }
            for r in results
        ]
    }
    return json.dumps(out)


async def reflect_core(
    deps: ToolDeps,
    question: str,
    context: str | None = None,
) -> str:
    """Core logic for koan_reflect.

    Runs run_reflect_agent with a trace callback that emits reflect_delta
    projection events for text-kind deltas (keeping the live streaming feed
    in sync). Returns a JSON string with answer, citations, and iterations.

    Re-raises IterationCapExceeded and RuntimeError so callers can map them
    to their error shapes.
    """
    import json

    from ..events import build_reflect_delta
    from ..memory.retrieval import ReflectTraceEvent, run_reflect_agent

    agent = deps.agent
    app_state = deps.app_state

    # Only text-kind deltas flow into the projection feed; other kinds (search,
    # done, thinking) are consumed by /api/memory/reflect instead.
    def _on_trace(ev: ReflectTraceEvent) -> None:
        if ev.kind != "text" or not ev.delta:
            return
        app_state.projection_store.push_event(
            "reflect_delta",
            build_reflect_delta(ev.delta),
            agent_id=agent.agent_id,
        )

    index = app_state.memory.retrieval_index
    result = await run_reflect_agent(index, question, context=context, on_trace=_on_trace)
    out = {
        "answer": result.answer,
        "citations": [
            {"id": c.id, "title": c.title, "type": c.type, "modifiedMs": c.modified_ms}
            for c in result.citations
        ],
        "iterations": result.iterations,
    }
    return json.dumps(out)


# -- Artifact tool cores -------------------------------------------------------


async def artifact_write_core(deps: ToolDeps, filename: str, content: str) -> str:
    """Core logic for koan_artifact_write.

    Validates filename, resolves the run directory, writes the artifact
    atomically (with managed frontmatter), and emits an artifact_diff event.
    Returns a JSON string {"ok": true, "filename": "..."}.

    Raises ValueError("invalid_filename: ...") for non-conforming filenames.
    Raises ValueError("no_run_dir: ...") when no run directory is available.
    """
    import json
    from pathlib import Path

    from ..artifacts import write_artifact_atomic
    from ..driver import _push_artifact_diff

    # Lazy import avoids a module-level dependency on mcp_endpoint from tools.
    # _validate_artifact_filename and _FILENAME_PATTERN live there until M9.
    from ..web.mcp_endpoint import _validate_artifact_filename

    agent = deps.agent
    app_state = deps.app_state

    err = _validate_artifact_filename(filename)
    if err:
        raise ValueError(f"invalid_filename: {err}")

    run_dir = _resolve_run_dir_core(agent, app_state)
    if not run_dir:
        raise ValueError("no_run_dir: No run directory available")

    target = Path(run_dir) / filename
    write_artifact_atomic(target, content or "")
    _push_artifact_diff(app_state)

    return json.dumps({"ok": True, "filename": filename})


async def artifact_edit_core(
    deps: ToolDeps,
    filename: str,
    old_string: str,
    new_string: str,
) -> str:
    """Core logic for koan_artifact_edit.

    Validates filename and edit parameters, resolves the run directory, reads
    the artifact body (stripping frontmatter), applies a single-occurrence
    replace, and re-writes via write_artifact_atomic. Emits artifact_diff.
    Returns a JSON string {"ok": true, "filename": "..."}.

    Error codes (all raised as ValueError("code: message")):
        invalid_filename, invalid_edit, no_run_dir, not_found, no_match,
        multiple_matches.
    """
    import json
    import os
    from pathlib import Path

    from ..artifacts import split_frontmatter, write_artifact_atomic
    from ..driver import _push_artifact_diff
    from ..web.mcp_endpoint import _validate_artifact_filename

    agent = deps.agent
    app_state = deps.app_state

    err = _validate_artifact_filename(filename)
    if err:
        raise ValueError(f"invalid_filename: {err}")

    if not old_string:
        raise ValueError("invalid_edit: old_string must be non-empty")
    if old_string == new_string:
        raise ValueError(
            "invalid_edit: old_string and new_string are identical; no edit to apply"
        )

    run_dir = _resolve_run_dir_core(agent, app_state)
    if not run_dir:
        raise ValueError("no_run_dir: No run directory available")

    target = Path(run_dir) / filename
    if not target.is_file():
        raise ValueError(f"not_found: {filename} not found")

    raw = target.read_text(encoding="utf-8")
    _, body = split_frontmatter(raw)

    count = body.count(old_string)
    if count == 0:
        raise ValueError("no_match: old_string not found in artifact body")
    if count > 1:
        raise ValueError(
            f"multiple_matches: {count} occurrences found; old_string must match exactly one"
        )

    new_body = body.replace(old_string, new_string, 1)
    write_artifact_atomic(target, new_body)
    _push_artifact_diff(app_state)

    return json.dumps({"ok": True, "filename": filename})


async def artifact_list_core(deps: ToolDeps) -> str:
    """Core logic for koan_artifact_list.

    Resolves the run directory and returns a JSON string {"artifacts": [...]}.
    Returns an empty list when no run directory is available (safe for all roles).
    """
    import json

    from ..artifacts import list_artifacts

    agent = deps.agent
    app_state = deps.app_state

    run_dir = _resolve_run_dir_core(agent, app_state)
    if not run_dir:
        return json.dumps({"artifacts": []})

    artifacts = list_artifacts(run_dir)
    return json.dumps({"artifacts": artifacts})


async def artifact_view_core(deps: ToolDeps, filename: str) -> str:
    """Core logic for koan_artifact_view.

    Resolves the run directory, guards against path traversal, reads the
    artifact body (stripping driver-managed frontmatter), and returns it.

    Raises ValueError("no_run_dir: ..."), ValueError("invalid_path: ..."),
    or ValueError("not_found: ...") on failure.
    """
    import os
    from pathlib import Path

    from ..artifacts import split_frontmatter

    agent = deps.agent
    app_state = deps.app_state

    run_dir = _resolve_run_dir_core(agent, app_state)
    if not run_dir:
        raise ValueError("no_run_dir: No run directory available")

    # Path-traversal guard: resolve and verify containment.
    run_root = Path(run_dir).resolve()
    target = (run_root / filename).resolve()
    if target != run_root and not str(target).startswith(str(run_root) + os.sep):
        raise ValueError("invalid_path: filename escapes run_dir")

    if not target.is_file():
        raise ValueError(f"not_found: {filename} not found")

    # Strip driver-managed frontmatter: LLMs should see the body only;
    # exposing frontmatter would invite the model to reproduce it.
    raw = target.read_text(encoding="utf-8")
    _, body = split_frontmatter(raw)
    return body


# -- Interaction tool cores ----------------------------------------------------


async def ask_question_core(deps: ToolDeps, questions: list[dict]) -> str:
    """Core logic for koan_ask_question -- async blocking part plus Q/A formatting.

    Enqueues the ask interaction (which emits the questions_asked projection
    event via enqueue_interaction -> _emit_interaction_request) then parks on
    the future.  Under yolo, the future is pre-resolved with synthesised
    answers from _yolo_ask_answer before the await, so the call returns
    without blocking on a user POST.

    Returns a plain-text Q/A string.  The MCP handler adds per-answer
    attachment blocks on top; the in-process pydantic-ai tool returns this
    string directly to the model.

    Raises RuntimeError when the interaction queue is full (converted from the
    fastmcp ToolError so the in-process path gets a clean exception type).
    """
    agent = deps.agent
    app_state = deps.app_state

    # enqueue_interaction also emits the questions_asked projection event.
    from ..web.interactions import enqueue_interaction
    try:
        future = await enqueue_interaction(agent, app_state, "ask", {"questions": questions or []})
    except Exception as exc:
        # enqueue_interaction raises ToolError (fastmcp) when the queue is full;
        # convert to RuntimeError so pydantic-ai does not see a foreign exception type.
        raise RuntimeError(f"ask_question_enqueue_failed: {exc}") from exc

    if app_state.server.yolo:
        # Pre-resolve before awaiting so no event-loop park occurs.
        from ..agents.loop import _yolo_ask_answer
        future.set_result(_yolo_ask_answer(questions or []))

    result = await future

    if isinstance(result, dict) and "error" in result:
        raise RuntimeError(f"{result['error']}: {result.get('message', '')}")

    answers = result.get("answers", []) if isinstance(result, dict) else []
    questions_list = questions or []
    parts = []
    for i, a in enumerate(answers):
        q_text = questions_list[i].get("question", f"Q{i+1}") if i < len(questions_list) else f"Q{i+1}"
        a_text = a.get("answer", "") if isinstance(a, dict) else str(a)
        parts.append(f"Q: {q_text}\nA: {a_text}")
    return "\n\n".join(parts) if parts else "No answers provided."


async def propose_memory_core(
    deps: ToolDeps,
    proposals: list[dict],
    context_note: str = "",
) -> tuple[str, list[dict]]:
    """Core logic for koan_memory_propose.

    Validates proposals, enforces the reentry guard, creates an
    ActiveCurationBatch, emits memory_curation_started, then:
    - Yolo path: synthesises an all-approved payload via
      _yolo_memory_propose_response and returns (yolo_text, []).
    - Interactive path: parks on memory_propose_future (resolved by
      api_memory_curation_submit), calls _render_curation_payload to build
      the JSON payload, and returns (json_text, decisions_list).

    Emits memory_curation_cleared after the future resolves (or in the yolo
    path).  The reentry guard raises RuntimeError when a prior proposal is
    still pending.

    Returns (curation_payload_json_text, raw_decisions_list).  The MCP
    handler uses both -- the JSON text as the primary block and the decisions
    list to attach per-decision file blocks.  The in-process tool discards
    the decisions list and returns only the JSON text.
    """
    import asyncio
    import uuid

    from ..projections import ActiveCurationBatch, Proposal

    agent = deps.agent
    app_state = deps.app_state

    if not proposals:
        raise ValueError("proposals must be a non-empty list")

    validated: list[Proposal] = []
    for p in proposals:
        try:
            validated.append(Proposal.model_validate(p))
        except Exception as exc:
            raise ValueError(f"proposal validation failed: {exc}") from exc

    # Reentry guard: refuse if a prior propose is still unresolved.
    existing = app_state.interactions.memory_propose_future
    if existing is not None and not existing.done():
        raise RuntimeError(
            "propose_already_pending: a prior memory proposal is still awaiting "
            "review; resolve it before calling koan_memory_propose again."
        )

    batch = ActiveCurationBatch(
        proposals=validated,
        batch_id=uuid.uuid4().hex,
        context_note=context_note,
    )

    from ..events import build_memory_curation_cleared, build_memory_curation_started
    app_state.projection_store.push_event(
        "memory_curation_started",
        build_memory_curation_started(batch.to_wire()),
        agent_id=agent.agent_id,
    )

    if app_state.server.yolo:
        from ..web.mcp_endpoint import _yolo_memory_propose_response
        yolo_text = _yolo_memory_propose_response(batch)
        app_state.projection_store.push_event(
            "memory_curation_cleared",
            build_memory_curation_cleared(),
            agent_id=agent.agent_id,
        )
        return (yolo_text, [])

    loop = asyncio.get_running_loop()
    future = loop.create_future()
    app_state.interactions.memory_propose_future = future
    try:
        decisions = await future
    finally:
        # Always clear so the guard resets even on cancellation / error.
        app_state.interactions.memory_propose_future = None

    if not isinstance(decisions, list):
        decisions = []

    run_dir = _resolve_run_dir_core(agent, app_state) or ""
    from ..web.mcp_endpoint import _render_curation_payload
    blocks, _ = _render_curation_payload(
        batch, decisions,
        app_state.uploads, run_dir, agent.runner_type,
    )
    json_text = blocks[0].text if blocks else "{}"

    app_state.projection_store.push_event(
        "memory_curation_cleared",
        build_memory_curation_cleared(),
        agent_id=agent.agent_id,
    )

    return (json_text, decisions)


# -- Full koan toolset builder -------------------------------------------------


def build_koan_toolset(allowed_names: "frozenset[str] | None" = None) -> Any:
    """Build a koan FunctionToolset with all 18 implemented koan tools.

    Registers koan_complete_step, koan_set_phase (M2), the 14 M3 tools
    (koan_set_workflow; the 4 story tools; the 5 memory tools; the 4 artifact
    tools), and the 2 M5 in-process interaction tools (koan_ask_question,
    koan_memory_propose).  The 2 deferred tools (koan_request_executor,
    koan_request_scouts) land in M6 when in-process subagent spawning is built.

    Args:
        allowed_names: When provided, only tools whose names are in this set
            are registered.  Pass compose_toolset(policy, role, phase) here to
            get a phase-correct toolset.  When None, all 16 implemented tools
            are registered (useful for tests that want the full vocabulary).

    Returns a FunctionToolset[ToolDeps].
    """
    from pydantic_ai.toolsets.function import FunctionToolset

    ts: FunctionToolset[ToolDeps] = FunctionToolset()

    # _reg is a local helper that respects the optional allowed_names filter.
    # All tool inner functions omit the ctx annotation for the same reason as
    # build_minimal_koan_toolset: 'from __future__ import annotations' turns
    # annotations into strings resolved against module globals, and RunContext
    # is not in module globals.  takes_ctx=True in add_function() informs
    # pydantic-ai without triggering get_type_hints() resolution.
    def _reg(func: Any, name: str, description: str) -> None:
        if allowed_names is None or name in allowed_names:
            ts.add_function(func, takes_ctx=True, name=name, description=description)

    # ---- M2 tools ----

    async def _koan_complete_step(ctx, thoughts: str = "") -> str:
        """Advance the step machine and receive guidance for the current step."""
        return await advance_step(ctx.deps, thoughts)

    async def _koan_set_phase(ctx, phase: str) -> str:
        """Transition to a new workflow phase, or tombstone the workflow with 'done'."""
        return await apply_set_phase(ctx.deps, phase)

    _reg(
        _koan_complete_step,
        "koan_complete_step",
        (
            "Advance the step machine and receive guidance for the current step. "
            "Call this at the start of each agent turn to receive your instructions. "
            "Pass optional reflective thoughts as the 'thoughts' argument."
        ),
    )
    _reg(
        _koan_set_phase,
        "koan_set_phase",
        (
            "Commit transition to the next workflow phase. Call after the user "
            "has confirmed a direction. The next koan_complete_step call delivers "
            "the new phase's first-step guidance. Pass 'done' to end the workflow."
        ),
    )

    # ---- M3: workflow tool ----

    async def _koan_set_workflow(ctx, workflow: str) -> str:
        """Switch the active workflow mid-run, preserving all run-directory context."""
        return await apply_set_workflow(ctx.deps, workflow)

    _reg(
        _koan_set_workflow,
        "koan_set_workflow",
        (
            "Switch the active workflow mid-run. The new workflow's initial_phase "
            "becomes active; call koan_complete_step to begin. "
            "Pass a workflow name registered in koan/lib/workflows.py."
        ),
    )

    # ---- M3: story tools ----

    async def _koan_select_story(ctx, story_id: str) -> str:
        """Select the next story for execution."""
        return await select_story(ctx.deps, story_id)

    async def _koan_complete_story(ctx, story_id: str) -> str:
        """Mark a story as successfully verified and completed."""
        return await complete_story(ctx.deps, story_id)

    async def _koan_retry_story(ctx, story_id: str, failure_summary: str) -> str:
        """Send a story back for retry with a detailed failure summary."""
        return await retry_story(ctx.deps, story_id, failure_summary)

    async def _koan_skip_story(ctx, story_id: str, reason: str = "") -> str:
        """Skip a story that is superseded or no longer needed."""
        return await skip_story(ctx.deps, story_id, reason)

    _reg(_koan_select_story, "koan_select_story", "Select the next story for execution.")
    _reg(_koan_complete_story, "koan_complete_story", "Mark a story as successfully verified and completed.")
    _reg(
        _koan_retry_story,
        "koan_retry_story",
        "Send a story back for retry with a detailed failure summary.",
    )
    _reg(
        _koan_skip_story,
        "koan_skip_story",
        "Skip a story that is superseded or no longer needed.",
    )

    # ---- M3: memory tools ----

    async def _koan_memorize(
        ctx,
        type: str,
        title: str,
        body: str,
        related: list[str] | None = None,
        entry_id: int | None = None,
    ) -> str:
        """Write a memory entry.

        Creates a new entry when entry_id is omitted. Updates an existing
        entry when entry_id is provided.
        """
        return await memorize_core(ctx.deps, type, title, body, related, entry_id)

    async def _koan_forget(ctx, entry_id: int, type: str | None = None) -> str:
        """Remove a memory entry. Deletes the entry file from disk."""
        return await forget_core(ctx.deps, entry_id, type)

    async def _koan_memory_status(ctx, type: str | None = None) -> str:
        """Get an orientation view of project memory."""
        return await memory_status_core(ctx.deps, type)

    async def _koan_search(ctx, query: str, type: str | None = None, k: int = 5) -> str:
        """Search memory entries by semantic similarity."""
        return await search_core(ctx.deps, query, type, k)

    async def _koan_reflect(ctx, question: str, context: str | None = None) -> str:
        """Synthesize a cited briefing over project memory."""
        return await reflect_core(ctx.deps, question, context)

    _reg(
        _koan_memorize,
        "koan_memorize",
        (
            "Write a memory entry. Creates a new entry when entry_id is omitted; "
            "updates when entry_id is provided. Args: type, title, body, related, entry_id."
        ),
    )
    _reg(
        _koan_forget,
        "koan_forget",
        "Remove a memory entry by sequence number (entry_id). Optionally assert type.",
    )
    _reg(
        _koan_memory_status,
        "koan_memory_status",
        "Get project memory summary and entry listing. Optionally filter by type.",
    )
    _reg(
        _koan_search,
        "koan_search",
        (
            "Search memory entries by semantic similarity. "
            "Args: query (str), type (optional filter), k (number of results, default 5)."
        ),
    )
    _reg(
        _koan_reflect,
        "koan_reflect",
        (
            "Synthesize a cited briefing over project memory using an LLM loop. "
            "Args: question (str), context (optional str)."
        ),
    )

    # ---- M3: artifact tools ----

    async def _koan_artifact_write(ctx, filename: str, content: str) -> str:
        """Write or update an artifact file. Full-rewrite semantics with managed frontmatter."""
        return await artifact_write_core(ctx.deps, filename, content)

    async def _koan_artifact_edit(
        ctx,
        filename: str,
        old_string: str,
        new_string: str,
    ) -> str:
        """Surgical in-place edit of an artifact body. Single-unique-match semantics."""
        return await artifact_edit_core(ctx.deps, filename, old_string, new_string)

    async def _koan_artifact_list(ctx) -> str:
        """List artifacts in the run directory."""
        return await artifact_list_core(ctx.deps)

    async def _koan_artifact_view(ctx, filename: str) -> str:
        """Return the full text content of an artifact (frontmatter stripped)."""
        return await artifact_view_core(ctx.deps, filename)

    _reg(
        _koan_artifact_write,
        "koan_artifact_write",
        (
            "Write or update an artifact file. Driver manages YAML frontmatter. "
            "Args: filename (must match [a-z0-9][a-z0-9_-]*.md), content (markdown body)."
        ),
    )
    _reg(
        _koan_artifact_edit,
        "koan_artifact_edit",
        (
            "Surgical single-occurrence edit of an artifact body. "
            "Strips frontmatter before matching. Args: filename, old_string, new_string."
        ),
    )
    _reg(
        _koan_artifact_list,
        "koan_artifact_list",
        "List run-directory artifacts with path, size, and modification time.",
    )
    _reg(
        _koan_artifact_view,
        "koan_artifact_view",
        "Return the full body of an artifact (driver frontmatter stripped). Arg: filename.",
    )

    # ---- M5: in-process interaction tools ----
    # koan_ask_question and koan_memory_propose park on futures resolved by the
    # surviving web endpoints (/api/interact and /api/memory/curation).
    # The cores live in this module; the MCP handlers delegate to them.

    async def _koan_ask_question(ctx, questions: list[dict] | None = None) -> str:
        """Ask the user one or more clarifying questions and return the answers."""
        return await ask_question_core(ctx.deps, questions or [])

    async def _koan_memory_propose(
        ctx,
        proposals: list[dict],
        context_note: str = "",
    ) -> str:
        """Propose memory entries for user review; return the curation payload JSON."""
        json_text, _ = await propose_memory_core(ctx.deps, proposals, context_note)
        return json_text

    _reg(
        _koan_ask_question,
        "koan_ask_question",
        (
            "Ask the user one or more clarifying questions and receive answers. "
            "Blocks until the user responds (or yolo auto-answers). "
            "Args: questions (list of {question, options, context?, multi?})."
        ),
    )
    _reg(
        _koan_memory_propose,
        "koan_memory_propose",
        (
            "Propose one or more memory entries to the user for approval; block until "
            "they submit decisions. Returns a JSON payload with per-proposal decisions. "
            "Args: proposals (list of proposal dicts), context_note (optional str)."
        ),
    )

    return ts


# -- PydanticAI toolset builder ------------------------------------------------


def build_minimal_koan_toolset() -> Any:
    """Backwards-compatible alias: build a toolset with only koan_complete_step and koan_set_phase.

    Kept for M2 compatibility; callers that need the full 16-tool set should
    use build_koan_toolset() directly.  PydanticAIAgent.run() switched to
    build_koan_toolset() in M3; this alias avoids breaking any remaining
    import sites.
    """
    # Filter to only the two M2 tools so callers that relied on the minimal
    # set continue to see exactly the same vocabulary.
    return build_koan_toolset(allowed_names=frozenset({"koan_complete_step", "koan_set_phase"}))
