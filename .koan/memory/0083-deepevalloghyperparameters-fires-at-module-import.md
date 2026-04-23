---
title: '@deepeval.log_hyperparameters fires at module-import against a stale test_run;
  evaluate(hyperparameters=) is the reliable wiring'
type: lesson
created: '2026-04-23T11:06:01Z'
modified: '2026-04-23T11:06:01Z'
related:
- 0079-deepeval-hyperparameter-triple-for-koan-suite.md
---

This entry records the wiring failure of `@deepeval.log_hyperparameters` under the pytest + evaluate() invocation path, diagnosed on 2026-04-23 afternoon in the koan DeepEval suite. Symptom: Leon observed the warning "⚠ WARNING: No hyperparameters logged. Log hyperparameters to attribute prompts and models to your test runs." in the `deepeval test run` output, despite `tests/evals/conftest.py` having a `@deepeval.log_hyperparameters`-decorated `hyperparameters()` function returning the three-value triple `{orchestrator_model, judge_model, koan_git_sha}`.

Root cause: reading `deepeval/test_run/hyperparameters.py:61-79` showed that `log_hyperparameters(func)` executes `func()` at decoration time -- i.e., at module import. It then fetches `global_test_run_manager.get_test_run()` and writes `test_run.hyperparameters = processed_hyperparameters(func())` to that run object, saving to `TEMP_FILE_PATH`. When the conftest module loads before `evaluate()` creates its active test run, the assignment lands on an ephemeral run object that is not the one `evaluate()` subsequently operates on. The final-session save then reports "No hyperparameters logged" (`deepeval/test_run/test_run.py:1030`) because the active run's `hyperparameters` field is empty.

Reliable wiring is the `hyperparameters=` kwarg on `evaluate()`: `evaluate(test_cases, metrics, hyperparameters: Optional[Dict[str, Union[str, int, float, Prompt]]], async_config, ...)`. Values pass through at call time and attach to the currently-active test run, regardless of whether pytest was invoked as plain `pytest` or as `deepeval test run`. Applied on 2026-04-23: the koan suite dropped `@deepeval.log_hyperparameters` from `tests/evals/conftest.py` in favor of a module-level `HYPERPARAMETERS: dict[str, str]` dict that `test_workflow_suite()` passes to `evaluate(hyperparameters=HYPERPARAMETERS)`. The warning disappeared; the dashboard's Compare Test Results page now slices runs by the three hyperparameter values. Lesson for future DeepEval work in this repo: when a `@deepeval.log_hyperparameters` path shows the "No hyperparameters logged" warning, the decorator ran against a stale test_run object; switch to passing `hyperparameters=` directly to `evaluate()` or `assert_test` rather than trying to fix the decoration context.
