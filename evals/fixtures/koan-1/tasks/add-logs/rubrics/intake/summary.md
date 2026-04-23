## Task-specific additions (add-logs)

Beyond the generic summary shape, the intake summary for "add more debug logs" should contain at least 4 of the following task-specific findings:

- Identified the logging imbalance: the memory subsystem (`koan/memory/`) accounts for roughly half of all logging calls, while the phase modules (`koan/phases/*.py`) have zero logging, and the rest of the system (driver, subagent, web server) has sparse coverage.
- Identified the existing logging infrastructure: centralized setup in `koan/logger.py` with `get_logger()`, dual handlers (console + file to `{run_dir}/koan.log`), plain-text format with timestamp/name/level/message.
- Documented which subsystems need logging and why -- at minimum the phase modules, but ideally also the driver's phase-transition path, subagent lifecycle, and permission checks.
- Made a decision about frontend scope (in or out) based on user clarification, and stated that decision explicitly.
- Noted that the existing logging is unstructured (format strings, no JSON or structured fields) and stated whether that pattern should be continued or changed.
- Identified that the goal is after-the-fact debuggability -- being able to reconstruct what happened during a run from log output alone, which is critical for LLM-driven workflows where failures are non-deterministic.

PASS if >= 4 task-specific findings are present with substantive detail.
FAIL if the summary discusses logging in the abstract without grounding in the actual codebase structure, or if fewer than 4 points are covered.
