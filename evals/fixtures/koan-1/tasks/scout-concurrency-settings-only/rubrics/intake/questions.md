Task-specific criteria for the scout-concurrency-settings-only task. These are appended to the fixture-level intake/questions rubric at grade time.

Beyond the generic question quality rubric, the intake questions for this task should cover at least 3 of the following task-specific ambiguities:

- What the new-run flow should use as the scout-concurrency value once the input is gone (settings store default vs. a hardcoded constant vs. reading from the backend config).
- Whether the `scoutConcurrency` parameter in the `api.startRun` signature should be dropped, kept optional, or kept required for backward compatibility with callers.
- Whether the `/api/start-run` request body should still include `scout_concurrency` at all, or whether the backend should derive it entirely from server-side config.
- Whether the existing Settings UI needs copy or layout updates now that it's the sole home for this control.
- Whether per-run overrides should remain possible via some other mechanism (e.g. a dev-only URL param, a CLI flag) or whether they are being fully eliminated.

PASS if at least 3 of these task-specific ambiguities are raised as questions (in addition to satisfying the generic question-quality rubric).
FAIL if the intake proceeds without raising enough of the above to nail down the scope.

Respond with PASS or FAIL on the last line.
