## Task-specific additions (add-logs)

Beyond the generic plan-spec coherence checks, the plan should:

- Cover multiple subsystems. A plan that only adds logging to one module
  (e.g., only the driver, or only phases) fails to reflect the broad survey
  expected from intake. The logging gap is systemic; the plan should address
  it systemically.
- Preserve the existing logging infrastructure. The plan should extend
  `koan/logger.py` and `get_logger()`, not introduce a competing framework
  or reinvent the handler setup.
- Not propose removing or restructuring existing logging in the memory
  subsystem. The memory subsystem is already well-logged; the plan should
  bring other modules up to a comparable level, not tear down what exists.
- Stay scoped to adding logs. The plan should not propose broader refactors
  (e.g., restructuring phase modules, changing the driver loop, adding
  observability infrastructure) unless directly required for logging.

PASS if all four criteria are met.
FAIL if any are violated.

Respond with PASS or FAIL on the last line.
