---
workflow: plan
directed_phases:
  - intake
  - plan-spec
  - done
---

Grade the consistency and coherence of the complete workflow across all phases.

This rubric evaluates cross-phase quality, not per-phase quality.

Check the following:

- Intake findings are reflected in the plan. The plan.md approach should be traceable to the questions and discoveries from intake -- the decisions made during intake should visibly shape the plan.
- Phase summaries form a coherent chain. The intake summary's conclusions should be consistent with the plan-spec summary's approach. No contradiction between summaries.
- At minimum, both intake and plan-spec phases were observed and produced summaries. A workflow that skipped either phase fails this rubric.
- No hallucinated pivots. The plan does not introduce a completely different approach than what intake suggested, without an explicit rationale.

## Task-specific additions (add-logs)

Beyond the generic cross-phase coherence checks, the plan for the "add logs" task should visibly carry forward the intake-phase decisions on:

- what type of logs: frontend, backend, etc.
- purpose of the logs / problem they're solving
- log level strategy (what constitutes as debug vs info vs warning vs error)
- structured vs unstructured logging

If intake decided a specific behavior for any of these and plan-spec contradicts it without rationale, that is a hallucinated pivot and fails this rubric.

PASS if all four generic criteria are met across the observed phases AND the plan's approach is traceable to the intake decisions on the four add-logs-specific points above.
FAIL if any criterion is violated, or if fewer than two phases are present, or if plan-spec silently diverges from an intake decision.

Respond with PASS or FAIL on the last line.
