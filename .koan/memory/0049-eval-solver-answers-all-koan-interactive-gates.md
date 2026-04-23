---
title: Eval runner uses yolo-mode auto-responses and post-hoc projection harvest for
  per-phase scoring
type: decision
created: '2026-04-17T12:06:18Z'
modified: '2026-04-22T09:23:30Z'
---

The koan eval runner's interactive-gate-handling strategy (at `evals/runner.py` as of 2026-04-22, originally `evals/solver.py`) was revised twice. On 2026-04-17, Leon originally adopted an SSE-driven design in which the solver subscribed to `/events`, detected `/run/activeYield` and `/run/focus` patch ops, and POSTed a fixed "Please use your best judgment" message to `/api/chat` and `/api/answer` to unblock every gate. That design was retired because it duplicated gate-detection logic the koan server already performs internally and did not extend cleanly to per-phase scoring.

On 2026-04-19, Leon adopted a two-part replacement in `evals/solver.py`: (1) the solver flipped `app_state.yolo = True` on its in-process `AppState` handle before calling `create_app()`, so koan's existing yolo-mode auto-response paths (`_yolo_yield_response` and `_yolo_ask_answer` in `koan/web/mcp_endpoint.py`) resolved every `koan_yield` and `koan_ask_question` with the recommended suggestion or option (falling back to "use your best judgement") without solver involvement; (2) after `projection.run.completion` is non-null, the solver harvested per-phase data from `ProjectionStore.events` -- phase-bucketed `koan_ask_question` / `koan_yield` / `koan_set_phase` / `koan_request_scouts` / `koan_memorize` / `koan_search` tool_called events plus `artifact_*` events walked against `phase_started` boundaries -- for downstream per-phase scoring.

On 2026-04-22 during the Inspect-to-DeepEval migration, Leon renamed `evals/solver.py` to `evals/runner.py`, removed the Inspect `@solver` decorator and the `solve(state: TaskState, generate) -> TaskState` signature, and replaced them with a plain `async def run_koan(case: Case) -> dict` whose sole output is the harvest dict. The `transcript().info(...)` progress lines were replaced by `logging.info(...)` on the `koan.evals.runner` logger. `_find_free_port`, `_wait_for_server`, `_wait_for_completion`, and `_validate_directed_phases` carried forward verbatim. The yolo-mode + post-hoc harvest strategy itself is unchanged; only the framework wrapper around it changed. The surrogate-user-LLM alternative remains rejected for the same reason as before (added cost, non-determinism).
