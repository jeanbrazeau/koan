---
title: DeepEval judge contract -- custom BaseMetric subclasses (RubricCompliance,
  CrossPhaseCoherence) replace DAGMetric and GEval for shared-singleton semantics
type: decision
created: '2026-04-22T09:16:34Z'
modified: '2026-04-23T11:04:38Z'
related:
- 0075-deepeval-test-layout-nine-parametrized-pytest.md
---

This entry documents the judge-LLM contract for the DeepEval-based koan eval harness in `evals/scorers.py`. Three dated revisions shape the current state.

On 2026-04-22, Leon chose `GEval(name=..., criteria=<rubric-body>, strict_mode=True, model=JUDGE_MODEL)` for per-phase rubrics, with `JUDGE_MODEL = GeminiModel(model="gemini-3-pro")` as a shared module constant. Rationale: binary PASS/FAIL matched the rubric files' existing "PASS or FAIL on the last line" tail contract, and passing the full rubric body via `criteria=` preserved the migration's "don't change rubric content" constraint. `DAGMetric` for per-criterion decomposition was deferred. `LiteLLMModel('google/gemini-3.1-pro-preview')` was rejected (plan-review caught the nonexistent `3.1` family).

On 2026-04-23 morning, during an intake-phase redesign, Leon adopted DAGMetric for a new `RubricCompliance` dimensional metric -- each rubric bullet becoming a `BinaryJudgementNode` aggregated via VerdictNodes.

On 2026-04-23 afternoon, plan-review reversed the DAGMetric choice. Root observation: `DeepAcyclicGraph.__init__` in deepeval 3.9.7 raises `ValueError("You cannot provide more than one root node when using 'BinaryJudgementNode' or 'NonBinaryJudgementNode' in root_nodes.")` whenever more than one binary judgement appears at the root level, which every multi-bullet rubric would trigger. The replacement is a custom `RubricComplianceMetric(BaseMetric)` that takes no criteria at construction, reads `rubric_criteria` from `LLMTestCase.additional_metadata` inside `a_measure()`, and issues one `JUDGE_MODEL.a_generate_with_schema(prompt, CriterionVerdict)` call per criterion via `asyncio.gather`. Verdicts are averaged into a pass-rate; `threshold=1.0` preserves all-or-nothing binary semantics while keeping the numeric score visible in `score_breakdown` for partial-failure diagnosis. `GEval` for CrossPhaseCoherence was retired in the same afternoon revision and replaced with `CrossPhaseCoherenceMetric(BaseMetric)` reading `rubric_body` from `additional_metadata` -- the conversion was needed because `evaluate()` applies the same metrics list to every test case, forcing metrics to be construction-parameterless singletons rather than per-row factory instances. `strict_mode=True` binary semantics preserved across both metrics. `JUDGE_MODEL` upgraded to `GeminiModel(model="gemini-3-pro-preview")` in the same revision.
