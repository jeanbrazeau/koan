# Plan-review phase -- 2-step workflow.
#
#   Step 1 (Read)      -- review intake context and plan.md; no writes
#   Step 2 (Evaluate)  -- classify findings; rewrite internal ones in place
#                         or recommend loop-back for new-files findings
#
# Rewrite-or-loop-back: internal findings are fixed via koan_artifact_write;
# new-files findings surface via koan_yield with plan-spec recommended.
# Scope: "general" -- reusable by any workflow.

from __future__ import annotations

from . import PhaseContext, StepGuidance
from .format_step import terminal_invoke

ROLE = "orchestrator"
SCOPE = "general"        # reusable by any workflow
TOTAL_STEPS = 2

STEP_NAMES: dict[int, str] = {
    1: "Read",
    2: "Evaluate",
}

PHASE_ROLE_CONTEXT = (
    "You are the adversarial reviewer for an implementation plan.\n"
    "\n"
    "You are the ONLY phase in this workflow that independently verifies claims\n"
    "against the actual codebase. Intake explored and gathered context. Plan-spec\n"
    "structured that context into a plan. Neither was asked to doubt the other.\n"
    "Your job is to doubt both.\n"
    "\n"
    "## Your role\n"
    "\n"
    "Find problems that would cause the executor to fail or produce wrong results.\n"
    "Verify every codebase claim the plan makes -- file paths, function names,\n"
    "interfaces, types -- by reading the actual source files. The plan may reference\n"
    "code that was renamed, moved, or never existed. Find out.\n"
    "\n"
    "Do NOT flag trivial issues the executor can resolve independently (minor typos,\n"
    "missing imports, syntax in snippets). Focus on issues that change the approach.\n"
    "\n"
    # M4: review phases apply rewrite-or-loopback semantics; prompt discipline
    # keeps each review phase rewriting only its own producer's artifact.
    "You apply rewrite-or-loop-back semantics. For each finding, you judge whether\n"
    "the producer (plan-spec) could have caught it from the files it already\n"
    "loaded; if yes, you fix the issue in place by issuing `koan_artifact_write`\n"
    "against the plan artifact. If the finding requires new files the producer\n"
    "didn't load, you recommend loop-back to plan-spec via the yield. See\n"
    "`docs/phase-trust.md` for the full doctrine.\n"
    "\n"
    "## Evaluation dimensions\n"
    "\n"
    "- **Completeness**: Does the plan cover every requirement from the intake findings?\n"
    "- **Correctness**: Are the file paths, function names, and interfaces accurate?\n"
    "  Verify against the actual codebase.\n"
    "- **Feasibility**: Are the implementation steps actionable as described? Would\n"
    "  an executor be able to follow them without ambiguity?\n"
    "- **Risks**: What could go wrong during execution? Missing edge cases?\n"
    "- **Gaps**: Anything not addressed that should be?\n"
    "\n"
    "## Strict rules\n"
    "\n"
    "- MUST read the plan artifact before evaluating.\n"
    "- MUST read the codebase files the plan references. Verify every claim.\n"
    "- MUST classify each finding as internal or new-files-needed.\n"
    "- MUST issue koan_artifact_write for internal findings (rewrite in place).\n"
    "- MUST recommend loop-back via koan_yield for new-files findings.\n"
    "- MUST NOT flag issues the executor can trivially resolve.\n"
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
        # brief.md gives the reviewer the authoritative requirement set, independent
        # of conversation history which may be long or noisy by this phase.
        lines.extend([
            "## Read initiative context",
            "",
            "Read `brief.md` from the run directory before verifying the plan's claims.",
            "It contains the frozen initiative scope, decisions, and constraints from",
            "intake. The plan must satisfy every requirement listed there; verify",
            "completeness against brief.md, not just the conversation history.",
            "",
            "Read and comprehend before evaluating. Do NOT write any files in this step.",
            "",
            "## Consult project memory",
            "",
            "Before verifying individual claims in plan.md, check what the",
            "project already knows about the correct approach for the",
            "subsystems being modified. Memory may contain past decisions that",
            "contradict the plan, lessons about what went wrong in similar",
            "changes, and procedures the executor must follow -- any of which",
            "reveal problems that cannot be detected by reading the plan and",
            "the code alone.",
            "",
            "If relevant memory entries appeared above (`## Relevant memory`),",
            "read them now.",
            "",
            "Then run `koan_reflect` with a broad question about the correct",
            "approach for the area the plan modifies (e.g. 'what is the",
            "expected approach for changes to the X subsystem?'). Use",
            "`koan_search` for specific past lessons or decisions that may bear",
            "on the plan.",
            "",
            "The question is not 'have we made this mistake before?' but 'what",
            "is the correct approach, and does this plan follow it?'",
            "",
            "Only after this should you verify individual claims.",
            "",
            "## Your verification mandate",
            "",
            "You are the only phase that independently checks claims against reality.",
            "Intake and plan-spec trusted each other. You trust nobody.",
            "",
            "## What to read",
            "",
            "1. Review the intake findings in your context for the requirements and",
            "   constraints the plan must satisfy.",
            "2. Read the plan artifact. The workflow guidance above specifies which file to"
            " review. If not specified, read `plan.md` in the run directory.",
            "3. For every codebase claim in the plan (file path, function name,",
            "   interface, type), open the actual source file and verify. If the plan",
            "   says 'modify function X in file Y', confirm X exists in Y with the",
            "   signature the plan assumes.",
            "",
            "## Build a mental model",
            "",
            "After reading, you should be able to answer:",
            "- What does the plan claim to change, and in which files?",
            "- Are those files and functions real and accurately described?",
            "- Does the plan cover all requirements from the intake findings?",
            "- Are the implementation steps in the right order?",
            "",
            "Do NOT write an evaluation yet. Comprehend first.",
        ])
        return StepGuidance(title=STEP_NAMES[1], instructions=lines)

    if step == 2:
        return StepGuidance(
            title=STEP_NAMES[2],
            instructions=[
                "Evaluate the plan and report findings in your response.",
                "",
                "## What to evaluate",
                "",
                "**Completeness**: Does the plan cover every requirement from the intake findings?",
                "List any requirements not addressed.",
                "",
                "**Correctness**: Are file paths, function names, and interfaces accurate?",
                "Note any incorrect references you verified against the codebase.",
                "",
                "**Feasibility**: Can an executor follow each step without ambiguity?",
                "Note any steps that are vague, contradictory, or would require judgment calls.",
                "",
                "**Risks**: What could go wrong? Missing edge cases, ordering issues, dependencies?",
                "",
                "**Gaps**: Anything the plan should address but doesn't?",
                "",
                "## Severity classification",
                "",
                "Report findings organized by severity:",
                "- **Critical**: would cause the executor to fail or produce wrong results",
                "- **Major**: significant gap or incorrectness requiring plan revision",
                "- **Minor**: small issue the executor can likely resolve independently",
                "",
                "Do NOT flag trivial executor-resolvable issues as major findings.",
                "",
                # M4: rewrite-or-loopback block; runs after severity classification,
                # before the yield. Internal findings are fixed in place; new-files
                # findings surface via the yield so the next plan-spec loads them.
                "## Rewrite-or-loop-back classification",
                "",
                "For each finding, classify it as one of:",
                "",
                "- **Internal**: the producer (plan-spec) could have caught this given the",
                "  files it already loaded (the plan artifact body + `brief.md`). Examples:",
                "  a step ordering bug, an inconsistency between two parts of the plan, a",
                "  decision that contradicts brief.md.",
                "- **New-files-needed**: catching this finding would have required the",
                "  producer to load files it did not load. Examples: a function-signature",
                "  claim against a file the plan does not reference; a constraint from",
                "  a sibling module the plan didn't open.",
                "",
                "## What to do with the classification",
                "",
                "- **All findings internal -> rewrite in place**. Issue",
                '  `koan_artifact_write(filename="<plan_artifact>", content=<corrected_plan>)`',
                "  to replace the plan artifact in place. The corrected plan must address",
                "  every internal finding. Then yield with `execute` recommended (proceed",
                "  to executor handoff).",
                "- **Any finding new-files-needed -> recommend loop-back**. Do NOT call",
                "  `koan_artifact_write`. Yield with `plan-spec` recommended in the",
                "  `koan_yield` suggestions so the producer phase re-runs with the new",
                "  files in scope. Surface the new-files findings prominently so the",
                "  next plan-spec session knows what to load.",
                "- **Mixed**: rewrite the internal findings in place AND recommend",
                "  loop-back via the yield. The producer phase, when it re-runs, will see",
                "  both the partially-rewritten plan and the new-files findings.",
                "",
                "The plan artifact filename comes from the workflow guidance: `plan.md`",
                "for plan workflow; `plan-milestone-N.md` for milestones workflow (read",
                "the workflow guidance above to determine N).",
                "",
                "## Using koan_ask_question",
                "",
                "If the review surfaces ambiguities requiring user input (requirements unclear,"
                " conflicting constraints, genuine design questions), call `koan_ask_question`.",
                "Only ask questions that affect the evaluation outcome.",
                "",
                "## After reporting",
            ],
            # terminal_invoke replaces the trailing koan_complete_step instruction.
            # next_phase=None: review findings determine whether to loop back to
            # plan-spec or proceed; user direction is required.
            invoke_after=terminal_invoke(ctx.next_phase, ctx.suggested_phases),
        )

    return StepGuidance(title=f"Step {step}", instructions=[f"Execute step {step}."])


# -- Lifecycle -----------------------------------------------------------------

def get_next_step(step: int, ctx: PhaseContext) -> int | None:
    if step < TOTAL_STEPS:
        return step + 1
    return None  # linear, no review gate


def validate_step_completion(step: int, ctx: PhaseContext) -> str | None:
    return None


async def on_loop_back(from_step: int, to_step: int, ctx: PhaseContext) -> None:
    pass
