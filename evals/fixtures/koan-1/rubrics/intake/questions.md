Grade the questions the orchestrator raised during the intake phase.

A well-performing intake should surface targeted, non-obvious questions:

- The orchestrator raised at least one question that flags a contradiction, inaccuracy, or mistake in the task description by cross-referencing the claim against the actual codebase.
- The orchestrator raised at least one question that probes the expected behavior of an API or system surface the task touches, when the task description does not specify.
- The orchestrator raised at least one question that seeks the broader use case or intent behind the requested change to ground scope decisions.
- The orchestrator raised at least one question that resolves ambiguity about downstream effects the task description is silent on (e.g. side effects on UI, events, persistence).

Generic questions already answerable from the task text (e.g. "what is the deadline?") do not count. Questions resolvable by reading the codebase alone do not count.

PASS if the orchestrator raised at least two targeted questions of the kinds above.
FAIL if the questions were generic, redundant with the task, or if no substantive questions were raised.
