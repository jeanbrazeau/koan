Grade whether the plan-spec phase produced the expected plan artifact.

The plan-spec phase must produce a plan.md file in the run directory.

- plan.md is present in the all_present artifact set for the plan-spec phase.
- plan.md cites at least 3 specific file paths from the actual codebase (not invented or generic paths).

PASS when plan.md is present in the all_present set for this phase.
FAIL if plan.md is absent from all_present.
