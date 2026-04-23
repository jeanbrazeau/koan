Task-specific criteria for the scout-concurrency-settings-only task. These are appended to the fixture-level plan_spec/summary rubric at grade time.

Beyond the generic summary shape, the plan-spec summary for this task should also contain:

- The specific files that will change, named explicitly: at minimum `frontend/src/components/organisms/NewRunForm.tsx` (field + state removed) and `frontend/src/api/client.ts` (the `scoutConcurrency` parameter handling in `startRun`), plus any upstream caller in `App.tsx` that stops piping the value through.
- The mechanism by which the new-run flow will obtain the scout concurrency value after the input is gone (e.g. reading `defaultScoutConcurrency` from the Zustand settings store inside `startRun`, or reading it in the component and passing it as before).
- The chosen fate of the `/api/start-run` request body -- either it still carries `scout_concurrency` (derived server-side or sent from the settings store) or it stops carrying it (and the backend derives it from config).
- Any tests or stories that need to be updated (e.g. a stub scout-concurrency field in NewRunForm stories).

PASS if the summary names at least 2 of the file paths above AND states the chosen value-sourcing mechanism AND states the API request-shape decision.
FAIL if the summary is generic ("remove the field, use settings") without naming the specific files and decisions.
