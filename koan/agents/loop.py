# Multi-turn agent loop: run_agent_loop.
#
# Owns the multi-turn conversation lifecycle for the primary orchestrator:
# each turn is one agent.iter() run; a terminal-text turn (End node, no
# outstanding tool calls initiated) is the hand-back signal -- the loop
# parks on a loop-owned yield_future (resolved by api_chat) and resumes
# on the next user message.
#
# Pure yolo/directed helpers are relocated here from mcp_endpoint.py so both
# the loop hand-back and the in-process ask tool can reuse them without
# importing from the web layer.
#
# Steering is injected between graph nodes (after CallToolsNode, before the
# next ModelRequestNode) via agent_run.enqueue(), satisfying the tool-call /
# tool-result adjacency constraint.

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any, AsyncIterator

if TYPE_CHECKING:
    from ..agents.base import AgentOptions
    from .events import StreamEvent
    from ..state import AgentState, AppState
    from ..tools.koan_tools import ToolDeps


# -- Pure yolo/directed helpers -----------------------------------------------
# Relocated verbatim from koan/web/mcp_endpoint.py; keeping them here makes
# both the loop hand-back and the in-process koan_ask_question core importable
# without pulling in the web layer.


def _yolo_yield_response(suggestions: list[dict] | None) -> str:
    """Return the auto-response text for a hand-back when running in yolo mode.

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


# -- Steering helper -----------------------------------------------------------


def drain_and_render_steering(
    app_state: AppState,
    agent: AgentState | None,
) -> str | None:
    """Drain the steering queue and render non-empty messages as a plain string.

    Returns a formatted steering-envelope string suitable for
    agent_run.enqueue() injection (pydantic-ai treats a plain string as a
    UserPromptPart). Returns None when there are no messages to inject.

    Uses render_text (text-only path) rather than render_blocks (ContentBlock
    path) because agent_run.enqueue() accepts str, not MCP ContentBlocks.
    """
    from ..agents.steering import drain_for_primary, render_text
    messages = drain_for_primary(app_state, agent)
    if not messages:
        return None
    from ..logger import get_logger
    log = get_logger("loop")
    log.info(
        "steering injected between nodes | agent=%s count=%d",
        agent.agent_id[:8] if agent else "?",
        len(messages),
    )
    # Emit steering_delivered projection event so the dashboard tracks delivery.
    ts_ms_list = [m.timestamp_ms for m in messages]
    delivery_ms = int(time.time() * 1000)
    from ..events import build_steering_delivered
    app_state.projection_store.push_event(
        "steering_delivered",
        build_steering_delivered(len(messages), ts_ms_list, delivery_ms),
    )
    return render_text(messages)


def assemble_resume_prompt(
    messages: list[Any],
    app_state: AppState,
    runner_type: str,
) -> tuple[str, list[dict]]:
    """Build the next-turn prompt + attachment manifest from buffered messages.

    This is the in-process replacement for the koan_yield tool result: when the
    loop resumes after a terminal-text hand-back, the buffered user messages
    become the next prompt. Attachments are delivered as TEXT appended to the
    prompt -- the loop carries a single string, so only the text content of
    upload_ids_to_blocks survives (full binary/image delivery to multimodal
    models is a documented follow-up: it needs multimodal content plumbing on
    the agent.iter prompt and live verification).

    Returns (turn_prompt, manifest) where manifest is the upload audit manifest
    (for the tool_attachments projection event the caller re-emits). Falls back
    to ("proceed", []) when no messages were buffered.
    """
    if not messages:
        return "proceed", []

    from ..phases.format_step import format_user_messages
    from mcp.types import TextContent

    blocks = format_user_messages(messages)
    turn_prompt = "\n\n".join(
        b.text for b in blocks if isinstance(b, TextContent)
    )
    manifest: list[dict] = []
    for msg in messages:
        if msg.attachments and app_state.run.run_dir:
            from ..web.uploads import upload_ids_to_blocks
            attach_blocks, msg_manifest = upload_ids_to_blocks(
                app_state.uploads,
                app_state.run.run_dir,
                msg.attachments,
                runner_type,
            )
            manifest.extend(msg_manifest)
            extra = "\n\n".join(
                b.text for b in attach_blocks if isinstance(b, TextContent)
            )
            if extra:
                turn_prompt = f"{turn_prompt}\n\n{extra}"
    return turn_prompt, manifest


# -- Multi-turn loop -----------------------------------------------------------


async def run_agent_loop(
    pai_agent: Any,
    deps: ToolDeps,
    options: AgentOptions,
    app_state: AppState,
    agent_state: AgentState,
) -> AsyncIterator[StreamEvent]:
    """Drive the multi-turn agent loop, yielding StreamEvents for spawn_subagent.

    Each iteration is one agent.iter() run (one "turn"). The loop terminates
    when:
      - app_state.run.workflow_done is True (after koan_set_phase("done")), OR
      - agent_state.is_primary is False (scouts/executors run one turn and exit).

    At each turn end (End node):
      - If workflow_done: terminate.
      - If is_primary: terminal-text hand-back -- emit yield_started, park on
        yield_future (resolved by api_chat), drain user messages, and re-run with
        the user message as the next prompt. Under yolo, synthesize the prompt
        from _directed_yolo_response or _yolo_yield_response without parking.
      - Else (scout/executor): terminate.

    Steering injection: after each CallToolsNode completes, drain_and_render_steering
    is called. Non-empty result is injected via agent_run.enqueue() which delivers
    it as a UserPromptPart before the next model request -- never between a tool
    call and its result.

    Message history: agent_state.message_history is updated to agent_run.all_messages()
    after each turn, then passed as message_history= to the next agent.iter() call.
    The first turn receives None (empty history) so pydantic-ai treats it fresh.

    Args:
        pai_agent: The pydantic-ai Agent instance (already constructed with
                   toolsets, capabilities, and model settings).
        deps: ToolDeps(app_state, agent_state) -- passed to agent.iter(deps=).
        options: AgentOptions carrying boot_prompt, system_prompt, and role.
        app_state: Live AppState for interaction state and projection events.
        agent_state: AgentState for history, is_primary, and identity.

    Yields StreamEvents using the same 8-type vocabulary as PydanticAIAgent.run().
    """
    from pydantic_ai._agent_graph import CallToolsNode, End, ModelRequestNode
    from pydantic_ai.messages import (
        FunctionToolResultEvent,
        PartDeltaEvent,
        PartEndEvent,
        PartStartEvent,
        TextPart,
        TextPartDelta,
        ThinkingPartDelta,
        ToolCallPart,
        ToolCallPartDelta,
    )
    from pydantic_ai.usage import RequestUsage

    from .events import StreamEvent

    # First turn uses the boot_prompt; subsequent turns use the user's reply.
    turn_prompt: str | None = options.boot_prompt

    while True:
        # Pass accumulated history so the model has full conversation context.
        # On the first turn, message_history is empty (treated as no history).
        history = agent_state.message_history if agent_state.message_history else None

        run_usage = None
        final_text = ""

        async with pai_agent.iter(
            turn_prompt,
            message_history=history,
            deps=deps,
        ) as agent_run:
            async for node in agent_run:

                if isinstance(node, ModelRequestNode):
                    async with node.stream(agent_run.ctx) as stream:
                        async for ev in stream:
                            if isinstance(ev, PartStartEvent):
                                part = ev.part
                                if isinstance(part, ToolCallPart):
                                    yield StreamEvent(
                                        type="tool_start",
                                        tool_name=part.tool_name,
                                        tool_use_id=part.tool_call_id,
                                        block_index=ev.index,
                                    )
                            elif isinstance(ev, PartDeltaEvent):
                                delta = ev.delta
                                if isinstance(delta, TextPartDelta):
                                    yield StreamEvent(
                                        type="token_delta",
                                        content=delta.content_delta,
                                    )
                                elif isinstance(delta, ThinkingPartDelta):
                                    if delta.content_delta:
                                        yield StreamEvent(
                                            type="thinking",
                                            content=delta.content_delta,
                                            is_thinking=True,
                                        )
                                elif isinstance(delta, ToolCallPartDelta):
                                    if delta.args_delta is not None:
                                        args_str = (
                                            delta.args_delta
                                            if isinstance(delta.args_delta, str)
                                            else str(delta.args_delta)
                                        )
                                        yield StreamEvent(
                                            type="tool_input_delta",
                                            content=args_str,
                                            block_index=ev.index,
                                        )
                            elif isinstance(ev, PartEndEvent):
                                part = ev.part
                                if isinstance(part, ToolCallPart):
                                    yield StreamEvent(
                                        type="tool_stop",
                                        block_index=ev.index,
                                    )
                                if isinstance(part, TextPart) and part.content:
                                    # Capture the full assistant text for the hand-back check.
                                    final_text = part.content
                                    yield StreamEvent(
                                        type="assistant_text",
                                        content=part.content,
                                    )

                elif isinstance(node, CallToolsNode):
                    async with node.stream(agent_run.ctx) as events_iter:
                        async for tool_ev in events_iter:
                            if isinstance(tool_ev, FunctionToolResultEvent):
                                result_part = tool_ev.part
                                tool_name = result_part.tool_name
                                tool_use_id = result_part.tool_call_id
                                raw_content = result_part.content
                                content_str = (
                                    raw_content
                                    if isinstance(raw_content, str)
                                    else str(raw_content) if raw_content is not None
                                    else ""
                                )
                                # Derive metrics mirroring PydanticAIAgent's parser paths.
                                metrics = None
                                if tool_name == "read":
                                    from ..agents.pydantic_ai import _parse_read_result_from_content
                                    metrics = _parse_read_result_from_content(content_str)
                                elif tool_name in ("grep", "glob"):
                                    from ..agents.pydantic_ai import _parse_grep_result_from_content
                                    metrics = _parse_grep_result_from_content(content_str)
                                yield StreamEvent(
                                    type="tool_result",
                                    tool_name=tool_name,
                                    tool_use_id=tool_use_id,
                                    content=content_str,
                                    metrics=metrics,
                                )

                    # Inject steering after all tools in this node finish, before
                    # the next model request.  This satisfies the adjacency constraint:
                    # the steering message lands at a request boundary, not between a
                    # tool call and its result.
                    steering_text = drain_and_render_steering(app_state, agent_state)
                    if steering_text:
                        agent_run.enqueue(steering_text)

                elif isinstance(node, End):
                    run_usage = agent_run.usage
                    request_usage = RequestUsage(
                        input_tokens=run_usage.input_tokens,
                        output_tokens=run_usage.output_tokens,
                        cache_read_tokens=run_usage.cache_read_tokens,
                        cache_write_tokens=run_usage.cache_write_tokens,
                    )
                    yield StreamEvent(
                        type="turn_complete",
                        usage=request_usage,
                    )

            # Persist the full conversation so the next turn has complete context.
            agent_state.message_history = list(agent_run.all_messages())

        # Termination check: workflow completed via koan_set_phase("done").
        if app_state.run.workflow_done:
            return

        # Non-primary agents (scouts/executors) run exactly one turn and exit.
        # They do not park; their result is the final_response in agent_state.
        if not agent_state.is_primary:
            return

        # Primary orchestrator: terminal-text hand-back.
        # Emit yield_started so the UI renders the hand-back card, with the
        # structured next-phase suggestions derived from the workflow (M7.5 --
        # restores the YieldPanel options koan_yield used to carry, without
        # requiring the model to call a tool at the hand-back).
        from ..events import build_yield_started
        from ..lib.workflows import build_phase_suggestions
        workflow = app_state.run.workflow
        suggestions = (
            build_phase_suggestions(workflow, app_state.run.phase)
            if workflow is not None else []
        )
        app_state.projection_store.push_event(
            "yield_started",
            build_yield_started(suggestions),
            agent_id=agent_state.agent_id,
        )

        if app_state.server.yolo:
            # Yolo mode: synthesize the next user message instead of parking.
            # Directed mode steers toward the next phase in the sequence; plain
            # yolo picks from the yield suggestions (none here, so "proceed").
            directed = app_state.server.directed_phases
            if directed is not None:
                turn_prompt = _directed_yolo_response(directed, app_state.run.phase)
            else:
                turn_prompt = _yolo_yield_response(None)
        else:
            # Interactive mode: park on yield_future until api_chat resolves it.
            # Reentry guard: if a prior yield is somehow still pending (should not
            # happen in normal flow), skip rather than create a second future.
            existing = app_state.interactions.yield_future
            if existing is not None and not existing.done():
                from ..logger import get_logger
                get_logger("loop").warning(
                    "yield_future already set (reentry) -- loop skipping park",
                )
                return

            loop = asyncio.get_running_loop()
            future = loop.create_future()
            app_state.interactions.yield_future = future
            await future
            app_state.interactions.yield_future = None

            # Drain the user messages that api_chat buffered and form the next prompt.
            from ..state import drain_user_messages
            messages = drain_user_messages(app_state)
            turn_prompt, attach_manifest = assemble_resume_prompt(
                messages, app_state, agent_state.runner_type,
            )
            # Re-emit tool_attachments so the audit log / UI records what the
            # user attached on resume (M7.5 -- the koan_yield handler used to do
            # this; restored here for the in-process hand-back).
            if attach_manifest:
                from ..events import build_tool_attachments
                app_state.projection_store.push_event(
                    "tool_attachments",
                    build_tool_attachments(attach_manifest),
                    agent_id=agent_state.agent_id,
                )
