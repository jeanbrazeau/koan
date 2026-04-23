# Eval Fixtures

Each subdirectory is one benchmark fixture. A fixture owns a project snapshot
and a set of rubrics. One fixture may host multiple tasks.

## Directory layout

    <fixture>/
        repo/                       -- git submodule pinned to a specific commit of the target project
        rubrics/
            <phase>/
                summary.md          -- grades the phase summary
                questions.md        -- grades questions asked during the phase
                artifacts.md        -- grades files created/modified during the phase
                overall.md          -- grades the phase holistically
        tasks/
            <task>/
                task.md             -- task description (UTF-8 plain text)
                rubrics/            -- optional task-level per-phase rubric addenda (invariant across directed-phase variants)
                    <phase>/
                        <section>.md
                cases/              -- one markdown file per test case; each defines a workflow, a directed phase sequence, and a cross-cutting rubric
                    <slug>.md

## Rubric sections

Each phase supports four sections: `summary`, `questions`, `artifacts`, `overall`.

Cross-cutting / overall rubrics live in case files under `tasks/<task>/cases/<slug>.md`.

## Test cases

Each file under `tasks/<task>/cases/` is a test case. It is a markdown file
with YAML frontmatter followed by the cross-cutting rubric body.

Frontmatter schema:

    ---
    workflow: plan              # string -- which koan workflow to run
    directed_phases:            # list[str] -- phase sequence, last entry must be "done"
      - intake
      - plan-spec
      - done
    ---

The body below the closing `---` is the cross-cutting rubric used by the
`test_run` test (via `CrossPhaseCoherence`). It must end with:
`Respond with PASS or FAIL on the last line.`

Phase-scoring semantics: a per-phase test grades only if the phase appears
in the case's `directed_phases`. Tests for phases absent from the list are
skipped even when a rubric file exists on disk.

## Rubric layering

At grade time the scorer concatenates the fixture-level rubric (required) with
the optional task-level rubric addendum. Fixture rubric comes first; task
addendum is appended. If neither exists for a (phase, section) pair, the scorer
is skipped for that sample (no score recorded, not a FAIL).

## Per-section rubric format

Per-section rubric files (under `rubrics/<phase>/<section>.md`) must list each
evaluation criterion as exactly one bullet line starting with `- ` or `* `.
`RubricComplianceMetric` calls the judge once per bullet and averages the
per-criterion pass/fail verdicts into a pass-rate score (threshold=1.0 by
default, so all criteria must pass). Prose paragraphs and blank lines are
ignored by the parser.

**Rules for per-section rubric files:**

- Each criterion must be a single bullet line -- do NOT combine multiple
  criteria with "and" or list sub-items under one bullet.
- Do NOT end per-section rubric files with `Respond with PASS or FAIL on
  the last line.` -- that directive is parsed by GEval but ignored (and
  potentially misleading) for `RubricComplianceMetric`.
- Do NOT write a rubric file with only prose and no bullets -- the scorer
  raises `ValueError` when a file exists but yields zero criteria.
- Self-contained bullets: do not use "see above" or "the preceding list" in
  a bullet; each criterion is sent to the judge in isolation.

**Exception:** case-body rubrics under `tasks/<task>/cases/<slug>.md` are
judged by `CrossPhaseCoherence` (a GEval instance) which uses the full body
as `criteria=`. These files retain the `Respond with PASS or FAIL on the
last line.` directive.

## Dimensional metric set

The eval harness produces five metric names per test invocation:

| Metric name          | Type                  | What it measures                                  |
|----------------------|-----------------------|---------------------------------------------------|
| `RubricCompliance`   | `RubricComplianceMetric` (custom BaseMetric) | Per-bullet pass-rate for a (phase, section) rubric |
| `CrossPhaseCoherence`| GEval                 | Cross-phase coherence using the case rubric body  |
| `Duration`           | Programmatic BaseMetric | Wall-clock seconds for the full run              |
| `TokenCost`          | Programmatic BaseMetric | Total input + output tokens (orchestrator only)  |
| `ToolCallCount`      | Programmatic BaseMetric | Total tool calls across all phases               |

`RubricCompliance` and `CrossPhaseCoherence` require a live LLM judge call
(via `JUDGE_MODEL = GeminiModel("gemini-3-pro-preview")`). The three
programmatic metrics read from `additional_metadata` and need no judge call.

## Artifact content limitation

Artifact content in the `artifacts` payload is read from disk at workflow
completion, not per-phase. Files modified in a later phase will show their
final content, not the content they had at the end of the phase that created
them. This is acceptable for the initial scope (intake + plan-spec) because:

- intake produces no artifacts
- plan-spec produces plan.md, which execute may modify -- but the initial
  eval scope does not run execute

## Test invocation

The test module `tests/evals/test_koan.py` defines a single pytest function
`test_workflow_suite` that invokes `deepeval.evaluate()` over all discovered
cases and rubric sections in one shot. Run via `pytest tests/evals/` or
`deepeval test run tests/evals/`. Row-level granularity is preserved on the
DeepEval dashboard via `LLMTestCase.name` (shaped as
`<fixture>/<task>/<case>/<phase>/<section>` for rubric rows and
`<fixture>/<task>/<case>/workflow` for run rows) rather than via pytest test IDs
-- there is exactly one pytest test ID (`tests/evals/test_koan.py::test_workflow_suite`).

## Authoring tips

- Keep rubrics tightly scoped. A rubric bullet that checks one thing is more
  reliably graded by the judge LLM than one that checks five.
- Phrase criteria as observable facts ("plan.md is present in all_present")
  rather than subjective judgments ("the plan is good").
- End every case-body rubric with exactly: `Respond with PASS or FAIL on the last line.`
- Do NOT end per-section rubric files with that directive.

## Hydrating fixtures

Each fixture's `repo/` directory is a git submodule. After cloning, run:

    git submodule update --init --recursive

to hydrate all submodules. Without this the runner sees an empty directory
and starts koan against an empty project, producing no artifacts.

## Bumping a fixture snapshot

To advance a fixture to a newer commit, check out the desired SHA inside
the submodule and stage the updated pointer:

    git -C evals/fixtures/<name>/repo checkout <sha>
    git add evals/fixtures/<name>/repo
    git commit -m "chore: bump <name> fixture to <sha>"
