Grade any questions the orchestrator raised during the plan-spec phase.

In plan-spec the orchestrator should not ask generic or exploratory questions -- those belong in intake. Questions during plan-spec are acceptable only when a genuine ambiguity blocks planning (e.g. a missing constraint that cannot be inferred from the codebase).

- The orchestrator asked no questions during plan-spec, or asked only targeted clarifications that were strictly necessary to resolve a concrete implementation ambiguity not resolvable by reading the codebase.

PASS if the orchestrator asked no questions, or asked only targeted clarifications that were necessary to resolve a concrete implementation ambiguity.
FAIL if the orchestrator asked generic questions, repeated questions already answered in intake, or asked questions that could have been resolved by reading the codebase.
