## Task-specific additions (add-logs)

The "add logs" task is maximally ambiguous -- it names no specific module, log level, or purpose. A well-performing orchestrator should demonstrate it treated this ambiguity as a signal to investigate broadly rather than narrowing prematurely.

Check the following:

- Performed a broad survey of logging coverage across the codebase rather than fixating on a single module -- at minimum, the orchestrator examined files in `koan/phases/`, `koan/driver.py`, `koan/subagent.py`, and `koan/memory/` to understand the current distribution.
- Recognized the frontend/backend ambiguity and surfaced it as a question rather than silently assuming one scope.
- Did not prematurely narrow scope to a single subsystem before understanding the full picture.

PASS if all three behaviors are observed.
FAIL if the orchestrator narrowed to a single module without surveying the landscape, or silently assumed frontend was out of scope.
