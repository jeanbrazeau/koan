# evals/scorers.py
# DeepEval metric classes and harvest payload helpers for koan evals.
#
# Public API:
#   JUDGE_MODEL                  -- shared GeminiModel instance
#   load_rubric_criteria         -- parse rubric file into list[str] of bullet criteria
#   RubricComplianceMetric       -- construction-parameterless BaseMetric; reads criteria
#                                   from LLMTestCase.additional_metadata["rubric_criteria"]
#   CrossPhaseCoherenceMetric    -- construction-parameterless BaseMetric; reads rubric_body
#                                   from LLMTestCase.additional_metadata["rubric_body"]
#   DurationMetric               -- programmatic BaseMetric scoring run duration
#   TokenCostMetric              -- programmatic BaseMetric scoring total token usage
#   ToolCallCountMetric          -- programmatic BaseMetric scoring total tool call count
#   RUBRIC_COMPLIANCE_METRIC     -- shared singleton (construction-parameterless)
#   CROSS_PHASE_COHERENCE_METRIC -- shared singleton (construction-parameterless)
#   DURATION_METRIC              -- shared singleton
#   TOKEN_COST_METRIC            -- shared singleton
#   TOOL_CALL_COUNT_METRIC       -- shared singleton
#   _payload_summary             -- extract phase summary text from harvest
#   _payload_questions           -- extract koan_ask_question calls from harvest
#   _payload_artifacts           -- extract artifact content from harvest
#   _payload_overall             -- combined phase payload
#   _payload_workflow            -- combined cross-phase payload
#
# All five metrics are construction-parameterless shared singletons. Per-row
# inputs (rubric_criteria, rubric_body, duration_s, token_cost, tool_call_count)
# travel on LLMTestCase.additional_metadata so the same instances can be passed
# to deepeval.evaluate() once over all test cases.
#
# Each metric sets self.skipped = True when its required metadata key is absent
# (e.g. rubric_criteria absent on run rows). DeepEval's execute path checks
# metric.skipped before recording MetricData, so skipped entries are excluded
# from the dashboard rather than recorded as failures.

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from deepeval.metrics import BaseMetric
from deepeval.models import GeminiModel
from deepeval.test_case import LLMTestCase
from pydantic import BaseModel


# -- Judge model ---------------------------------------------------------------

# Model string is pinned per memory entry 77. Do not change speculatively.
JUDGE_MODEL = GeminiModel(model="gemini-3-pro-preview")


# -- Rubric loading ------------------------------------------------------------

def load_rubric_criteria(
    fixture_dir: Path,
    task_dir: Path,
    phase: str,
    section: str,
) -> list[str] | None:
    """Parse rubric file(s) into a list of individual criterion strings.

    Loads the fixture-level rubric file and, if present, concatenates the
    task-level addendum. Iterates the combined text line by line, treating
    any line starting with '- ' or '* ' (after stripping leading whitespace)
    as a single criterion. Prose paragraphs and blank lines are ignored.

    Returns None when no rubric file exists (test is skipped, not failed).
    Raises ValueError when a rubric file exists but parses to zero criteria
    -- that is a rubric authoring error, not a pass-by-default case.

    Rubric directories use underscores regardless of how koan names the phase
    (e.g. phase "plan-spec" -> dir "plan_spec").
    """
    phase_dir = phase.replace("-", "_")
    fixture_rubric = fixture_dir / "rubrics" / phase_dir / f"{section}.md"
    task_rubric = task_dir / "rubrics" / phase_dir / f"{section}.md"

    parts = []
    if fixture_rubric.exists():
        parts.append(fixture_rubric.read_text(encoding="utf-8"))
    if task_rubric.exists():
        parts.append(task_rubric.read_text(encoding="utf-8"))

    if not parts:
        return None

    combined = "\n\n".join(parts)
    criteria = []
    for line in combined.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("- "):
            criteria.append(stripped[2:].strip())
        elif stripped.startswith("* "):
            criteria.append(stripped[2:].strip())

    if not criteria:
        raise ValueError(
            f"rubric {fixture_rubric} parsed to zero criteria -- "
            "ensure each criterion is on its own bullet line (- or *)"
        )
    return criteria


# -- Structured judge output schemas ------------------------------------------

class CriterionVerdict(BaseModel):
    passed: bool
    reason: str = ""


class OverallVerdict(BaseModel):
    passed: bool
    reason: str = ""


# -- RubricComplianceMetric ----------------------------------------------------

_RUBRIC_PROMPT = """\
Evaluate the following output against a single criterion.

Criterion:
{criterion}

Output:
{actual_output}

Return JSON with two fields:
  passed: true if the output satisfies the criterion, false otherwise.
  reason: one-sentence justification.
"""


class RubricComplianceMetric(BaseMetric):
    """Construction-parameterless BaseMetric; issues one judge call per criterion bullet.

    Criteria are read from test_case.additional_metadata["rubric_criteria"] at
    measure time. This allows a single shared instance to handle all rubric rows
    when passed to deepeval.evaluate() -- row identity is carried by the test case,
    not baked into the metric object.

    Sets self.skipped = True for rows that lack rubric_criteria (e.g. run rows).
    """

    async_mode = True
    verbose_mode = True
    evaluation_params: list = []
    _name = "RubricCompliance"

    def __init__(self, threshold: float = 1.0, model=None) -> None:
        self.threshold = threshold
        self.model = model or JUDGE_MODEL
        self.score = 0.0
        self.success = False
        self.reason = ""
        self.error = None
        self.score_breakdown = {}
        self.verbose_logs = ""
        self.skipped = False

    @property
    def __name__(self) -> str:
        return self._name

    async def _judge_one(self, criterion: str, actual_output: str) -> CriterionVerdict:
        prompt = _RUBRIC_PROMPT.format(
            criterion=criterion,
            actual_output=actual_output,
        )
        result = await self.model.a_generate_with_schema(prompt, CriterionVerdict)
        # GeminiModel.a_generate returns (parsed_model, cost) tuple
        if isinstance(result, tuple):
            result = result[0]
        return result

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        # Reset skipped so a prior skip on another row does not bleed through.
        self.skipped = False
        criteria = (test_case.additional_metadata or {}).get("rubric_criteria") or []
        if not criteria:
            self.skipped = True
            self.score = 0.0
            self.success = False
            self.reason = "no rubric_criteria in additional_metadata"
            return 0.0
        actual = test_case.actual_output or ""
        results = await asyncio.gather(
            *(self._judge_one(c, actual) for c in criteria)
        )
        verdicts = [1.0 if v.passed else 0.0 for v in results]
        self.score = sum(verdicts) / len(verdicts)
        self.success = self.score >= self.threshold
        self.score_breakdown = {
            c: {"passed": bool(v.passed), "reason": v.reason}
            for c, v in zip(criteria, results)
        }
        failed = [c for c, v in zip(criteria, results) if not v.passed]
        self.reason = (
            f"Pass-rate {self.score:.2f} "
            f"({int(self.score * len(verdicts))}/{len(verdicts)} criteria passed). "
            + (f"Failed: {failed}" if failed else "All criteria passed.")
        )
        return self.score

    def measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        return asyncio.run(self.a_measure(test_case, *args, **kwargs))

    def is_successful(self) -> bool:
        return self.success


# -- CrossPhaseCoherence -------------------------------------------------------

_CROSS_PHASE_PROMPT = """\
Grade the following workflow output against the cross-phase rubric.

Rubric:
{rubric_body}

Output:
{actual_output}

Return JSON with two fields:
  passed: true if the output satisfies the rubric, false otherwise.
  reason: one-sentence justification.
"""


class CrossPhaseCoherenceMetric(BaseMetric):
    """Construction-parameterless BaseMetric for cross-phase coherence.

    Reads rubric_body from test_case.additional_metadata["rubric_body"] at
    measure time. Allows a single shared instance across all run rows; rows
    that lack rubric_body (e.g. rubric section rows) are skipped.

    Uses a_generate_with_schema with OverallVerdict instead of GEval so the
    metric is stateless with respect to row identity -- GEval would need one
    instance per case because criteria are baked into the constructor.
    """

    async_mode = True
    verbose_mode = True
    evaluation_params: list = []
    _name = "CrossPhaseCoherence"

    def __init__(self, model=None) -> None:
        # Binary pass/fail: passed=True -> score 1.0, failed -> score 0.0.
        self.threshold = 1.0
        self.model = model or JUDGE_MODEL
        self.score = 0.0
        self.success = False
        self.reason = ""
        self.error = None
        self.score_breakdown = {}
        self.verbose_logs = ""
        self.skipped = False

    @property
    def __name__(self) -> str:
        return self._name

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        # Reset skipped so a prior skip on another row does not bleed through.
        self.skipped = False
        body = (test_case.additional_metadata or {}).get("rubric_body") or ""
        if not body.strip():
            self.skipped = True
            self.score = 0.0
            self.success = False
            self.reason = "no rubric_body in additional_metadata"
            return 0.0
        prompt = _CROSS_PHASE_PROMPT.format(
            rubric_body=body,
            actual_output=test_case.actual_output or "",
        )
        verdict = await self.model.a_generate_with_schema(prompt, OverallVerdict)
        if isinstance(verdict, tuple):
            verdict = verdict[0]
        self.score = 1.0 if verdict.passed else 0.0
        self.success = verdict.passed
        self.reason = verdict.reason or ("Passed." if verdict.passed else "Failed.")
        return self.score

    def measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        return asyncio.run(self.a_measure(test_case, *args, **kwargs))

    def is_successful(self) -> bool:
        return self.success


# -- Programmatic BaseMetric subclasses ----------------------------------------

class DurationMetric(BaseMetric):
    """Scores run duration against a wall-clock threshold.

    Reads duration_s from test_case.additional_metadata -- no LLM call needed.
    threshold_s defaults to 1800 (30 minutes), enough headroom for plan+intake.
    Skips (does not record MetricData) for rubric rows that lack duration_s.
    """

    async_mode = False

    def __init__(self, threshold_s: float = 1800.0) -> None:
        self.threshold = threshold_s
        self.score = 0.0
        self.success = False
        self.reason = ""
        self.error = None
        self.score_breakdown = {}
        self.skipped = False

    @property
    def __name__(self) -> str:
        return "Duration"

    def measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        # Reset so a prior skip on another row does not bleed through.
        self.skipped = False
        meta = test_case.additional_metadata or {}
        if "duration_s" not in meta:
            self.skipped = True
            self.score = 0.0
            self.success = False
            self.reason = "no duration_s in additional_metadata"
            return 0.0
        s = float(meta["duration_s"])
        self.score = s
        self.success = s <= self.threshold
        self.reason = f"duration {s:.1f}s vs threshold {self.threshold:.1f}s"
        return self.score

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        return self.measure(test_case, *args, **kwargs)

    def is_successful(self) -> bool:
        return self.success


class TokenCostMetric(BaseMetric):
    """Scores total orchestrator token usage against a threshold.

    Reads token_cost from test_case.additional_metadata. threshold_tokens
    defaults to 500k -- a generous budget for a two-phase plan run.
    Skips for rubric rows that lack token_cost.
    """

    async_mode = False

    def __init__(self, threshold_tokens: int = 500_000) -> None:
        self.threshold = float(threshold_tokens)
        self.score = 0.0
        self.success = False
        self.reason = ""
        self.error = None
        self.score_breakdown = {}
        self.skipped = False

    @property
    def __name__(self) -> str:
        return "TokenCost"

    def measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        # Reset so a prior skip on another row does not bleed through.
        self.skipped = False
        meta = test_case.additional_metadata or {}
        if "token_cost" not in meta:
            self.skipped = True
            self.score = 0.0
            self.success = False
            self.reason = "no token_cost in additional_metadata"
            return 0.0
        tc = meta["token_cost"] or {}
        total = int(tc.get("input_tokens", 0)) + int(tc.get("output_tokens", 0))
        self.score = float(total)
        self.success = total <= self.threshold
        self.reason = (
            f"tokens {total} (in={tc.get('input_tokens', 0)} "
            f"out={tc.get('output_tokens', 0)}) vs threshold {int(self.threshold)}"
        )
        return self.score

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        return self.measure(test_case, *args, **kwargs)

    def is_successful(self) -> bool:
        return self.success


class ToolCallCountMetric(BaseMetric):
    """Scores total tool call count across all phases against a threshold.

    Reads tool_call_count from test_case.additional_metadata. threshold_calls
    defaults to 500 -- a rough ceiling for non-pathological runs.
    Skips for rubric rows that lack tool_call_count.
    """

    async_mode = False

    def __init__(self, threshold_calls: int = 500) -> None:
        self.threshold = float(threshold_calls)
        self.score = 0.0
        self.success = False
        self.reason = ""
        self.error = None
        self.score_breakdown = {}
        self.skipped = False

    @property
    def __name__(self) -> str:
        return "ToolCallCount"

    def measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        # Reset so a prior skip on another row does not bleed through.
        self.skipped = False
        meta = test_case.additional_metadata or {}
        if "tool_call_count" not in meta:
            self.skipped = True
            self.score = 0.0
            self.success = False
            self.reason = "no tool_call_count in additional_metadata"
            return 0.0
        counts = meta["tool_call_count"] or {}
        total = sum(int(v) for v in counts.values())
        self.score = float(total)
        self.success = total <= self.threshold
        self.score_breakdown = dict(counts)
        self.reason = f"tool calls total={total} vs threshold {int(self.threshold)}"
        return self.score

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        return self.measure(test_case, *args, **kwargs)

    def is_successful(self) -> bool:
        return self.success


# Module-level shared singletons -- one instance per metric type, reused across
# all test case rows. Dimensional naming ("RubricCompliance", "Duration", etc.)
# groups all rows under the same metric axis on the DeepEval dashboard.
# Construction-parameterless design lets deepeval.evaluate() receive the same
# list for every test case; row-specific inputs travel via additional_metadata.
RUBRIC_COMPLIANCE_METRIC = RubricComplianceMetric()
CROSS_PHASE_COHERENCE_METRIC = CrossPhaseCoherenceMetric()
DURATION_METRIC = DurationMetric()
TOKEN_COST_METRIC = TokenCostMetric()
TOOL_CALL_COUNT_METRIC = ToolCallCountMetric()


# -- Payload selection ---------------------------------------------------------

def _payload_summary(harvest: dict, phase: str) -> str:
    summary = harvest.get("phase_summaries", {}).get(phase)
    if not summary:
        return "(no summary captured for this phase)"
    return summary


def _payload_questions(harvest: dict, phase: str) -> str:
    calls = harvest.get("tool_calls_by_phase", {}).get(phase, [])
    asks = [c for c in calls if c["tool"] == "koan_ask_question"]
    if not asks:
        return "(no koan_ask_question calls during this phase)"
    return json.dumps([c["args"] for c in asks], indent=2)


def _payload_artifacts(harvest: dict, phase: str) -> str:
    art = harvest.get("artifacts_by_phase", {}).get(phase, {
        "created": {}, "modified": {}, "all_present": {},
    })
    blocks = []
    for kind in ("created", "modified", "all_present"):
        items = art.get(kind, {})
        if not items:
            blocks.append(f"### {kind}\n(none)")
        else:
            blocks.append(
                f"### {kind}\n"
                + "\n".join(
                    f"#### {p}\n```\n{c}\n```"
                    for p, c in items.items()
                )
            )
    return "\n\n".join(blocks)


def _payload_overall(harvest: dict, phase: str) -> str:
    return (
        f"## summary\n{_payload_summary(harvest, phase)}\n\n"
        f"## questions\n{_payload_questions(harvest, phase)}\n\n"
        f"## artifacts\n{_payload_artifacts(harvest, phase)}\n\n"
        f"## all_tool_calls\n"
        + json.dumps(
            harvest.get("tool_calls_by_phase", {}).get(phase, []),
            indent=2,
        )
    )


def _payload_workflow(harvest: dict) -> str:
    summaries = harvest.get("phase_summaries", {})
    tools = harvest.get("tool_calls_by_phase", {})
    order = harvest.get("phase_order") or sorted(summaries.keys())
    tail = [p for p in summaries.keys() if p not in order]
    blocks = []
    for phase in list(order) + tail:
        blocks.append(
            f"# phase: {phase}\n\n"
            f"## summary\n{summaries.get(phase, '')}\n\n"
            f"## tool_calls\n{json.dumps(tools.get(phase, []), indent=2)}\n\n"
            f"## artifacts\n{_payload_artifacts(harvest, phase)}"
        )
    return "\n\n---\n\n".join(blocks)
