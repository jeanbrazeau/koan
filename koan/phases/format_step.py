# Step prompt assembly -- formats StepGuidance into the string returned to the LLM.
# Python port of src/planner/lib/step.ts formatStep().

from __future__ import annotations

from typing import TYPE_CHECKING

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
