# evals/tasks.py
# Inspect AI @task factories, one per discovered case file.
#
# Cases are enumerated at module import time; for each case, a
# factory function named `koan_<fixture>_<task>_<case>` is written
# into globals() so Inspect AI's module scanner picks it up.
# Each factory wires scorers based on the case's directed_phases.

from __future__ import annotations

from pathlib import Path

from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset, Sample

from evals.cases import Case, discover_cases
from evals.dataset import FIXTURES_DIR, load_dataset
from evals.scorers import (
    intake_artifacts,
    intake_overall,
    intake_questions,
    intake_summary,
    plan_spec_artifacts,
    plan_spec_overall,
    plan_spec_questions,
    plan_spec_summary,
    workflow_overall,
)
from evals.solver import koan_solver


_SCORERS_BY_PHASE = {
    "intake": [intake_summary, intake_questions, intake_artifacts, intake_overall],
    "plan-spec": [plan_spec_summary, plan_spec_questions, plan_spec_artifacts, plan_spec_overall],
}


def _fn_name(case: Case) -> str:
    """koan_<fixture>_<task>_<case> with hyphens -> underscores."""
    def _ident(s: str) -> str:
        return s.replace("-", "_")
    return f"koan_{_ident(case.fixture_id)}_{_ident(case.task_id)}_{_ident(case.case_id)}"


def _single_case_dataset(case: Case) -> MemoryDataset:
    """Load the full dataset and filter to this one case's Sample."""
    full = load_dataset()
    sid = f"{case.fixture_id}/{case.task_id}/{case.case_id}"
    return MemoryDataset(
        [s for s in full.samples if s.id == sid],
        name=f"koan-bench-{sid}",
    )


def _make_task(case: Case):
    # Close over `case` via argument to avoid the late-binding loop-variable
    # pitfall -- each call to _make_task captures its own `case` object.
    phases_scored = [p for p in case.directed_phases if p != "done"]
    scorers = []
    for ph in phases_scored:
        scorers.extend(factory() for factory in _SCORERS_BY_PHASE.get(ph, []))
    scorers.append(workflow_overall())

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
