# Workflow definitions for the koan orchestrator.
#
# A Workflow defines the phases available to the orchestrator, their suggested
# transition order, phase descriptions shown at boundaries, and per-phase
# guidance injected into step 1 instructions.
#
# Design notes:
#   - frozen=True prevents field reassignment after construction (mutation protection).
#   - frozen=True does NOT make Workflow hashable --dict fields are unhashable.
#     Do not use Workflow as a dict key or set member.
#   - Workflows are defined as module-level constants (PLAN_WORKFLOW, etc.).
#   - Phase transition validation: any phase in available_phases is reachable
#     from any other (user-directed), except self-transitions.

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Workflow:
    """Immutable workflow definition.

    Attributes:
        name: Short identifier (e.g. "plan", "milestones").
        description: Human-readable description shown in the UI.
        available_phases: All phases the user can transition to in this workflow.
        initial_phase: Phase the orchestrator starts in.
        suggested_transitions: Per-phase ordered list of suggested next phases.
            Guides the orchestrator's boundary response; user can override.
        phase_descriptions: One-line description of each phase shown at boundaries.
        phase_guidance: Per-phase scope framing injected at the top of step 1
            guidance. Controls investigation depth, question posture, etc.

            Only workflow-agnostic phases (intake, execute) need entries here.
            These phases are reused across workflows, so the workflow injects
            context they cannot hardcode. Workflow-specific phases (plan-spec,
            plan-review) carry their own context -- they do not need injection
            because they ARE the workflow.
    """
    name: str
    description: str
    available_phases: tuple[str, ...]
    initial_phase: str
    suggested_transitions: dict[str, list[str]]
    phase_descriptions: dict[str, str]
    phase_guidance: dict[str, str]


# -- Curation directives (injected as phase_instructions) ---------------------
#
# Directives bind the static curation step prompts to a specific entry
# point. They own *what to look for* and *which source-gathering moves
# are authorized*. They must NOT own step mechanics (which belong to
# koan/phases/curation.py) or writing discipline (which belongs to the
# curation system prompt).

_POSTMORTEM_DIRECTIVE = (
    "## Source: postmortem\n"
    "\n"
    "The source for this curation is your conversation history with the\n"
    "user during the workflow that just completed. The transcript IS the\n"
    "task. Ignore the <task> block in step 1 -- it carries the parent\n"
    "workflow's task description, which is not your curation source.\n"
    "\n"
    "## What to harvest\n"
    "\n"
    "- Decisions made during the workflow, with rationale and rejected\n"
    "  alternatives.\n"
    "- Lessons from mistakes, corrections, or surprises.\n"
    "- Procedures that emerged from patterns the user reinforced.\n"
    "- Context facts about the project that surfaced during dialogue.\n"
    "\n"
    "## How to walk the transcript\n"
    "\n"
    "1. Step back. Identify 2-4 themes from this run -- the major\n"
    "   decisions, the surprises, the corrections, the reusable patterns.\n"
    "2. For each theme, walk the relevant turns and harvest candidates.\n"
    "   Most impactful first.\n"
    "\n"
    "## Forbidden moves\n"
    "\n"
    "- Do NOT call `koan_request_scouts`. The source is bounded by what\n"
    "  you already discussed in this run.\n"
    "- Do NOT read codebase files for new context. Anything you did not\n"
    "  already touch in the workflow is out of scope.\n"
    "- Do NOT call `koan_ask_question`. If clarification is needed,\n"
    "  surface it inside a batch yield instead.\n"
    "\n"
    "## What this phase produces\n"
    "\n"
    "Your output for this phase is `koan_memorize` calls (and `koan_forget`\n"
    "where DEPRECATE applies), not analysis. Step 1 is preparation; step 2\n"
    "is where the writes happen. A curation phase that ends with zero\n"
    "writes -- when the transcript clearly contains harvestable knowledge --\n"
    "is a failed phase."
)

_STANDALONE_DIRECTIVE = (
    "## Source: standalone curation\n"
    "\n"
    "Your source is determined by the user's task in the <task> block\n"
    "above combined with the current state of memory in <existing_memory>.\n"
    "Unlike the postmortem entry point, you do NOT have a recent workflow\n"
    "transcript to draw from -- context must be gathered.\n"
    "\n"
    "## Mode pivot (do this in step 1, before gathering)\n"
    "\n"
    "Decide which mode you are in by walking these four moves:\n"
    "\n"
    "- **Describe**  Paraphrase the user's <task> in one sentence.\n"
    "- **Explain**   Look at <existing_memory>: empty, sparse, or\n"
    "                populated? Does the task reference specific source\n"
    "                material (a doc path, a subsystem name, a file)?\n"
    "- **Plan**      Pick exactly one mode:\n"
    "                  - **Review**     Memory is populated and the task\n"
    "                                   is health/maintenance (\"audit my\n"
    "                                   memory\", \"check for stale\n"
    "                                   entries\", \"find duplicates\").\n"
    "                  - **Document**   The task points at specific\n"
    "                                   source material -- a doc, a spec,\n"
    "                                   a subsystem, a path. Ingest it.\n"
    "                  - **Bootstrap**  Memory is empty or near-empty and\n"
    "                                   the task is open-ended (\"set up\n"
    "                                   memory for this project\").\n"
    "- **Select**    Commit to the mode. Name it in your end-of-step-1\n"
    "                orientation summary so the user can correct you\n"
    "                before you start gathering.\n"
    "\n"
    "## Source-gathering posture by mode\n"
    "\n"
    "- **Review**:    Read suspect entries directly from `.koan/memory/`.\n"
    "                 Dispatch 1-2 scouts via `koan_request_scouts` to\n"
    "                 verify high-stakes decisions against the current\n"
    "                 codebase. Use `koan_ask_question` only for\n"
    "                 ambiguities the files cannot resolve.\n"
    "\n"
    "- **Document**:  Read the source the user pointed at directly. If\n"
    "                 it spans multiple subsystems, dispatch 2-4 scouts\n"
    "                 in parallel to cover each one. Treat the document\n"
    "                 as authoritative for facts; treat the codebase as\n"
    "                 authoritative for current state.\n"
    "\n"
    "- **Bootstrap**: Lean heavily on scouts -- 3-5 to cover the major\n"
    "                 subsystems. Read README, AGENTS.md, and CLAUDE.md\n"
    "                 directly if they exist. Interview the user via\n"
    "                 `koan_ask_question` for context the codebase\n"
    "                 cannot reveal: team size, deployment, conventions,\n"
    "                 historical decisions.\n"
    "\n"
    "In every mode you may always read individual memory entries\n"
    "directly from `.koan/memory/NNNN-*.md` -- direct reads are the\n"
    "intended duplicate-detection path. Writes still go through\n"
    "`koan_memorize` / `koan_forget` only.\n"
    "\n"
    "## What this phase produces\n"
    "\n"
    "Your output for this phase is `koan_memorize` calls (and `koan_forget`\n"
    "where DEPRECATE applies), not analysis. Step 1 is preparation; step 2\n"
    "is where the writes happen. A curation phase that ends with zero\n"
    "writes -- when there is genuine novel knowledge to capture -- is a\n"
    "failed phase."
)


# -- Plan workflow -------------------------------------------------------------
# intake → plan-spec → plan-review → execute → curation
# Lightweight focused-change pipeline. Single executor spawn.

PLAN_WORKFLOW = Workflow(
    name="plan",
    description="Plan an implementation approach, review it, then execute",
    available_phases=("intake", "plan-spec", "plan-review", "execute", "curation"),
    initial_phase="intake",
    suggested_transitions={
        "intake":       ["plan-spec", "execute"],
        "plan-spec":    ["plan-review", "execute"],
        "plan-review":  ["plan-spec", "execute"],
        "execute":      ["curation", "plan-review"],
        "curation":     [],
    },
    phase_descriptions={
        "intake":      "Explore the codebase and align on requirements through Q&A",
        "plan-spec":   "Write a technical implementation plan grounded in the codebase",
        "plan-review": "Evaluate the plan for completeness, correctness, and risks",
        "execute":     "Hand off the plan to an executor agent for implementation",
        "curation":    "Capture lessons, decisions, and context from the completed run",
    },
    phase_guidance={
        "intake": (
            "## Scope\n"
            "This is a **plan** workflow \u2014 a focused change touching a bounded\n"
            "area of the codebase.\n"
            "\n"
            "## Downstream\n"
            "The understanding you build here feeds into an implementation plan.\n"
            "The planner needs enough context to write specific file-level\n"
            "instructions, but does not need exhaustive coverage of the entire\n"
            "codebase.\n"
            "\n"
            "## Investigation posture\n"
            "- **Prefer direct reading.** For focused changes, reading the referenced\n"
            "  files yourself is faster and more precise than dispatching scouts.\n"
            "- **Dispatch scouts** when the task references subsystems you're unfamiliar\n"
            "  with, or when dependency tracing would require opening more than ~10 files.\n"
            "- If you dispatch scouts, 1\u20133 is typical for a plan workflow.\n"
            "\n"
            "## Question posture\n"
            "- Always ask at least one round of questions. Even well-specified tasks\n"
            "  benefit from confirming assumptions and surfacing implicit decisions.\n"
            "- A plan workflow needs 2\u20134 targeted questions covering: approach\n"
            "  confirmation, constraint verification, and scope boundaries.\n"
            "- The user wants to be consulted \u2014 asking questions is a feature, not a\n"
            "  burden. When in doubt, ask.\n"
            "\n"
            "## User override\n"
            "The user can always ask you to go deeper, dispatch more scouts, or ask\n"
            "more questions. Follow their lead over these defaults."
        ),
        "execute": (
            "## What to hand off\n"
            "Call `koan_request_executor` with:\n"
            "- **artifacts**: `[\"plan.md\"]` \u2014 the implementation plan.\n"
            "- **instructions**: Key decisions from plan-review, user clarifications,\n"
            "  or constraints. Do NOT repeat plan.md contents \u2014 the executor reads\n"
            "  it directly. Instructions are for context that isn't in the files.\n"
            "\n"
            "## After execution\n"
            "Report the result. If the executor failed or asked questions, relay\n"
            "the situation to the user and suggest next steps."
        ),
        "curation": _POSTMORTEM_DIRECTIVE,
    },
)


# -- Milestones workflow (stub) -----------------------------------------------
# Runs intake only. Phase boundary reports the workflow is not yet implemented.

MILESTONES_WORKFLOW = Workflow(
    name="milestones",
    description="Break work into milestones with phased delivery (coming soon)",
    available_phases=("intake",),
    initial_phase="intake",
    suggested_transitions={"intake": []},
    phase_descriptions={
        "intake": "Explore the codebase and align on requirements through Q&A",
    },
    phase_guidance={
        "intake": (
            "## Scope\n"
            "This is a **milestones** workflow \u2014 a broad initiative spanning\n"
            "multiple subsystems requiring significant codebase exploration.\n"
            "\n"
            "## Downstream\n"
            "The understanding you build here feeds into milestone decomposition\n"
            "and multi-phase planning. Downstream phases need comprehensive\n"
            "coverage: every affected subsystem, integration point, and constraint\n"
            "must be documented.\n"
            "\n"
            "## Investigation posture\n"
            "- **Dispatch scouts broadly.** Explore every subsystem the task touches\n"
            "  and adjacent areas that might be affected. 3\u20135 scouts is typical.\n"
            "- **Also read directly** \u2014 verify key scout findings against the actual\n"
            "  code, especially integration points and conventions.\n"
            "\n"
            "## Question posture\n"
            "- Ask multiple rounds of questions. For broad initiatives, 2\u20133 rounds\n"
            "  of 3\u20136 questions is typical.\n"
            "- Surface assumptions early. Each answer may reveal new areas to probe.\n"
            "- Probe cross-cutting concerns: shared patterns, naming conventions,\n"
            "  error handling strategies, test coverage expectations.\n"
            "\n"
            "## User override\n"
            "The user can always tell you to narrow scope or skip questions.\n"
            "Follow their lead over these defaults."
        ),
    },
)


# -- Curation workflow --------------------------------------------------------
# Standalone memory maintenance workflow (review directive).

CURATION_WORKFLOW = Workflow(
    name="curation",
    description="Maintain the project memory: review, bootstrap, or ingest documents",
    available_phases=("curation",),
    initial_phase="curation",
    suggested_transitions={"curation": []},
    phase_descriptions={
        "curation": "Review and maintain the project's memory entries",
    },
    phase_guidance={
        "curation": _STANDALONE_DIRECTIVE,
    },
)


# -- Registry -----------------------------------------------------------------

WORKFLOWS: dict[str, Workflow] = {
    "plan": PLAN_WORKFLOW,
    "milestones": MILESTONES_WORKFLOW,
    "curation": CURATION_WORKFLOW,
}


def get_workflow(name: str) -> Workflow:
    """Return the Workflow for the given name, or raise ValueError."""
    wf = WORKFLOWS.get(name)
    if wf is None:
        raise ValueError(f"Unknown workflow: {name!r}. Valid: {list(WORKFLOWS)}")
    return wf


def get_suggested_phases(workflow: Workflow, phase: str) -> list[str]:
    """Return the ordered suggested next phases for the current phase."""
    return list(workflow.suggested_transitions.get(phase, []))


def is_valid_transition(workflow: Workflow, from_phase: str, to_phase: str) -> bool:
    """Any phase in the workflow is reachable from any other (except self-transition).

    The user drives macro-level progression; suggested_transitions guides defaults
    but does not constrain choices.
    """
    return to_phase in workflow.available_phases and to_phase != from_phase
