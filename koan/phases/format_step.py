# Step prompt assembly -- formats StepGuidance into the string returned to the LLM.

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


def format_phase_boundary(
    phase: str,
    messages: list[Any],
    suggested: list[str],
    phase_descriptions: dict[str, str] | None = None,
) -> str:
    """Format a phase-boundary response with user messages and suggested next phases.

    If suggested is empty (stub workflow), renders a graceful end-of-workflow message
    instead of an empty phases section.
    """
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

    if suggested:
        descs = phase_descriptions or {}
        lines.append("## Suggested Next Phases")
        lines.append("")
        for s in suggested:
            desc = descs.get(s, "")
            if desc:
                lines.append(f"- **{s}** \u2014 {desc}")
            else:
                lines.append(f"- **{s}**")
        lines.append("")
        lines.append("## Instructions")
        lines.append("")
        lines.append("Briefly summarize what was accomplished in this phase. Present the")
        lines.append("suggested phases above to the user, explaining what each one does.")
        lines.append("Ask which direction they would like to go. The user can also request")
        lines.append("any other phase available in this workflow.")
        lines.append("Once confirmed, call `koan_set_phase` then `koan_complete_step`.")
    else:
        lines.append("## Workflow Stub")
        lines.append("")
        lines.append("This workflow does not have further phases implemented yet.")
        lines.append("Summarize what was accomplished in intake and let the user know")
        lines.append("the workflow will end here for now.")

    return "\n".join(lines)
