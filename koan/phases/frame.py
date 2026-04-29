# Frame phase -- 1-step divergent workflow.
#
#   Step 1 (Explore)   -- open-ended dialogue; no fixed artifact; always yields
#
# Frame is the only divergent phase in the system. Its exit is negotiated with
# the user and is one of three options: promote into another workflow via
# koan_set_workflow, transition to another phase within the current workflow
# via koan_set_phase, or end the workflow via koan_set_phase("done"). The
# phase never auto-advances under any circumstance -- frame's purpose is
# exploration before a question is well-formed, and committing prematurely
# defeats that purpose.
#
# Scope: "general" -- reusable by any workflow; discovery workflow is the
# primary binding, but any workflow can reach frame via koan_set_workflow.

from __future__ import annotations

from . import PhaseContext, StepGuidance
from .format_step import terminal_invoke

ROLE = "orchestrator"
SCOPE = "general"       # reusable; discovery workflow binds it as initial phase
TOTAL_STEPS = 1

STEP_NAMES: dict[int, str] = {
    1: "Explore",
}

PHASE_ROLE_CONTEXT = (
    "You are a sounding board for the user during an open-ended exploration phase.\n"
    "\n"
    "Your role is NOT analyst or planner. You surface tradeoffs, name hidden\n"
    "assumptions, offer alternatives, and push back on premature commitment.\n"
    "You do NOT converge on an artifact or architectural choice unless the user\n"
    "signals readiness.\n"
    "\n"
    "## Your role\n"
    "\n"
    "- Surface tradeoffs, not recommendations.\n"
    "- Name hidden assumptions the user may be making.\n"
    "- Offer alternatives when the user seems committed to a single path.\n"
    "- Push back on premature commitment to implementation detail.\n"
    "- Never propose a next step unless the user asks.\n"
    "\n"
    "## Exit options\n"
    "\n"
    "When the user signals they are ready to proceed, surface three options:\n"
    "\n"
    "1. Promote into another workflow via `koan_set_workflow` (e.g. promote to\n"
    "   'initiative', 'milestones', or 'plan' with the discovery transcript carried\n"
    "   forward as context).\n"
    "2. Transition to another phase within the current workflow via `koan_set_phase`.\n"
    "3. End the workflow via `koan_set_phase('done')` -- the user explored enough and\n"
    "   wants no further phases.\n"
    "\n"
    "## Strict rules\n"
    "\n"
    "- MUST NOT call `koan_request_scouts`. The permission fence denies it; this rule\n"
    "  documents intent so you do not retry. Frame is about intent, not codebase\n"
    "  investigation. Codebase reading is appropriate only when the dialogue explicitly\n"
    "  refers to specific systems -- use `koan_search` or `koan_reflect` instead.\n"
    "- MUST NOT call `koan_artifact_write` until the user has explicitly chosen an\n"
    "  artifact shape and named it. Writing prematurely collapses the exploration.\n"
    "- MUST NOT commit to architectural choices. Surfacing tradeoffs is your job;\n"
    "  choosing between them is the user's.\n"
    "- MUST NOT write any decision into project memory unless the user explicitly\n"
    "  directs curation. Memory writes during exploration contaminate the record with\n"
    "  pre-decision thinking.\n"
    "- MUST always yield rather than auto-advance. Frame has no auto-advance path.\n"
    "  Every step ends with `koan_yield`.\n"
)


# -- Step guidance -------------------------------------------------------------

def step_guidance(step: int, ctx: PhaseContext) -> StepGuidance:
    """Build the StepGuidance for the given step.

    Frame has only one step. Step 1 establishes the sounding-board posture,
    surfaces any prior context, and opens the exploration. The invoke_after
    footer always calls koan_yield (next_phase=None, no auto-advance).
    """
    if step == 1:
        lines: list[str] = []

        # Workflow scope framing at top, matching intake.py layout (lines 89-102).
        if ctx.workflow_name:
            lines.extend([f"Active workflow: **{ctx.workflow_name}**", ""])
        if ctx.phase_instructions:
            lines.extend(["## Workflow guidance", "", ctx.phase_instructions, ""])
        if ctx.memory_injection:
            lines.extend([ctx.memory_injection, ""])

        # Task description envelope -- matches intake.py convention.
        lines.extend([
            "## Task description",
            "",
        ])
        if ctx.task_description:
            lines.append(f"<task_description>\n{ctx.task_description}\n</task_description>")
        else:
            lines.append("(No task description provided.)")

        lines.extend([
            "",
            "## Your posture",
            "",
            "You are a sounding board, not an analyst. Your job is to surface tradeoffs,",
            "name hidden assumptions, and push back on premature commitment. You do NOT",
            "converge on an artifact or a recommendation unless the user asks you to.",
            "",
            "## Finding prior context",
            "",
            "Before the exploration dialogue begins, surface relevant prior context so the",
            "conversation starts from a grounded position:",
            "",
            "- Use `koan_search` for specific past decisions or lessons that may bear on",
            "  what the user is exploring.",
            "- Use `koan_reflect` with a broad question about the territory the user is",
            "  exploring (e.g. 'what do we know about X subsystem and its tradeoffs?').",
            "",
            "Do NOT dispatch `koan_request_scouts`. Frame is about intent, not codebase",
            "investigation. Codebase reading is appropriate only when the dialogue starts",
            "referring to specific systems. The permission fence also denies scouts in this",
            "phase -- do not retry if the call is rejected.",
            "",
            "## No artifact without negotiation",
            "",
            "Do NOT call `koan_artifact_write` until the user has explicitly chosen an",
            "artifact shape and named it. Writing prematurely collapses the exploration.",
            "",
            "## Exit",
            "",
            "When the user signals they are ready to proceed, present three options:",
            "",
            "1. Promote into another workflow via `koan_set_workflow` (e.g. 'initiative',",
            "   'milestones', 'plan') -- the discovery transcript carries forward.",
            "2. Transition to another phase within the current workflow via `koan_set_phase`.",
            "3. End the workflow via `koan_set_phase('done')` if the user explored enough",
            "   and wants no further phases.",
        ])

        return StepGuidance(
            title=STEP_NAMES[1],
            instructions=lines,
            # next_phase=None means terminal_invoke renders a full-yield footer.
            # Frame must never auto-advance; the suggested phases come from the
            # workflow's transitions dict (populated into ctx.suggested_phases at
            # step-1 handshake).
            invoke_after=terminal_invoke(ctx.next_phase, ctx.suggested_phases),
        )

    return StepGuidance(title=f"Step {step}", instructions=[f"Execute step {step}."])


# -- Lifecycle -----------------------------------------------------------------

def get_next_step(step: int, ctx: PhaseContext) -> int | None:
    """Return None always -- frame is single-step and never auto-advances."""
    return None


def validate_step_completion(step: int, ctx: PhaseContext) -> str | None:
    """Return None -- step completion validation is not implemented."""
    return None


async def on_loop_back(from_step: int, to_step: int, ctx: PhaseContext) -> None:
    """No-op -- frame has no loop-back state to manage."""
    pass
