## Task-specific additions (add-logs)

The task "add more debug logs to the application" is deliberately ambiguous.
A well-performing orchestrator should surface at least 4 of the following
questions or equivalent probes:

- Asked whether frontend logging is in scope or only backend. The project has
  both a Python backend and a TypeScript/React frontend -- the task says
  "application" without specifying which side. This cannot be inferred from
  the codebase alone and must be clarified with the user.
- Identified the logging gap between the memory subsystem (heavily logged) and
  the rest of the system (sparsely logged), and asked whether the goal is to
  bring the rest up to the memory subsystem's level of coverage.
- Asked what the logs are meant to help with: after-the-fact debugging of
  failed runs, live observability, or both. This shapes placement and
  verbosity.
- Asked about the current inability to trace what went wrong after a run
  fails -- i.e., whether the goal is evidence-driven debugging (reconstructing
  LLM decisions, phase transitions, tool call outcomes from log output).
- Asked whether there is a preferred logging pattern or framework to follow,
  or whether the existing `get_logger()` / `koan.logger` pattern should be
  extended to uncovered modules.
- Asked about log level strategy: what events warrant info vs debug vs
  warning, or whether everything should default to debug given the task
  description says "debug logs."

PASS if >= 4 of the above points (or clear equivalents) were raised.
FAIL if fewer than 4 were raised, or if questions are generic rather than
grounded in the actual codebase structure.

Respond with PASS or FAIL on the last line.
