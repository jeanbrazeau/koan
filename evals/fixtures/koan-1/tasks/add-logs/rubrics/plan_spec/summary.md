## Task-specific additions (add-logs)

Beyond the generic plan-spec summary shape, the plan for "add logs" should
explicitly cover at least 4 of the following:

- Which subsystems will receive new logging and in what priority order. At
  minimum the phase modules (`koan/phases/*.py`) should be listed, since they
  currently have zero logging despite being the core orchestration layer.
- Specific file paths for each subsystem targeted -- not "add logging to
  phases" but naming actual files like `koan/phases/intake.py`,
  `koan/phases/plan_spec.py`, `koan/driver.py`, etc.
- What events to log within each subsystem. For phases: step transitions,
  guidance delivery, phase boundaries. For the driver: orchestrator spawn,
  phase commits, run completion. For subagents: spawn, registration, exit.
- Whether to extend the existing `get_logger()` pattern from `koan/logger.py`
  to all new logging sites, maintaining the `koan.<scope>` namespace
  convention.
- Log level assignment strategy: what constitutes debug (verbose tracing) vs
  info (operational milestones) vs warning (recoverable issues) for this
  codebase.
- Frontend logging plan if frontend was determined to be in scope during
  intake -- what to log in the TypeScript/React layer and through what
  mechanism.

PASS if >= 4 of these points are addressed with specific enough detail that
an engineer could begin implementation without further research.
FAIL if the plan stays at the level of "add logging to various modules"
without naming files, events, or levels.

Respond with PASS or FAIL on the last line.
