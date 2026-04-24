# Exec-review phase -- 2-step workflow.
#
#   Step 1 (Verify)  -- read plan and run verification commands; no writes
#   Step 2 (Assess)  -- classify outcome and report findings via chat
#
# Advisory only: findings are reported in chat, not written to a file.
# Scope: "general" -- reusable by any workflow.

from __future__ import annotations

from . import PhaseContext, StepGuidance

ROLE = "orchestrator"
SCOPE = "general"        # reusable by any workflow
TOTAL_STEPS = 2

STEP_NAMES: dict[int, str] = {
    1: "Verify",
    2: "Assess",
}

PHASE_ROLE_CONTEXT = (
    "You are reviewing the results of an executor's implementation work. The executor was\n"
    "given a plan and implemented it. Your job is to verify what was accomplished, identify\n"
    "deviations from the plan, and assess whether the implementation meets the plan's goals.\n"
    "You may run verification commands (tests, type checks, linting) to confirm the\n"
    "executor's claims.\n"
    "\n"
    "## Your role\n"
    "\n"
    "You are a reviewer. You do NOT write code or modify the implementation.\n"
    "\n"
    "## Evaluation dimensions\n"
    "\n"
    "- **Goal completion**: Were all planned goals met?\n"
    "- **Deviations**: What deviated from the plan, and are the deviations acceptable?\n"
    "- **Quality**: Does the implementation appear correct? Run verification commands.\n"
    "- **Completeness**: Was any planned work left incomplete?\n"
    "\n"
    "## Strict rules\n"
    "\n"
    "- MUST read the executor's deviation report from the conversation context.\n"
    "- MUST run at least one verification command (build, tests, type check) if applicable.\n"
    "- MUST NOT write code or modify files.\n"
    "- MUST classify the outcome (Clean / Minor deviations / Significant deviations / Incomplete).\n"
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
            "Verify what the executor accomplished. Do NOT make any code changes in this step.",
            "",
            "## What to verify",
            "",
            "1. Read the executor's deviation report from the conversation context (the final",
            "   koan_complete_step response from the execute phase).",
            "2. Read the plan artifact and note what was planned.",
            "3. Run verification commands to confirm the executor's claims:",
            "   - Build or compile the project if applicable.",
            "   - Run the test suite or relevant test subset.",
            "   - Run type checks (e.g. `npx tsc --noEmit`) if applicable.",
            "4. List the codebase files the plan specified and confirm they were modified as intended.",
            "",
            "Do NOT write an assessment yet. Verify first.",
            "",
            "Call `koan_complete_step` with a verification summary:",
            "- What verification commands you ran and their results",
            "- Which planned goals appear met vs. incomplete",
        ])
        return StepGuidance(title=STEP_NAMES[1], instructions=lines)

    if step == 2:
        return StepGuidance(
            title=STEP_NAMES[2],
            instructions=[
                "Report your assessment in this response.",
                "",
                "## Outcome classification",
                "",
                "Classify the execution outcome using exactly one of:",
                "- **Clean execution**: plan was followed, all goals met, no significant deviations.",
                "- **Minor deviations**: plan was mostly followed; deviations are acceptable or trivial.",
                "- **Significant deviations**: deviations require downstream adjustments.",
                "- **Incomplete**: planned work was not done.",
                "",
                "## Assessment structure",
                "",
                "1. **Outcome**: [classification]",
                "2. **Implemented as planned**: what matched the plan",
                "3. **Deviations**: what diverged and why (from the executor's own report + your verification)",
                "4. **Incomplete**: anything the plan specified that was not done",
                "5. **Verification results**: build/test outcomes",
                "",
                "The workflow guidance above specifies what to do after this assessment.",
                "",
                "Call `koan_complete_step` when your assessment is delivered in chat.",
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
