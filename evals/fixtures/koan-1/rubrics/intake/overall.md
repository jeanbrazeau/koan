Grade the overall behavior of the orchestrator during the intake phase.

Check the following cross-cutting behaviors:

- Scout discipline: the orchestrator launched scouts only when the task genuinely required broad codebase investigation; for a trivial self-contained change, no scouts were spawned.
- Memory usage: the orchestrator called at least one of `koan_reflect` or `koan_search` during intake.
- Codebase grounding: the orchestrator opened the files the task description references and verified claims against what it read, rather than taking the task description at face value.

PASS if all three behaviors are observed.
FAIL if any of the three behaviors is absent.
