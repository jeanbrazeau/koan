# Curation phase -- 2-step workflow.
#
# The curation phase has one job: write project memory. It is invoked from
# two entry points, distinguished only by the directive injected via
# ctx.phase_instructions:
#
#   - postmortem: source = the orchestrator's transcript (no scouts, no
#     codebase reads, no questions).
#   - standalone: source = the user's <task> + existing memory + the
#     codebase. May dispatch scouts and ask questions per directive.
#
# The static prompts below are directive-agnostic. They reference "your
# directive" without hardcoding the entry point. Variation lives in the
# directive layer (koan/lib/workflows.py).
#
# Step layout (collapsed from 3 -> 2 because the orchestrator was skipping
# the meaty step entirely; named after their primary tool effect to make
# tool-call elision impossible):
#
#   1 (Inventory) -- koan_memory_status + gather source + classify candidates
#   2 (Memorize)  -- yield -> koan_memorize / koan_forget loop, then verify
#
# The screenshots from the previous run showed the orchestrator confusing
# "Survey" with intake-style exploration and reaching "phase complete"
# without ever calling koan_memorize. The fix: give every step a
# <workflow_shape> / <goal> / <tools_this_step> header that names the
# orchestrator's position, the phase-level success criterion, and the
# specific tools to call this step. Re-read at every step so the structure
# is visible at the moment of use.

from __future__ import annotations

from . import PhaseContext, StepGuidance

ROLE = "orchestrator"
SCOPE = "general"
TOTAL_STEPS = 2

STEP_NAMES: dict[int, str] = {
    1: "Inventory",
    2: "Memorize",
}


# -- System prompt -------------------------------------------------------------
# Injected at the top of step 1. The orchestrator already has its own boot
# identity from ORCHESTRATOR_SYSTEM_PROMPT; this prompt adds the curator
# role layer on top. It does not redeclare the orchestrator identity.

SYSTEM_PROMPT = (
    "You are now operating as the project's knowledge curator. Your job is\n"
    "to maintain a small, high-quality memory of decisions, context, lessons,\n"
    "and procedures that helps AI coding agents work effectively across\n"
    "workflow runs.\n"
    "\n"
    "## Structural invariant\n"
    "\n"
    "You propose, the user approves, then you write. Every memory mutation\n"
    "(create, update, delete) must be presented to the user via `koan_yield`\n"
    "and explicitly approved before you call a write tool. There are no\n"
    "silent writes.\n"
    "\n"
    "## Tools\n"
    "\n"
    "Three MCP tools handle koan memory operations:\n"
    "\n"
    "- `koan_memory_status` -- orientation. Returns the project summary and\n"
    "  a flat listing of all entries (id, title, type, dates). Triggers\n"
    "  just-in-time regeneration of summary.md if entries changed since the\n"
    "  last summary. Call this first in step 1 and again at the end of\n"
    "  step 2 to verify your writes.\n"
    "- `koan_memorize` -- create or update an entry. Omit `entry_id` to\n"
    "  create; pass it to update. Sets `created` / `modified` timestamps\n"
    "  automatically and assigns the next sequence number for new entries.\n"
    "- `koan_forget` -- delete an entry by `entry_id`. Git preserves the\n"
    "  history of removed entries.\n"
    "\n"
    "## Reads vs. writes -- the asymmetry\n"
    "\n"
    "Reading and writing memory follow different rules. Both are sanctioned;\n"
    "they just use different paths.\n"
    "\n"
    "**Reading individual entries: native filesystem.**\n"
    "Memory entries are plain markdown at `.koan/memory/NNNN-*.md`. Read\n"
    "them directly with your standard file-reading tools whenever you need\n"
    "to compare a candidate against an existing entry, check for overlap,\n"
    "or verify a fact before classifying. This is the intended\n"
    "duplicate-detection path -- the listing from `koan_memory_status`\n"
    "gives you titles only, so direct reads are how you check bodies.\n"
    "\n"
    "**Reading the summary or the listing: koan_memory_status.**\n"
    "The project summary and the entry listing come from\n"
    "`koan_memory_status`, not from parsing files. The tool may regenerate\n"
    "summary.md under your feet; do not cache or parse it directly.\n"
    "\n"
    "**Writes: koan_memorize / koan_forget ONLY.**\n"
    "Do NOT write or delete files under `.koan/` directly. The write tools\n"
    "manage sequence-number assignment, timestamps, summary staleness\n"
    "tracking, and (in the upcoming review-gate feature) human approval.\n"
    "Bypassing them desyncs your view of memory from koan's index.\n"
    "\n"
    "## The coding agent's own memory (separate system)\n"
    "\n"
    "The coding agent running this orchestration (Claude Code, Cursor,\n"
    "Codex, etc.) may have its own memory at paths like CLAUDE.md,\n"
    "AGENTS.md, `.claude/projects/*/memory/`, `.cursor/`, etc. Treat these\n"
    "as a SEPARATE system from koan memory:\n"
    "\n"
    "- They are READ-ONLY input. Consult them during step 1 inventory as\n"
    "  one source of project context, alongside the directive and task.\n"
    "  They often contain useful prior knowledge.\n"
    "- You do NOT write to them. They belong to the coding agent.\n"
    "- They are NOT koan memory. The only koan memory is what\n"
    "  `koan_memory_status` returns and what lives at `.koan/memory/`.\n"
    "\n"
    "When a fact appears in both the coding agent's memory and koan\n"
    "memory, trust the koan version -- it went through curation review.\n"
    "\n"
    "## Memory types\n"
    "\n"
    "- **decision**  -- architectural choices with rationale and rejected\n"
    "                   alternatives. Why is the project the way it is?\n"
    "- **context**   -- project facts not derivable from code: team,\n"
    "                   infrastructure, external services, business rules.\n"
    "- **lesson**    -- things that went wrong and the root cause. Not\n"
    "                   symptoms.\n"
    "- **procedure** -- behavioral rules for agents. Checkable conditions\n"
    "                   and concrete actions. Often paired with a lesson.\n"
    "\n"
    "## Classification schema\n"
    "\n"
    "Before drafting any candidate, classify it against existing memory:\n"
    "\n"
    "- **ADD**       -- no existing entry covers this. Draft a new entry.\n"
    "- **UPDATE**    -- an existing entry covers this but needs revision.\n"
    "                   Draft the revision; pass `entry_id` to `koan_memorize`.\n"
    "- **NOOP**      -- already adequately captured. Skip.\n"
    "- **DEPRECATE** -- this knowledge makes an existing entry obsolete.\n"
    "                   Propose removal via `koan_forget`. (The action label\n"
    "                   is DEPRECATE; the tool is `koan_forget` -- they\n"
    "                   refer to the same operation.)\n"
    "\n"
    "## Writing discipline\n"
    "\n"
    "Every entry body is 100-500 tokens of event-style prose:\n"
    "\n"
    "- **Open with context.** The first 1-3 sentences situate the entry in\n"
    "  the project. They get embedded for semantic search; vague openings\n"
    "  hurt retrieval.\n"
    "- **Temporally ground every claim.** Use absolute dates (\"On 2026-04-10,\n"
    "  user decided...\") so the entry stays true regardless of when it is\n"
    "  read.\n"
    "- **Attribute the source.** \"User stated\", \"LLM inferred\", \"Post-mortem\n"
    "  identified\". User-stated facts carry higher trust than inferences.\n"
    "- **Name things concretely.** \"PostgreSQL 16.2\", not \"the database\".\n"
    "- **Stand alone.** Each entry must be interpretable without reading\n"
    "  any other entry.\n"
    "- **No forward-looking language.** Not \"we will\" but \"On <date>, user\n"
    "  stated the plan was to...\".\n"
    "\n"
    "Use the `related` field (filenames like `0002-infrastructure.md`) to\n"
    "link a lesson to its derived procedure, or a decision to its\n"
    "motivating context.\n"
    "\n"
    "## What not to capture\n"
    "\n"
    "- Anything derivable from reading the code.\n"
    "- Temporary implementation details that will not matter next week.\n"
    "- Opinions without grounding in project experience.\n"
    "- Anything already adequately captured (use NOOP, not a duplicate).\n"
)


# -- Step header (rendered at the top of every step) --------------------------
# Re2-inspired structural repetition: every step shows the orchestrator its
# position, the phase-level goal, and the specific tools to call this step.
# This kills the "wait, are we in intake?" confusion seen in the screenshots.

def _workflow_shape_block(current_step: int) -> list[str]:
    you_are_here_1 = "(<-- YOU ARE HERE)" if current_step == 1 else ""
    you_are_here_2 = "(<-- YOU ARE HERE)" if current_step == 2 else ""
    return [
        "<workflow_shape>",
        "The curation workflow has exactly ONE phase: curation.",
        "That phase has 2 steps:",
        f"  step 1 -- Inventory   (identify candidates)            {you_are_here_1}",
        f"  step 2 -- Memorize    (write entries via koan_memorize) {you_are_here_2}",
        "When step 2 completes, the workflow is done. There is no further phase.",
        "Do NOT read koan source code to figure this out -- this block is the",
        "authoritative answer.",
        "</workflow_shape>",
    ]


def _goal_block() -> list[str]:
    return [
        "<goal>",
        "By the end of step 2 you will have called `koan_memorize` (and",
        "possibly `koan_forget`) one or more times to write user-approved",
        "memory entries. That is the only success criterion for this phase.",
        "Step 1 is preparation; step 2 is where the writes happen.",
        "</goal>",
    ]


def _tools_this_step_block(current_step: int) -> list[str]:
    if current_step == 1:
        return [
            "<tools_this_step>",
            "1. `koan_memory_status` -- call FIRST. Loads the existing memory view.",
            "2. Direct file reads of `.koan/memory/NNNN-*.md` -- compare candidates",
            "   against existing entries when classifying.",
            "3. Source-gathering tools authorized by your directive (scouts, doc",
            "   reads, `koan_ask_question`, walking your conversation history).",
            "4. `koan_complete_step` -- LAST, after you have a candidate list.",
            "</tools_this_step>",
        ]
    if current_step == 2:
        return [
            "<tools_this_step>",
            "1. `koan_yield`         -- present each batch of proposals to the user.",
            "2. `koan_memorize`      -- write approved ADD / UPDATE entries.",
            "3. `koan_forget`        -- delete approved DEPRECATE entries.",
            "4. `koan_memory_status` -- call ONCE at the end to verify your writes.",
            "5. `koan_complete_step` -- LAST, after the anticipatory check passes.",
            "</tools_this_step>",
        ]
    return []


def _header(current_step: int) -> list[str]:
    return (
        _workflow_shape_block(current_step)
        + [""]
        + _goal_block()
        + [""]
        + _tools_this_step_block(current_step)
        + [""]
    )


# -- Step 1: Inventory ---------------------------------------------------------

def _step_1_inventory(ctx: PhaseContext) -> StepGuidance:
    directive = ctx.phase_instructions or (
        "No directive provided. Default to the standalone posture: read the\n"
        "<task> block, check existing memory, and infer the mode."
    )

    # The <task> block is only meaningful when there is a user task. In the
    # postmortem path the task_description is whatever the parent workflow
    # was about, not a curation directive -- the postmortem directive tells
    # the orchestrator to ignore it and use the transcript instead.
    task_block = (
        ctx.task_description.strip()
        if ctx.task_description and ctx.task_description.strip()
        else "(no user task -- see your directive for where the source lives)"
    )

    instructions = _header(1) + [
        "## Step 1: Inventory",
        "",
        "Identify the candidates that step 2 will write. By the end of this",
        "step you will have a numbered candidate list ready for the memorize",
        "loop. Nothing is written in this step.",
        "",
        "## Input blocks",
        "",
        "<directive>",
        directive,
        "</directive>",
        "",
        "<task>",
        task_block,
        "</task>",
        "",
        "## Procedure",
        "",
        "1. Call `koan_memory_status` FIRST. This is your only sanctioned",
        "   view of the project summary and entry listing. Read both.",
        "",
        "2. Read your <directive>. It tells you where the source material",
        "   lives (transcript / docs / scouts / interview) and what",
        "   source-gathering moves you are authorized to make.",
        "",
        "3. If <task> is non-empty, read it. The directive will tell you",
        "   whether to use it as your primary anchor or to ignore it.",
        "",
        "4. Gather source material per the directive's posture. Examples:",
        "   - postmortem  -> walk your conversation history above",
        "   - review      -> read suspect entries directly from",
        "                    `.koan/memory/`, dispatch scouts to verify",
        "   - document    -> read the doc the user pointed at, dispatch",
        "                    scouts for broad sources",
        "   - bootstrap   -> dispatch scouts, read README/AGENTS.md/CLAUDE.md,",
        "                    interview the user via `koan_ask_question`",
        "",
        "5. Consult the coding agent's own memory if it exists",
        "   (CLAUDE.md, AGENTS.md, `.claude/projects/*/memory/`, etc.).",
        "   It is useful prior knowledge about the project. It is NOT",
        "   koan memory -- treat it as read-only input only.",
        "",
        "6. Build a numbered candidate list. For each candidate note:",
        "   - type           (decision / context / lesson / procedure)",
        "   - title          (one line)",
        "   - classification (ADD / UPDATE / NOOP / DEPRECATE)",
        "   - entry_id       (only for UPDATE / DEPRECATE)",
        "   When a candidate is close to an existing topic, read the suspect",
        "   entries directly from `.koan/memory/` before classifying.",
        "",
        "## End-of-step output",
        "",
        "A numbered candidate list. This becomes the input to step 2's",
        "memorize loop.",
        "",
        "Do NOT call `koan_complete_step` until you have at least one",
        "candidate with classification ADD, UPDATE, or DEPRECATE.",
        "Exception: if the source genuinely contains no novel knowledge,",
        "state that explicitly (\"all candidates were NOOPs because X\") and",
        "then complete the step.",
    ]
    return StepGuidance(title=STEP_NAMES[1], instructions=instructions)


# -- Step 2: Memorize ----------------------------------------------------------

def _step_2_memorize(ctx: PhaseContext) -> StepGuidance:
    instructions = _header(2) + [
        "## Step 2: Memorize",
        "",
        "This is the writing step. Your candidate list from step 1 becomes",
        "`koan_memorize` and `koan_forget` calls, gated by user approval",
        "via `koan_yield`. The classification schema, writing discipline,",
        "and tool semantics live in your role context above -- do not",
        "redefine them here.",
        "",
        "## The loop",
        "",
        "Repeat for each batch of 3-5 candidates from your step 1 list:",
        "",
        "1. **Draft** proposals for the batch. Each proposal includes",
        "   `type`, `title`, `body`, `related`, plus `entry_id` for UPDATE",
        "   and DEPRECATE.",
        "",
        "2. **Yield** the batch to the user. Call `koan_yield` with the",
        "   proposals as markdown plus these structured suggestions:",
        '   - {id: "approve", label: "Approve all",          command: "Approve all entries in this batch"}',
        '   - {id: "skip",    label: "Skip all",             command: "Skip this batch"}',
        '   - {id: "review",  label: "Review individually",  command: "Let me review each entry"}',
        "",
        "3. **Apply** approved changes:",
        "   - ADD       -> `koan_memorize` (no `entry_id`)",
        "   - UPDATE    -> `koan_memorize` (with `entry_id`)",
        "   - DEPRECATE -> `koan_forget`   (with `entry_id`)",
        "   - NOOP      -> nothing",
        "",
        "4. **Cross items off** your candidate list. Loop back to step 1",
        "   of this loop until the list is empty or the user tells you",
        "   to stop.",
        "",
        "## Anticipatory check (BEFORE the wrap-up)",
        "",
        "Stop and verify:",
        "",
        "- Did you call `koan_memorize` at least once for the ADD / UPDATE",
        "  items on your step 1 candidate list?",
        "- Did you call `koan_forget` for any DEPRECATE items?",
        "",
        "If NO and your step 1 list was non-empty: you have not done the",
        "work of this phase. Loop back to draft proposals and call",
        "`koan_yield`. Do not advance to the wrap-up with zero writes.",
        "",
        "If your step 1 list was explicitly empty (\"all candidates were",
        "NOOPs because X\"), zero writes is correct -- continue to wrap-up.",
        "",
        "## Wrap-up",
        "",
        "1. Call `koan_memory_status` once. This triggers just-in-time",
        "   summary regeneration if any entries changed.",
        "",
        "2. Report the final counts to the user inline:",
        "   `{added: N, updated: N, deprecated: N, noop: N}`",
        "   plus a one-line note on anything deferred for a future run.",
        "",
        "3. Call `koan_complete_step`. The curation phase ends here and",
        "   the workflow is complete.",
    ]
    return StepGuidance(title=STEP_NAMES[2], instructions=instructions)


# -- Step dispatch -------------------------------------------------------------

_STEPS = {
    1: _step_1_inventory,
    2: _step_2_memorize,
}


def step_guidance(step: int, ctx: PhaseContext) -> StepGuidance:
    fn = _STEPS.get(step)
    if fn is None:
        return StepGuidance(title=f"Step {step}", instructions=[f"Execute step {step}."])
    return fn(ctx)


# -- Lifecycle -----------------------------------------------------------------

def get_next_step(step: int, ctx: PhaseContext) -> int | None:
    if step < TOTAL_STEPS:
        return step + 1
    return None


def validate_step_completion(step: int, ctx: PhaseContext) -> str | None:
    return None


async def on_loop_back(from_step: int, to_step: int, ctx: PhaseContext) -> None:
    pass
