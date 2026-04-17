---
title: 'Intake confidence loop removed: unnecessary scout batches and intrinsic self-correction
  risk'
type: lesson
created: '2026-04-16T08:34:26Z'
modified: '2026-04-16T08:34:26Z'
related:
- 0002-step-first-workflow-pattern-boot-prompt-is.md
- 0005-phase-trust-model-plan-review-as-designated.md
---

The intake phase in koan (`koan/phases/intake.py`) previously included a confidence-gated loop where steps 2-4 would repeat based on a structured confidence value. Leon removed this loop in favour of the current 2-step design (Gather + Deepen), as documented in `docs/intake-loop.md` (Pitfalls section -- "Don't add a confidence loop"), confirmed in the codebase as of 2026-04-16. Leon identified three reasons for removal: (a) the loop produced unnecessary second scout batches -- repeating expensive scout runs that a focused single Deepen pass could replace; (b) the self-verification step ("Reflect") risked intrinsic self-correction without external grounding, meaning the same LLM checking its own prior reasoning rather than verifying against actual codebase files; (c) one focused pass through the Deepen step was sufficient when the step was designed to be thorough. Leon replaced the confidence gate with a design that defines phase completion by depth of understanding rather than loop iteration count, and explicitly removed per-round question limits that had previously created an implicit ceiling discouraging iterative deepening.
