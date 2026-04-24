# Milestone-spec phase -- 2-step workflow.
#
#   Step 1 (Analyze)  -- determine mode (CREATE/UPDATE), analyze scope; no writes
#   Step 2 (Write)    -- write or update milestones.md via koan_artifact_propose
#
# Handles both initial decomposition (no milestones.md) and post-execution
# updates (after exec-review). Mode is determined by reading milestones.md.
# Scope: "milestones" -- specific to the milestones workflow.

from __future__ import annotations

from . import PhaseContext, StepGuidance

ROLE = "orchestrator"
SCOPE = "milestones"     # specific to the milestones workflow
TOTAL_STEPS = 2

STEP_NAMES: dict[int, str] = {
    1: "Analyze",
    2: "Write",
}

PHASE_ROLE_CONTEXT = (
    "You are a technical architect managing milestone decomposition for a broad initiative.\n"
    "You may be creating the initial decomposition or updating milestones.md after a milestone\n"
    "was executed. Read `milestones.md` in the run directory -- if it exists, you are updating;\n"
    "if not, you are creating from intake findings.\n"
    "\n"
    "Each milestone should be a coherent, independently-deliverable unit of work. You decompose\n"
    "and track progress; you do not plan implementation details.\n"
    "\n"
    "## milestones.md format\n"
    "\n"
    "```markdown\n"
    "# Milestones: <initiative title>\n"
    "\n"
    "## Milestone 1: <title> [done]\n"
    "\n"
    "<description of what was accomplished>\n"
    "\n"
    "### Outcome\n"
    "\n"
    "<post-execution notes added during milestone-spec update>\n"
    "\n"
    "## Milestone 2: <title> [in-progress]\n"
    "\n"
    "<rough sketch of what should happen>\n"
    "\n"
    "## Milestone 3: <title> [pending]\n"
    "\n"
    "<rough sketch of what should happen>\n"
    "```\n"
    "\n"
    "## Status markers\n"
    "\n"
    "- `[pending]`: not yet started\n"
    "- `[in-progress]`: currently being planned or executed\n"
    "- `[done]`: execution complete\n"
    "- `[skipped]`: intentionally omitted\n"
    "\n"
    "## Strict rules\n"
    "\n"
    "- MUST read milestones.md (if it exists) before writing.\n"
    "- MUST use koan_artifact_propose to write milestones.md.\n"
    "- MUST NOT plan implementation details -- rough sketches only.\n"
    "- When updating: MUST add an Outcome section to the completed milestone.\n"
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
            "Read and analyze before writing. Do NOT write milestones.md in this step.",
            "",
            "## Determine mode",
            "",
            "Check whether milestones.md exists in the run directory.",
            "- If it does NOT exist: you are in CREATE mode. Read intake findings from the",
            "  conversation context to understand the initiative scope.",
            "- If it DOES exist: you are in UPDATE mode. Read milestones.md, then read the",
            "  exec-review assessment from the conversation context to understand what was",
            "  accomplished and any deviations.",
            "",
            "## Consult project memory",
            "",
            "Run koan_search or koan_reflect for architectural constraints relevant to",
            "milestone ordering and scope boundaries.",
            "",
            "## Analysis goal",
            "",
            "CREATE mode: Identify 3-7 independently-deliverable milestones that cover the",
            "full initiative scope. Each milestone should be completable in a focused coding",
            "session. Note dependencies and ordering constraints.",
            "",
            "UPDATE mode: Determine what the completed milestone achieved. Identify any",
            "adjustments needed to remaining milestones based on deviations from the plan.",
            "Note whether the scope of remaining milestones has changed.",
            "",
            "Call `koan_complete_step` with:",
            "- Mode (CREATE or UPDATE)",
            "- CREATE: proposed milestone list with rough sketches",
            "- UPDATE: completed milestone outcome and proposed adjustments to remaining milestones",
        ])
        return StepGuidance(title=STEP_NAMES[1], instructions=lines)

    if step == 2:
        return StepGuidance(
            title=STEP_NAMES[2],
            instructions=[
                "Write or update milestones.md via `koan_artifact_propose`.",
                "",
                "```",
                "koan_artifact_propose(",
                '    filename="milestones.md",',
                '    content="""\\ ',
                "# Milestones: <initiative title>",
                "",
                "## Milestone 1: <title> [status]",
                "...",
                '""",',
                ")",
                "```",
                "",
                "## CREATE mode",
                "",
                "- Give the **first** milestone `[in-progress]` status; give all subsequent milestones `[pending]` status.",
                "- Write a rough sketch (3-6 sentences) describing what this milestone covers.",
                "- Order milestones by dependency: earlier milestones must not depend on later ones.",
                "",
                "## UPDATE mode",
                "",
                "- Change the completed milestone's status from `[in-progress]` to `[done]`.",
                "- Add an `### Outcome` section under it describing what was actually accomplished.",
                "- Adjust remaining milestones if execution deviated from expectations:",
                "  reorder, add, remove, or revise sketches as needed.",
                "- Mark the next `[pending]` milestone as `[in-progress]` (if one exists).",
                "- Leave unaffected milestones unchanged.",
                "",
                "## After user approves",
                "",
                "Check the remaining milestone statuses:",
                "- If any milestones are `[pending]` or `[in-progress]`: call `koan_set_phase` with",
                '  `"plan-spec"` to plan the next milestone.',
                "- If all milestones are `[done]` or `[skipped]`: call `koan_set_phase` with",
                '  `"curation"` to complete the workflow.',
                "",
                "Call `koan_complete_step` to trigger the phase boundary.",
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
