## Task-specific additions (add-logs)

Beyond the generic plan-spec coherence checks, the plan should:

- Cover multiple subsystems -- a plan that only adds logging to one module (e.g., only the driver, or only phases) fails to reflect the broad survey expected from intake.
- Preserve the existing logging infrastructure by extending `koan/logger.py` and `get_logger()`, not introducing a competing framework or reinventing the handler setup.
- Not propose removing or restructuring existing logging in the memory subsystem (the memory subsystem is already well-logged; the plan should bring other modules up to a comparable level, not tear down what exists).
- Stay scoped to adding logs without proposing broader refactors (e.g., restructuring phase modules, changing the driver loop, adding observability infrastructure) unless directly required for logging.

PASS if all four criteria are met.
FAIL if any are violated.
