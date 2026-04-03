# Step prompt assembly -- formats StepGuidance into the string returned to the LLM.
# Python port of src/planner/lib/step.ts formatStep().

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from . import StepGuidance


DEFAULT_INVOKE = (
    "WHEN DONE: Call koan_complete_step to advance to the next step.\n"
    "Do NOT call this tool until the work described in this step is finished."
)


def format_step(g: StepGuidance) -> str:
    header = f"{g.title}\n{'=' * len(g.title)}\n\n"
    body = "\n".join(g.instructions)
    invoke = g.invoke_after if g.invoke_after is not None else DEFAULT_INVOKE
    return f"{header}{body}\n\n{invoke}"


def format_user_messages(messages: list[Any]) -> str:
    """Format a list of ChatMessage objects into a readable string block."""
    parts = []
    for msg in messages:
        ts = datetime.fromtimestamp(msg.timestamp_ms / 1000, tz=timezone.utc)
        ts_str = ts.strftime("%H:%M:%S UTC")
        parts.append(f"---\nUSER MESSAGE (at {ts_str}):\n{msg.content}\n---")
    return "\n\n".join(parts)


def format_steering_messages(messages: list[Any]) -> str:
    """Format steering queue messages into a clearly demarcated XML block.

    Appended to tool responses so the LLM sees user feedback that arrived
    while it was working. The framing instructs the LLM to integrate the
    feedback without derailing from the current workflow.
    """
    parts = []
    for msg in messages:
        ts = datetime.fromtimestamp(msg.timestamp_ms / 1000, tz=timezone.utc)
        ts_str = ts.strftime("%H:%M:%S UTC")
        parts.append(f"[{ts_str}] {msg.content}")
    body = "\n\n".join(parts)
    return (
        "\n\n<steering>\n"
        "The user sent the following message(s) while you were working.\n"
        "Take these into account going forward, but do not abandon the\n"
        "current workflow step. Integrate the feedback into your approach.\n"
        "\n"
        f"{body}\n"
        "</steering>"
    )


def format_phase_boundary(phase: str, messages: list[Any], successors: list[str]) -> str:
    """Format a phase-boundary response that includes user messages and next-phase options."""
    title = f"Phase Complete: {phase}"
    lines = [title, "=" * len(title), ""]

    if messages:
        lines.append("## User Message(s)")
        lines.append("")
        for msg in messages:
            ts = datetime.fromtimestamp(msg.timestamp_ms / 1000, tz=timezone.utc)
            ts_str = ts.strftime("%H:%M:%S UTC")
            lines.append(f"**[{ts_str}]** {msg.content}")
        lines.append("")

    lines.append("## Available Next Phases")
    lines.append("")
    for s in successors:
        lines.append(f"- **{s}**")
    lines.append("")

    lines.append("## Instructions")
    lines.append("")
    lines.append("Discuss the completed phase and the user's message(s) with the user.")
    lines.append("Once the user has confirmed what to do next, call `koan_set_phase` with")
    lines.append("the chosen phase name. Then call `koan_complete_step` to begin.")

    return "\n".join(lines)
