# Milestone-review phase -- 2-step workflow.
#
#   Step 1 (Read)      -- read milestones.md and codebase areas; no writes
#   Step 2 (Evaluate)  -- report findings organized by severity via chat
#
# Advisory only: findings are reported in chat, not written to a file.
# Scope: "milestones" -- specific to the milestones workflow.

from __future__ import annotations

from . import PhaseContext, StepGuidance

ROLE = "orchestrator"
SCOPE = "milestones"     # specific to the milestones workflow
TOTAL_STEPS = 2

STEP_NAMES: dict[int, str] = {
    1: "Read",
    2: "Evaluate",
}

PHASE_ROLE_CONTEXT = (
    "You are reviewing a milestone decomposition for a broad initiative. Your job is to\n"
    "find problems in how the work was divided: scope issues, ordering mistakes, missing\n"
    "milestones, milestones that are too large or too small, dependencies that would block\n"
    "progress.\n"
    "\n"
    "## Your role\n"
    "\n"
    "You are advisory. You do NOT modify milestones.md. You report findings; milestone-spec\n"
    "will incorporate them.\n"
    "\n"
    "## Evaluation dimensions\n"
    "\n"
    "- **Scope**: Is each milestone well-bounded and not too large to plan in a single session?\n"
    "- **Ordering**: Are dependencies correct? Can each milestone be started after the prior one?\n"
    "- **Completeness**: Are there gaps? Work that belongs to the initiative but no milestone covers?\n"
    "- **Independence**: Can each milestone be delivered without the next being started?\n"
    "- **Feasibility**: Is each milestone's sketch detailed enough to plan from?\n"
    "\n"
    "## Strict rules\n"
    "\n"
    "- MUST read milestones.md before evaluating.\n"
    "- MUST read the codebase areas each milestone touches to verify the decomposition.\n"
    "- MUST NOT modify milestones.md.\n"
    "- MUST classify findings by severity (Critical / Major / Minor).\n"
)


# -- Step guidance -------------------------------------------------------------

def step_guidance(step: int, ctx: PhaseContext) -> StepGuidance:
    if step == 1:
        lines: list[str] = []
        # phase_instructions at top per established pattern (intake.py, execute.py)
        if ctx.phase_instructions:
            lines.extend(["## Workflow guidance", "", ctx.phase_instructions, ""])
        if ctx.memory_injection:
            lines.extend([ctx.memory_injection, ""])
        lines.extend([
            "Read and comprehend before evaluating. Do NOT write anything in this step.",
            "",
            "## What to read",
            "",
            "1. Read `milestones.md` from start to finish.",
            "2. For each milestone, read the codebase areas it covers -- verify that the",
            "   decomposition makes sense against the actual code structure.",
            "3. Check for ordering issues: would implementing milestone N require changes",
            "   that milestone N+1 also modifies (i.e., are they truly independent)?",
            "",
            "Call `koan_complete_step` with a comprehension summary:",
            "- What you read",
            "- Any immediate concerns spotted",
        ])
        return StepGuidance(title=STEP_NAMES[1], instructions=lines)

    if step == 2:
        return StepGuidance(
            title=STEP_NAMES[2],
            instructions=[
                "Report your findings in this response.",
                "",
                "## Severity classification",
                "",
                "- **Critical**: a fundamental problem (wrong ordering, impossible dependency, missing",
                "  major area) that would cause the initiative to fail without rework.",
                "- **Major**: significant gap or scope problem requiring milestone revision.",
                "- **Minor**: small issue the milestone-spec phase can address independently.",
                "",
                "## Evaluation dimensions",
                "",
                "For each dimension, report findings or confirm it is sound:",
                "- **Scope**: Are milestones well-bounded?",
                "- **Ordering**: Are dependencies correct?",
                "- **Completeness**: Are there gaps?",
                "- **Independence**: Can each be delivered without the next?",
                "- **Feasibility**: Is each sketch detailed enough to plan from?",
                "",
                "## After reporting",
                "",
                "The workflow guidance above specifies where to go next.",
                "",
                "Call `koan_complete_step` when your evaluation is delivered in chat.",
            ],
        )

    return StepGuidance(title=f"Step {step}", instructions=[f"Execute step {step}."])


# -- Lifecycle -----------------------------------------------------------------

def get_next_step(step: int, ctx: PhaseContext) -> int | None:
    if step < TOTAL_STEPS:
        return step + 1
    return None


def validate_step_completion(step: int, ctx: PhaseContext) -> str | None:
    return None


async def on_loop_back(from_step: int, to_step: int, ctx: PhaseContext) -> None:
    pass
