# Guided phase transitions

## Overview

Each `PhaseBinding` in a workflow carries an optional `next_phase: str | None`
field that controls how the orchestrator exits the phase:

- **`next_phase = "some-phase"`** -- auto-advance. The orchestrator calls
  `koan_set_phase("some-phase")` directly after summarizing what was accomplished.
  No `koan_yield` is needed; the workflow advances without user input.

- **`next_phase = None`** -- full yield. The orchestrator calls `koan_yield`
  with structured suggestions and waits for the user to confirm direction before
  calling `koan_set_phase`.

Auto-advance is guidance, not enforcement. The orchestrator may call `koan_yield`
instead of `koan_set_phase` when exceptional circumstances warrant user direction
(see Override discipline below). The default promotes smooth forward progress on
the happy path; overrides surface when findings demand it.

## Per-workflow transition tables

### Plan workflow

| Phase         | `next_phase`  | Behaviour                                                                         |
| ------------- | ------------- | --------------------------------------------------------------------------------- |
| `intake`      | `plan-spec`   | auto-advance                                                                      |
| `plan-spec`   | `plan-review` | auto-advance                                                                      |
| `plan-review` | `None`        | full yield (orchestrator picks `plan-spec` for loop-back or `execute` to proceed) |
| `execute`     | `exec-review` | auto-advance                                                                      |
| `exec-review` | `None`        | full yield (orchestrator picks `curation` to proceed or `plan-spec` to loop back) |
| `curation`    | `None`        | terminal yield -- workflow ends here                                              |

### Milestones workflow

| Phase              | `next_phase`     | Behaviour                                                                                   |
| ------------------ | ---------------- | ------------------------------------------------------------------------------------------- |
| `intake`           | `milestone-spec` | auto-advance                                                                                |
| `milestone-spec`   | `plan-spec`      | auto-advance (CREATE-mode default; orchestrator may yield to milestone-review if warranted) |
| `milestone-review` | `None`           | full yield (orchestrator picks `milestone-spec` for revision or `plan-spec` to proceed)     |
| `plan-spec`        | `plan-review`    | auto-advance                                                                                |
| `plan-review`      | `None`           | full yield (orchestrator picks `plan-spec` for loop-back or `execute` to proceed)           |
| `execute`          | `exec-review`    | auto-advance                                                                                |
| `exec-review`      | `None`           | full yield (orchestrator picks `milestone-spec` loop, `plan-spec`, or `curation`)           |
| `curation`         | `None`           | terminal yield -- workflow ends here                                                        |

## The trampoline and its removal

**Pre-M3:** when `get_next_step` returned `None`, the `koan_complete_step` handler
called `format_phase_complete(phase, suggested_phases, descriptions)`. This rendered
a "Phase Complete" banner telling the orchestrator to summarize and call `koan_yield`.
The orchestrator then called `koan_yield` and the user directed the next phase.

**Post-M3:** the directive moved into each phase module's last-step
`step_guidance()` return value, carried in the `invoke_after` field of
`StepGuidance`. Each last step calls:

```python
invoke_after=terminal_invoke(ctx.next_phase, ctx.suggested_phases)
```

The `terminal_invoke(next_phase, suggested_phases) -> str` helper (in
`koan/phases/format_step.py`) renders either the auto-advance directive or the
full-yield directive depending on whether `next_phase` is bound. Because
`invoke_after` is rendered at the bottom of the step guidance by `format_step()`,
the LLM receives the directive at the same recency position as the former
`DEFAULT_INVOKE` footer.

The `koan_complete_step` phase-boundary branch became a defensive fallback:

```
if next_step is None:
    # nudge the orchestrator back to koan_set_phase or koan_yield
    return "This phase has no further steps. The directive at the end of your
            prior step's guidance instructed you to call koan_set_phase or
            koan_yield -- follow that directive now."
```

The LLM should never land here after M3 -- the `invoke_after` directive fires
before `koan_complete_step` is called at all. The fallback catches accidental
calls gracefully rather than crashing.

## Override discipline

The orchestrator may call `koan_yield` instead of `koan_set_phase` (even when
`next_phase` is bound) when any of the following apply:

1. An exceptional finding has surfaced that the user must direct (e.g.,
   exec-review reveals a fundamental flaw requiring a scope change beyond
   the current plan).
2. The phase outcome does not match any single bound `next_phase` (e.g.,
   milestone-spec completed all milestones on the first pass and curation
   is the right target, not plan-spec).
3. The user asked mid-phase to redirect the workflow.

This is intentionally soft -- prompt discipline rather than fence enforcement.
Review phases (`plan-review`, `milestone-review`, `exec-review`) are always
`next_phase=None` precisely because their outcome is inherently variable;
auto-advance would bypass the signal they exist to surface.

## The `directed_phases` interaction

`directed_phases` (yolo mode, set by the eval harness) short-circuits `koan_yield`
to a fixed phase sequence so eval runs do not pause for user input. It is
independent of `next_phase`:

- A phase with `next_phase` bound calls `koan_set_phase` directly -- it never
  reaches the yield handler and is unaffected by `directed_phases`.
- A phase with `next_phase=None` calls `koan_yield`, which may be short-circuited
  by `directed_phases` to the next configured phase.

Both regimes work correctly with the other present.

## Eval fixture acknowledgement

`evals/fixtures/koan-1/repo/` is a pinned snapshot of the koan codebase at an
earlier point. It retains the old `format_phase_complete` symbol in its copy of
`koan/phases/format_step.py`. This is expected and correct: the eval runner
spawns koan as a subprocess from the fixture submodule, so the fixture is
self-contained and unaffected by changes in the live tree. Do NOT edit the eval
fixture to remove the old symbol -- it would break the snapshot's pin.
