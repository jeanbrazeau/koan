# evals/scorers.py
# Rubric-driven scorers for koan eval tasks.
#
# Each scorer loads a fixture-level rubric (required) plus an optional
# task-level addendum for a (phase, section) pair, selects the matching
# payload slice from state.metadata["harvest"], and asks a judge model for
# PASS or FAIL. Missing rubric -> scorer returns None -> inspect_ai skips it.
#
# Section enum per phase: summary | questions | artifacts | overall.
# Workflow-level cross-cutter: rubric body from the case file (overall_rubric in metadata).
#
# Scorers are independent `@scorer` functions (not a composite dict-valued
# score) so each shows as its own span in the transcript, its own row in
# the scoring table, and can be re-run individually via `inspect eval
# --scorer <name>`. Inspect dispatches them sequentially within a sample;
# parallelism across samples is controlled via `max_samples`.

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from inspect_ai.model import get_model
from inspect_ai.scorer import (
    CORRECT,
    INCORRECT,
    Score,
    Scorer,
    accuracy,
    mean,
    scorer,
    stderr,
    value_to_float,
)
from inspect_ai.solver import TaskState


JUDGE_MODEL = "google/gemini-3.1-pro-preview"


# -- Rubric loading ------------------------------------------------------------

def _load_rubric(state: TaskState, phase: str, section: str) -> str | None:
    fixture_dir = Path(state.metadata["fixture_dir"])
    task_dir = Path(state.metadata["task_dir"])
    # Rubric directories use Python-style underscores regardless of how koan
    # names the phase internally (e.g. phase "plan-spec" -> dir "plan_spec").
    phase_dir = phase.replace("-", "_")
    fixture_rubric = fixture_dir / "rubrics" / phase_dir / f"{section}.md"
    task_rubric = task_dir / "rubrics" / phase_dir / f"{section}.md"
    parts = []
    if fixture_rubric.exists():
        parts.append(fixture_rubric.read_text(encoding="utf-8"))
    if task_rubric.exists():
        parts.append(
            "\n\n## Task-specific additions\n\n"
            + task_rubric.read_text(encoding="utf-8")
        )
    return "\n\n".join(parts) if parts else None


def _load_case_rubric(state: TaskState) -> str | None:
    # The overall rubric is now embedded in the case file body and injected
    # into Sample metadata by load_dataset. Reading from metadata avoids a
    # second file read at score time and keeps the scorer independent of the
    # fixtures directory layout.
    rubric = state.metadata.get("overall_rubric")
    return rubric if rubric else None


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
    # Use the chronological phase_order captured by harvest_run so the
    # workflow-level payload reads in the order phases actually ran
    # (intake -> plan-spec -> ...) rather than alphabetically.
    order = harvest.get("phase_order") or sorted(summaries.keys())
    # Append any phases that appear in data but not in phase_order (shouldn't
    # happen, but keeps the payload lossless if harvest is incomplete).
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


# -- Judge invocation ----------------------------------------------------------

_JUDGE_PROMPT = """You are grading an AI orchestrator against a rubric.

## Rubric

{rubric}

## Data

{payload}

Respond with a brief rationale, then on the last line exactly one of:
PASS
FAIL
"""


async def _grade(rubric: str, payload: str) -> Score:
    model = get_model(JUDGE_MODEL)
    out = await model.generate(_JUDGE_PROMPT.format(rubric=rubric, payload=payload))
    text = out.completion.strip()
    last_line = text.splitlines()[-1].strip().upper() if text else "FAIL"
    passing = last_line == "PASS"
    # CORRECT / INCORRECT are inspect_ai's canonical binary values ("C"/"I").
    # Default value_to_float recognises them, so default accuracy()/stderr()
    # work without any custom converter, and `inspect view` renders them with
    # built-in styling rather than bare numerics.
    return Score(
        value=CORRECT if passing else INCORRECT,
        answer="PASS" if passing else "FAIL",
        explanation=text,
    )


# -- Scorer factories ----------------------------------------------------------

def _scorer_name(phase: str, section: str) -> str:
    # Normalize phase names like "plan-spec" to underscores so log columns
    # render cleanly and match the Python factory variable names.
    return f"{phase.replace('-', '_')}_{section}"


def _rubric_scorer(phase: str, section: str, payload_fn: Callable):
    # Returns a scorer factory (call with () to get a Scorer). The inner
    # _build function is decorated with @scorer so inspect_ai picks it up;
    # name= is set explicitly because all eight factories share the same
    # inner function name (_build) and need distinct registry keys.
    @scorer(metrics=[accuracy(), stderr()], name=_scorer_name(phase, section))
    def _build() -> Scorer:
        async def score(state: TaskState, target) -> Score | None:
            # Gate: skip phases that did not run under this case's directed
            # sequence. Empty scored_phases (no directed_phases in metadata)
            # falls through so Samples without the field are still scored.
            directed = state.metadata.get("directed_phases") or []
            scored_phases = [p for p in directed if p != "done"]
            if scored_phases and phase not in scored_phases:
                return None
            rubric = _load_rubric(state, phase, section)
            if rubric is None:
                # No rubric for this (phase, section) -> skip gracefully.
                # Inspect treats this as "unscored" rather than FAIL.
                return None
            harvest = state.metadata.get("harvest", {})
            payload = payload_fn(harvest, phase)
            return await _grade(rubric, payload)
        return score
    return _build


intake_summary    = _rubric_scorer("intake",    "summary",   _payload_summary)
intake_questions  = _rubric_scorer("intake",    "questions", _payload_questions)
intake_artifacts  = _rubric_scorer("intake",    "artifacts", _payload_artifacts)
intake_overall    = _rubric_scorer("intake",    "overall",   _payload_overall)

plan_spec_summary   = _rubric_scorer("plan-spec", "summary",   _payload_summary)
plan_spec_questions = _rubric_scorer("plan-spec", "questions", _payload_questions)
plan_spec_artifacts = _rubric_scorer("plan-spec", "artifacts", _payload_artifacts)
plan_spec_overall   = _rubric_scorer("plan-spec", "overall",   _payload_overall)


@scorer(metrics=[accuracy(), stderr()], name="workflow_overall")
def workflow_overall() -> Scorer:
    async def score(state: TaskState, target) -> Score | None:
        rubric = _load_case_rubric(state)
        if rubric is None:
            return None
        harvest = state.metadata.get("harvest", {})
        return await _grade(rubric, _payload_workflow(harvest))
    return score


# -- Aggregate scorer ---------------------------------------------------------
# `overall_pass_rate` reads state.scores populated by the prior scorers in the
# list (inspect_ai's task runner writes state.scores[name] after each scorer
# returns, so any scorer that runs LATER can observe earlier results). It
# returns the fraction of rubric scorers that PASSed for this sample.
#
# Placed LAST in the scorer list so it sees the full picture. The per-sample
# Score value is a float in [0, 1]; the metric `mean()` aggregates across
# samples. This gives a real headline number (e.g. 0.67 = 6/9 PASS) instead
# of the first-scorer-only view that made 6/9 runs show up as "Score 0.0".

_to_float = value_to_float()


@scorer(metrics=[mean(), stderr()], name="overall_pass_rate")
def overall_pass_rate() -> Scorer:
    async def score(state: TaskState, target) -> Score | None:
        # Exclude this scorer's own future entry; state.scores already has
        # every prior scorer keyed by name. Ignore any score already named
        # overall_pass_rate to stay safe under re-scoring.
        prior = {k: v for k, v in state.scores.items() if k != "overall_pass_rate"}
        if not prior:
            return None
        passed = sum(1 for v in prior.values() if _to_float(v.value) >= 1.0)
        total = len(prior)
        ratio = passed / total
        breakdown = ", ".join(
            f"{k}={v.answer or v.value}" for k, v in sorted(prior.items())
        )
        return Score(
            value=ratio,
            answer=f"{passed}/{total} passed",
            explanation=breakdown,
        )
    return score
