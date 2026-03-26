# MCP endpoint -- fastmcp server with permission-fenced tool handlers.
#
# Exposes build_mcp_asgi_app() which returns an ASGI sub-app that:
#   1. Validates agent_id from query params before reaching fastmcp.
#   2. Runs check_permission() on every tool call.
#   3. Implements koan_complete_step, koan_set_confidence, koan_request_scouts.

from __future__ import annotations

import asyncio
import json
import uuid
from contextvars import ContextVar
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import parse_qs

import aiofiles
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from ..epic_state import ensure_subagent_directory
from ..lib.permissions import check_permission
from ..logger import get_logger
from ..phases.format_step import format_step
from ..runners import resolve_runner

if TYPE_CHECKING:
    from ..state import AgentState, AppState

log = get_logger("mcp")

# Request-scoped agent state, set by the ASGI wrapper before fastmcp runs.
_agent_ctx: ContextVar[AgentState | None] = ContextVar("_agent_ctx", default=None)

# Module-level app_state reference, set by build_mcp_asgi_app().
_app_state: AppState | None = None

# -- fastmcp server -----------------------------------------------------------

mcp = FastMCP(name="koan")


def _check_or_raise(agent: AgentState, tool_name: str, tool_args: dict | None = None) -> None:
    phase_ctx = agent.phase_ctx
    resolved_epic_dir = (
        phase_ctx.epic_dir if phase_ctx is not None and phase_ctx.epic_dir
        else agent.epic_dir or None
    )
    result = check_permission(
        role=agent.role,
        tool_name=tool_name,
        epic_dir=resolved_epic_dir,
        tool_args=tool_args,
        current_step=agent.step,
    )
    if not result["allowed"]:
        raise ToolError(
            json.dumps({"error": "permission_denied", "message": result["reason"]})
        )


def _get_agent() -> AgentState:
    agent = _agent_ctx.get()
    if agent is None:
        raise ToolError(
            json.dumps({"error": "permission_denied", "message": "No agent context"})
        )
    return agent


# -- Tool implementations -----------------------------------------------------

@mcp.tool(name="koan_complete_step")
async def koan_complete_step(thoughts: str = "") -> str:
    agent = _get_agent()
    _check_or_raise(agent, "koan_complete_step", {"thoughts": thoughts})

    # Mark handshake observed (decoupled from stream parsing)
    agent.handshake_observed = True

    phase_module = agent.phase_module
    ctx = agent.phase_ctx
    current_step = agent.step

    # Validate current step completion
    err = phase_module.validate_step_completion(current_step, ctx)
    if err:
        raise ToolError(
            json.dumps({"error": "step_validation_failed", "message": err})
        )

    # Get next step
    next_step = phase_module.get_next_step(current_step, ctx)

    # Loop-back handling
    if next_step is not None and next_step <= current_step:
        await phase_module.on_loop_back(current_step, next_step, ctx)

    # Advance step
    agent.step = next_step if next_step is not None else current_step

    # Determine step name for audit
    step_names = getattr(phase_module, "STEP_NAMES", {})
    step_name = step_names.get(next_step if next_step is not None else current_step, "")

    # Emit audit event
    if agent.event_log is not None:
        await agent.event_log.emit_step_transition(
            next_step if next_step is not None else current_step,
            step_name,
            phase_module.TOTAL_STEPS,
        )

    # Return guidance or completion signal
    if next_step is None:
        return "Phase complete."

    guidance = phase_module.step_guidance(next_step, ctx)
    return format_step(guidance)


@mcp.tool(name="koan_set_confidence")
async def koan_set_confidence(level: str = "") -> str:
    agent = _get_agent()
    _check_or_raise(agent, "koan_set_confidence", {"level": level})

    valid_levels = {"high", "medium", "low"}
    if level not in valid_levels:
        raise ToolError(
            json.dumps({"error": "invalid_confidence", "message": f"level must be one of {valid_levels}"})
        )

    agent.phase_ctx.intake_confidence = level
    return f"Confidence set to {level}."


@mcp.tool(name="koan_request_scouts")
async def koan_request_scouts(questions: list[dict] | None = None) -> str:
    agent = _get_agent()
    _check_or_raise(agent, "koan_request_scouts", {"questions": questions})

    if not questions:
        return "No scouts requested."

    assert _app_state is not None, "app_state not initialized"

    semaphore = asyncio.Semaphore(_app_state.config.scout_concurrency)
    epic_dir = agent.phase_ctx.epic_dir

    scout_tasks = []
    for q in questions:
        scout_id = q.get("id", str(uuid.uuid4())[:8])
        subagent_dir = await ensure_subagent_directory(
            epic_dir, f"scout-{scout_id}-{uuid.uuid4().hex[:8]}"
        )
        scout_tasks.append({
            "role": "scout",
            "epic_dir": epic_dir,
            "subagent_dir": subagent_dir,
            "question": q.get("prompt", ""),
            "output_file": "findings.md",
            "investigator_role": q.get("role", "investigator"),
        })

    async def run_scout(scout_task: dict) -> str | None:
        async with semaphore:
            from ..subagent import spawn_subagent

            runner = resolve_runner("scout", _app_state.config, scout_task["subagent_dir"])
            exit_code = await spawn_subagent(scout_task, _app_state, runner)

            # Require state.json with status=="completed" (regardless of exit code)
            state_path = Path(scout_task["subagent_dir"]) / "state.json"
            try:
                async with aiofiles.open(state_path, "r") as f:
                    projection = json.loads(await f.read())
            except (FileNotFoundError, json.JSONDecodeError):
                return None
            if projection.get("status") != "completed":
                return None

            # Read findings
            findings_path = Path(scout_task["subagent_dir"]) / "findings.md"
            try:
                async with aiofiles.open(findings_path, "r") as f:
                    return await f.read()
            except FileNotFoundError:
                return None

    results = await asyncio.gather(*[run_scout(t) for t in scout_tasks])
    findings = [r for r in results if r is not None]

    if not findings:
        return "No findings returned."

    return "\n\n---\n\n".join(findings)


@mcp.tool(name="koan_ask_question")
def koan_ask_question(question: str = "") -> str:
    agent = _get_agent()
    _check_or_raise(agent, "koan_ask_question", {"question": question})
    return "[stub] koan_ask_question: not yet implemented"


@mcp.tool(name="koan_review_artifact")
def koan_review_artifact(artifact: str = "") -> str:
    agent = _get_agent()
    _check_or_raise(agent, "koan_review_artifact", {"artifact": artifact})
    return "[stub] koan_review_artifact: not yet implemented"


@mcp.tool(name="koan_propose_workflow")
def koan_propose_workflow(workflow: str = "") -> str:
    agent = _get_agent()
    _check_or_raise(agent, "koan_propose_workflow", {"workflow": workflow})
    return "[stub] koan_propose_workflow: not yet implemented"


@mcp.tool(name="koan_set_next_phase")
def koan_set_next_phase(phase: str = "") -> str:
    agent = _get_agent()
    _check_or_raise(agent, "koan_set_next_phase", {"phase": phase})
    return "[stub] koan_set_next_phase: not yet implemented"


# -- ASGI wrapper --------------------------------------------------------------

def build_mcp_asgi_app(app_state: AppState):
    """Return an ASGI app that validates agent_id then delegates to fastmcp."""
    global _app_state
    _app_state = app_state

    inner = mcp.http_app()

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

            token = _agent_ctx.set(agent)
            try:
                await inner(scope, receive, send)
            finally:
                _agent_ctx.reset(token)
        else:
            await inner(scope, receive, send)

    return asgi_wrapper
