# Default-deny role-based permissions for koan subagents.
#
# Permission model:
#   1. READ_TOOLS always allowed for all roles (bash read/write ambiguity accepted).
#   2. ROLE_PERMISSIONS controls koan-specific tools and write/edit access.
#   3. Planning roles have write/edit path-scoped to the epic directory.
#      Only executor has unrestricted write access.
#
# Pure functions -- no I/O, no mutable state.

from __future__ import annotations

from pathlib import Path

from ..logger import get_logger

log = get_logger("permissions")

# -- Constants ----------------------------------------------------------------

READ_TOOLS: frozenset[str] = frozenset({
    "bash", "read", "grep", "glob", "find", "ls",
})

WRITE_TOOLS: frozenset[str] = frozenset({"edit", "write"})

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "intake": frozenset({
        "koan_complete_step",
        "koan_ask_question",
        "koan_request_scouts",
        "koan_review_artifact",
        "koan_set_confidence",
        "edit",
        "write",
    }),
    "scout": frozenset({
        "koan_complete_step",
    }),
    "decomposer": frozenset({
        "koan_complete_step",
        "koan_ask_question",
        "koan_request_scouts",
        "edit",
        "write",
    }),
    "brief-writer": frozenset({
        "koan_complete_step",
        "koan_review_artifact",
        "edit",
        "write",
    }),
    "orchestrator": frozenset({
        "koan_complete_step",
        "koan_ask_question",
        "koan_select_story",
        "koan_complete_story",
        "koan_retry_story",
        "koan_skip_story",
        "edit",
        "write",
        "bash",
    }),
    "planner": frozenset({
        "koan_complete_step",
        "koan_ask_question",
        "koan_request_scouts",
        "edit",
        "write",
    }),
    "executor": frozenset({
        "koan_complete_step",
        "koan_ask_question",
        "edit",
        "write",
        "bash",
    }),
    "workflow-orchestrator": frozenset({
        "koan_complete_step",
        "koan_propose_workflow",
        "koan_set_next_phase",
    }),
    "ticket-breakdown": frozenset({
        "koan_complete_step",
        "koan_ask_question",
        "koan_request_scouts",
        "edit",
        "write",
    }),
    "cross-artifact-validator": frozenset({
        "koan_complete_step",
        "koan_ask_question",
        "koan_request_scouts",
        "edit",
        "write",
    }),
}

PLANNING_ROLES: frozenset[str] = frozenset({
    "intake",
    "scout",
    "decomposer",
    "brief-writer",
    "orchestrator",
    "planner",
    "workflow-orchestrator",
    "ticket-breakdown",
    "cross-artifact-validator",
})

READ_ONLY_ROLES: frozenset[str] = frozenset({"scout"})

STEP_1_BLOCKED_TOOLS: frozenset[str] = frozenset({
    "koan_request_scouts",
    "koan_ask_question",
    "write",
    "edit",
})


# -- Permission check ---------------------------------------------------------

def check_permission(
    role: str,
    tool_name: str,
    epic_dir: str | None = None,
    tool_args: dict | None = None,
    current_step: int | None = None,
) -> dict:
    """Return {"allowed": True/False, "reason": str|None}."""

    # Read tools always allowed -- check before role map lookup.
    if tool_name in READ_TOOLS:
        return {"allowed": True, "reason": None}

    # Intake step 1 (Extract) is read-only.
    if role == "intake" and current_step == 1 and tool_name in STEP_1_BLOCKED_TOOLS:
        return {
            "allowed": False,
            "reason": (
                f"{tool_name} is not available during the Extract step (step 1). "
                "Complete koan_complete_step first to advance to the Scout step."
            ),
        }

    # Brief-writer step 1 (Read) is read-only.
    if role == "brief-writer" and current_step == 1 and tool_name in STEP_1_BLOCKED_TOOLS:
        return {
            "allowed": False,
            "reason": (
                f"{tool_name} is not available during the Read step (step 1). "
                "Complete koan_complete_step first to advance to the Draft & Review step."
            ),
        }

    # Unknown role: blocked under default-deny policy.
    if role not in ROLE_PERMISSIONS:
        log.warning("Unknown role blocked: role=%s tool=%s", role, tool_name)
        return {"allowed": False, "reason": f"Unknown role: {role}"}

    allowed_tools = ROLE_PERMISSIONS[role]

    if tool_name not in allowed_tools:
        return {"allowed": False, "reason": f"{tool_name} is not available for role {role}"}

    # Path-scope enforcement: planning roles may only write inside epic dir.
    if tool_name in WRITE_TOOLS and role in PLANNING_ROLES:
        if epic_dir and tool_args:
            raw_path = tool_args.get("path")
            if isinstance(raw_path, str):
                resolved_tool = Path(raw_path).resolve()
                resolved_epic = Path(epic_dir).resolve()
                if resolved_tool != resolved_epic and not str(resolved_tool).startswith(str(resolved_epic) + "/"):
                    log.warning(
                        "Write blocked: path outside epic dir: role=%s tool=%s path=%s epic=%s",
                        role, tool_name, raw_path, epic_dir,
                    )
                    return {
                        "allowed": False,
                        "reason": f'{tool_name} path "{raw_path}" is outside epic directory',
                    }
        return {"allowed": True, "reason": None}

    return {"allowed": True, "reason": None}
