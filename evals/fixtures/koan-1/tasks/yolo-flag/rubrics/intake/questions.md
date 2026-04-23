Task-specific criteria for the --yolo task. These are appended to the fixture-level intake/questions rubric at grade time.

Beyond the generic checks, the orchestrator should have raised at least 3 of the following --yolo-specific points as targeted questions or observations during intake:

- Flagged the inaccuracy in the task description's claim "--yolo is currently a no-op": --yolo is already used in the codex and gemini runner paths as an "accept everything" permission mode; the accurate framing is that --yolo currently has no effect on koan's own user-interaction gates (`koan_yield`, `koan_ask_question`).
- Asked what `koan_yield` should return in yolo mode (recommended behavior: the recommended-progression hint from the yield's suggestions list).
- Asked what `koan_ask_question` should return in yolo mode (recommended behavior: the pre-configured recommended answer if one exists, or free-form text such as "use your best judgement").
- Asked whether UI events should still be emitted when interactions are auto-answered (acceptable options: skip entirely, emit with an `auto_answered` flag, or emit normally and resolve immediately).
- Asked about the broader use case for --yolo as a non-interactive mode (expected answer: running evals in unsupervised mode).

PASS if at least 3 of the above were raised.
FAIL if fewer than 3 were raised.
