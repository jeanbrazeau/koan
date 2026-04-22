# evals/tasks.py
# Inspect AI @task factories for koan evals.
#
# Two discovery paths:
#
#   1. The static @task `koan` below runs every discovered case as one
#      multi-sample task. Per-sample scoring is filtered by
#      `directed_phases` carried in Sample metadata -- scorers for phases
#      absent from a case's directed_phases return None automatically.
#
#   2. One @task factory is synthesised per case at import time by
#      assigning into globals() (names of the form
#      `koan_<fixture>_<task>_<case>`). These let you target a single
#      case via `inspect eval evals/tasks.py@koan_<...>`.
#
# Inspect's CLI discovery is AST-based: it scans the file for a
# top-level `@task` decorator before it will import the module. The
# static `koan` function below is what passes that gate. Without it,
# the dynamic factories never get registered because Inspect never
# even imports this file. (Lesson: `python -c "import evals.tasks"`
# succeeds even when `inspect eval evals/tasks.py` finds zero tasks.)

from __future__ import annotations

from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset

from evals.cases import Case, discover_cases
from evals.dataset import FIXTURES_DIR, load_dataset
from evals.scorers import (
    intake_artifacts,
    intake_overall,
    intake_questions,
    intake_summary,
    overall_pass_rate,
    plan_spec_artifacts,
    plan_spec_overall,
    plan_spec_questions,
    plan_spec_summary,
    workflow_overall,
)
from evals.solver import koan_solver


_SCORERS_BY_PHASE = {
    "intake": [intake_summary, intake_questions, intake_artifacts, intake_overall],
    "plan-spec": [
        plan_spec_summary,
        plan_spec_questions,
        plan_spec_artifacts,
        plan_spec_overall,
    ],
}


@task
def koan() -> Task:
    """Run every discovered case as one multi-sample task.

    Each case is a Sample; per-sample scoring is gated by
    `directed_phases` in Sample metadata, so phase scorers that don't
    apply return None for samples where that phase wasn't in the case's
    directed sequence. The full scorer set is attached here; the
    _rubric_scorer gate handles per-sample filtering.
    """
    # Order matters: workflow_overall is FIRST so the task-list "Score"
    # column renders the end-to-end holistic judgment as the headline
    # (rather than the first per-phase sub-criterion). overall_pass_rate
    # is LAST so it can read state.scores populated by the preceding
    # scorers and return a pass ratio.
    all_scorers = [
        workflow_overall(),
        intake_summary(),
        intake_questions(),
        intake_artifacts(),
        intake_overall(),
        plan_spec_summary(),
        plan_spec_questions(),
        plan_spec_artifacts(),
        plan_spec_overall(),
        overall_pass_rate(),
    ]
    return Task(
        dataset=load_dataset(),
        solver=koan_solver(),
        scorer=all_scorers,
    )


# -- Per-case @task factories (dynamic) ---------------------------------------
# Registered via globals() so each case is addressable individually:
#
#   inspect eval evals/tasks.py@koan_koan_1_yolo_flag_intake_plan_spec
#
# Requires the static @task above to satisfy Inspect's AST-based discovery
# gate; the module-exec that registers these happens only when the gate
# passes.


def _fn_name(case: Case) -> str:
    def _ident(s: str) -> str:
        return s.replace("-", "_")
    return f"koan_{_ident(case.fixture_id)}_{_ident(case.task_id)}_{_ident(case.case_id)}"


def _single_case_dataset(case: Case) -> MemoryDataset:
    full = load_dataset()
    sid = f"{case.fixture_id}/{case.task_id}/{case.case_id}"
    return MemoryDataset(
        [s for s in full.samples if s.id == sid],
        name=f"koan-bench-{sid}",
    )


def _make_task(case: Case):
    # Close over `case` via argument to avoid the late-binding loop-variable
    # pitfall -- each call to _make_task captures its own `case` object.
    # Scorer order mirrors the static `koan` task: workflow_overall first
    # (headline), per-phase scorers next, overall_pass_rate last (reads
    # state.scores populated by the preceding scorers).
    phases_scored = [p for p in case.directed_phases if p != "done"]
    scorers = [workflow_overall()]
    for ph in phases_scored:
        scorers.extend(factory() for factory in _SCORERS_BY_PHASE.get(ph, []))
    scorers.append(overall_pass_rate())

    fn_name = _fn_name(case)

    def _factory() -> Task:
        return Task(
            dataset=_single_case_dataset(case),
            solver=koan_solver(),
            scorer=scorers,
        )

    # Set __name__ before applying @task so the registry key matches the
    # globals() key. inspect_ai's @task decorator uses __name__ for both
    # the registry entry and the task name shown in logs/reports.
    _factory.__name__ = fn_name
    _factory.__qualname__ = fn_name

    return task(_factory)


for _case in discover_cases(FIXTURES_DIR):
    globals()[_fn_name(_case)] = _make_task(_case)
