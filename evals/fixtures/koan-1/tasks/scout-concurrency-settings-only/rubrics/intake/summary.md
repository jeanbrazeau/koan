Task-specific criteria for the scout-concurrency-settings-only task. These are appended to the fixture-level intake/summary rubric at grade time.

Beyond the generic summary shape, the intake summary for this task should also contain:

- The specific frontend surfaces that currently expose scout concurrency: `frontend/src/components/organisms/NewRunForm.tsx` (the per-run field being removed) and the Settings UI (`SettingsOverlay.tsx` / `SettingsPage.tsx`) where it continues to live.
- The settings store key that persists the default value (`defaultScoutConcurrency` on the Zustand settings slice) and the fact that the new-run flow should read from it after the per-run field is removed.
- The chosen fate of the `scoutConcurrency` parameter in the `api.startRun` signature (dropped, kept-optional, or kept-required) and the reasoning.
- The chosen fate of the `scout_concurrency` field in the `/api/start-run` request body, and how the backend (`koan/config.py`, start-run handler) continues to obtain the value.
- Whether any UI copy around scout concurrency in Settings needs updating (e.g. to clarify that this is now the only place it's configured).

PASS if at least 3 of the above task-specific points are present in addition to the generic categories.
FAIL if the summary discusses the change only abstractly without naming the specific files / store keys / API fields above.
