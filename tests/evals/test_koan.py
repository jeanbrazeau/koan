# tests/evals/test_koan.py
# Single test function that calls deepeval.evaluate() over all discovered cases
# and rubric sections in one shot.
#
# test_workflow_suite() builds:
#   - rubric test cases: one per (case, phase, section) triple that has a rubric
#     file on disk. RubricComplianceMetric applies; others skip.
#   - run test cases: one per case. Duration/TokenCost/ToolCallCount/CrossPhaseCoherence
#     apply; RubricCompliance skips.
#
# All ~21 test cases are passed to evaluate() at once so DeepEval's async engine
# parallelizes up to max_concurrent=100 (case, metric) pairs simultaneously.
# Row-level granularity on the Confident AI dashboard is keyed by LLMTestCase.name
# rather than by pytest test IDs (there is now exactly one pytest test ID).

from __future__ import annotations

import logging

from deepeval import evaluate
from deepeval.evaluate.configs import AsyncConfig, DisplayConfig
from deepeval.test_case import LLMTestCase

from evals.cases import Case
from evals.scorers import (
    CROSS_PHASE_COHERENCE_METRIC,
    DURATION_METRIC,
    RUBRIC_COMPLIANCE_METRIC,
    TOKEN_COST_METRIC,
    TOOL_CALL_COUNT_METRIC,
    load_rubric_criteria,
    _payload_artifacts,
    _payload_overall,
    _payload_questions,
    _payload_summary,
    _payload_workflow,
)
from tests.evals.conftest import CASES, HYPERPARAMETERS, _get_harvest

log = logging.getLogger("koan.evals.test_koan")

SECTIONS = ("summary", "questions", "artifacts", "overall")

_PAYLOAD_FNS = {
    "summary":   _payload_summary,
    "questions": _payload_questions,
    "artifacts": _payload_artifacts,
    "overall":   _payload_overall,
}

# All five metrics as a shared list. Metrics are construction-parameterless
# singletons; per-row inputs travel via LLMTestCase.additional_metadata.
# Metrics skip (self.skipped=True) for rows where their required key is absent.
ALL_METRICS = [
    RUBRIC_COMPLIANCE_METRIC,
    CROSS_PHASE_COHERENCE_METRIC,
    DURATION_METRIC,
    TOKEN_COST_METRIC,
    TOOL_CALL_COUNT_METRIC,
]


def _active_phases(case: Case) -> list[str]:
    return [p for p in case.directed_phases if p != "done"]


def _build_rubric_test_cases(harvest_cache: dict) -> list[LLMTestCase]:
    """One LLMTestCase per (case, phase, section) triple that has a rubric on disk."""
    tcs = []
    for case in CASES:
        h = _get_harvest(case, harvest_cache)
        # Use the task description as input so the judge has meaningful context.
        task_md = (case.task_dir / "task.md").read_text(encoding="utf-8").strip()
        for phase in _active_phases(case):
            for section in SECTIONS:
                criteria = load_rubric_criteria(
                    case.fixture_dir, case.task_dir, phase, section,
                )
                if criteria is None:
                    continue
                payload = _PAYLOAD_FNS[section](h, phase)
                tcs.append(LLMTestCase(
                    name=f"{case.fixture_id}/{case.task_id}/{case.case_id}/{phase}/{section}",
                    input=task_md,
                    actual_output=payload,
                    additional_metadata={
                        "fixture_id":      case.fixture_id,
                        "task_id":         case.task_id,
                        "case_id":         case.case_id,
                        "phase":           phase,
                        "section":         section,
                        "rubric_criteria": criteria,
                    },
                ))
    return tcs


def _build_run_test_cases(harvest_cache: dict) -> list[LLMTestCase]:
    """One LLMTestCase per case for programmatic and cross-phase metrics."""
    tcs = []
    for case in CASES:
        h = _get_harvest(case, harvest_cache)
        task_md = (case.task_dir / "task.md").read_text(encoding="utf-8").strip()
        tok = h.get("token_cost", {}) or {}
        total_tokens = int(tok.get("input_tokens", 0)) + int(tok.get("output_tokens", 0))
        tcs.append(LLMTestCase(
            name=f"{case.fixture_id}/{case.task_id}/{case.case_id}/workflow",
            input=task_md,
            actual_output=_payload_workflow(h),
            # First-class fields for native DeepEval dashboard visualization.
            token_cost=float(total_tokens),
            completion_time=float(h.get("duration_s", 0.0)),
            additional_metadata={
                "fixture_id":      case.fixture_id,
                "task_id":         case.task_id,
                "case_id":         case.case_id,
                "workflow":        case.workflow,
                "directed_phases": case.directed_phases,
                # duration_s and token_cost in metadata for Duration/TokenCost
                # metrics (richer structure than the first-class scalar fields).
                "duration_s":      h.get("duration_s", 0.0),
                "token_cost":      tok,
                "tool_call_count": h.get("tool_call_count", {}),
                # None when rubric_body is empty so CrossPhaseCoherenceMetric skips.
                "rubric_body":     case.rubric_body if case.rubric_body.strip() else None,
            },
        ))
    return tcs


def test_workflow_suite(harvest_cache):
    test_cases = _build_rubric_test_cases(harvest_cache) + _build_run_test_cases(harvest_cache)

    # Guard against the deduplication bug: identical names collapse all rows
    # into one on the Confident AI dashboard. Fail fast at collection time.
    names = [tc.name for tc in test_cases]
    assert len(set(names)) == len(names), "duplicate LLMTestCase.name values"

    log.info(
        "running evaluate() over %d test cases x %d metrics",
        len(test_cases), len(ALL_METRICS),
    )
    result = evaluate(
        test_cases=test_cases,
        metrics=ALL_METRICS,
        hyperparameters=HYPERPARAMETERS,
        # max_concurrent=100: fan out all (case, metric) pairs simultaneously.
        # Default is 20; the suite has ~21 cases x 5 metrics = ~105 pairs.
        async_config=AsyncConfig(run_async=True, throttle_value=0, max_concurrent=100),
        display_config=DisplayConfig(show_indicator=True, print_results=True),
    )

    # Surface all failing rows in a single assertion so pytest reports which rows
    # failed. Individual row names are enough to locate the rubric + payload.
    failed = [r for r in result.test_results if not r.success]
    if failed:
        names = [r.name for r in failed]
        raise AssertionError(
            f"{len(failed)} of {len(test_cases)} test rows failed: {names}"
        )
