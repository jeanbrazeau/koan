Task-specific criteria for the scout-concurrency-settings-only task. These are appended to the fixture-level plan_spec/overall rubric at grade time.

Beyond the generic plan-spec quality rubric, the plan for this task should:

- Specify the removal of the scout-concurrency control from `frontend/src/components/organisms/NewRunForm.tsx` (the `nrf-field` block, the `scoutConcurrency` local state, and its use in the `handleStart` / `api.startRun` call site).
- Preserve the existing Settings UI (`SettingsOverlay.tsx` / `SettingsPage.tsx`) -- the plan should NOT also remove the control from Settings.
- Specify how `api.startRun` obtains the value afterwards (reads from the settings store, reads from the backend, or the parameter is dropped entirely) -- one clear decision, not a list of maybes.
- Leave the backend `koan/config.py` default (`scout_concurrency: int = 8`) intact as the fallback source of truth when no explicit override is provided.

PASS if the plan names the NewRunForm changes specifically, keeps the Settings UI unchanged, states one clear value-sourcing decision, and does not propose deleting the backend config default.
FAIL if the plan also proposes removing the control from Settings, omits the NewRunForm file-level change list, or leaves the value-sourcing decision unresolved.
