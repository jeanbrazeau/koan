---
title: Eval test cases as frontmatter markdown files with dynamic @task synthesis
  and directed_phases-gated per-phase scoring
type: decision
created: '2026-04-19T15:19:45Z'
modified: '2026-04-19T15:19:45Z'
related:
- 0059-eval-rubric-layout-directory-per-phase-with-fixed.md
- 0060-eval-fixture-data-model-one-snapshot-per-fixture.md
- 0061-directedphases-fixed-phase-sequence-for-eval.md
---

The koan-bench Inspect AI test-case model in `evals/` was introduced on 2026-04-19 during a reorganization that split fixture state from test-case definition. On 2026-04-19, Leon decided that each test case is a single markdown file at `evals/fixtures/<fixture>/tasks/<task>/cases/<slug>.md` with YAML frontmatter declaring `workflow` (string, e.g. `"plan"`) and `directed_phases` (a list ending in `"done"`). The body below the closing `---` is the cross-cutting rubric graded by the `workflow_overall` scorer. Leon stated the reframe: "the rubrics are actually test cases, but separately we want to execute the workflow in a few directed ways." Cases are parsed by a new `evals/cases.py` module using `yaml.safe_load` (no new dependency -- `pyyaml` was already in `pyproject.toml`).

Leon decided that `evals/tasks.py` synthesizes one Inspect `@task` per discovered case at module import time by writing into `globals()`, with function names of the form `koan_<fixture>_<task>_<case>` and hyphens converted to underscores for Python-identifier compliance. A `_make_task(case)` helper creates the closure so each factory captures its own `case` variable, avoiding Python's late-binding loop-variable pitfall. The critical verification on 2026-04-19 was `uv run inspect eval evals/tasks.py --list` confirming that Inspect AI's module scanner picks up factories registered via `globals()` assignment. Each factory wires only the scorers for phases in its case's `directed_phases`; per-phase scorers return `None` (Inspect skips them) when the scorer's phase is not in the Sample's declared `directed_phases` after dropping `"done"`. The `workflow_overall` scorer loads its rubric from the case body (stored in Sample metadata under `overall_rubric`), not from a separate file.

Rejected alternatives on 2026-04-19 during intake: JSON sidecar files next to each case (Leon called them "ugly"); one `@task` over a multi-Sample dataset (Leon rejected it for losing per-variant addressability under `inspect eval ...@<name>`); manual per-case registry in `tasks.py` (Leon rejected it for breaking data-driven discovery); explicit `phases_scored` frontmatter field (Leon rejected as duplicating information already in `directed_phases`); flat `evals/cases/*.md` tree with fixture+task in frontmatter (Leon rejected for weaker cohesion with task state); nested case directories under a separate top-level `cases/` tree mirroring `fixtures/` (Leon rejected in favor of co-locating cases with task state under `tasks/<t>/cases/`).
