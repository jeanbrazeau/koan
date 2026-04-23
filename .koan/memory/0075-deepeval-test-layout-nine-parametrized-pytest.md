---
title: DeepEval test layout -- single test_workflow_suite() calling evaluate() replaces
  parametrized two-function shape
type: decision
created: '2026-04-22T09:16:47Z'
modified: '2026-04-23T11:05:00Z'
related:
- 0074-deepeval-judge-contract-gevalstrictmodetrue.md
---

This entry documents the test-module layout of `tests/evals/test_koan.py` and `tests/evals/conftest.py`. Three dated decisions shape the current state.

On 2026-04-22, Leon decided the nine-function shape: one pytest function per `(phase, section)` combination, each parametrized via a session-scoped `case` fixture over `discover_cases(FIXTURES_DIR)`. A session-scoped `harvest(case)` fixture ran `run_koan(case)` once per unique case. Rationale: preserving per-(case, section) granularity in pytest output required distinct function definitions.

On 2026-04-23 morning, during an intake investigating harvest dumps for the three `koan-1` tasks, Leon reversed the nine-function decision. The shape became two parametrized functions: `test_rubric` over `(case, phase, section)` rows (~18 today) and `test_run` over `(case)` rows (3 today), both reading from a session-scoped `harvest_cache: dict[tuple, dict]` keyed on `(fixture_id, task_id, case_id)` via a `_get_harvest(case, cache)` helper.

On 2026-04-23 afternoon, after observing live output from `deepeval test run`, Leon reversed the two-function decision too. Triggers: (1) the progress bar read "Evaluating 1 test case(s) in parallel" for every pytest test because `assert_test(tc, metrics)` wraps its case in a singleton `[test_case]` list before handing to the batch executor (`deepeval/evaluate/evaluate.py:137, 150`), so DeepEval never parallelized across rows within a pytest process; (2) the Confident AI dashboard showed one logical test per test-run because every `LLMTestCase` used `input="(koan eval harvest)"` without setting `name=`, collapsing all rows by identical input; (3) `@deepeval.log_hyperparameters` emitted "No hyperparameters logged" warnings because it fires at module-import time against an ephemeral test_run. The replacement is a single pytest function `test_workflow_suite(harvest_cache)` that builds all ~21 test cases (rubric rows named `<fixture>/<task>/<case>/<phase>/<section>`, run rows named `<fixture>/<task>/<case>/workflow`) and calls `evaluate(test_cases, metrics, hyperparameters=HYPERPARAMETERS, async_config=AsyncConfig(max_concurrent=100))` exactly once. DeepEval's engine parallelizes up to 100 concurrent `(case, metric)` evaluations; the dashboard keys results by `LLMTestCase.name` + metric name; hyperparameters attach via the `evaluate()` kwarg rather than the decorator. Metrics (RubricCompliance, CrossPhaseCoherence, Duration, TokenCost, ToolCallCount) all set `self.skipped = True` when their required metadata field is absent, so each row shows only the metrics that apply to it. A runtime `assert len(set(names)) == len(names)` inside the suite guards against the dashboard-dedupe bug silently resurfacing. Koan subprocess invocations remain 3 per run; row-level `pytest -k` granularity is lost in exchange for dashboard-level slicing.
