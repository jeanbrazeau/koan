# Planning Widget Refresh

## Context
The planning widget now follows the design-deck contract selected on Feb 25 2026:

- **Canvas direction:** Stacked Modular Cards
- **Navigation direction:** Vertical Timeline Rail
- **Log strategy:** Declarative shape-table serialization + dense two-column layout
- **QR strategy:** Inline integrated section (not a detached sub-card)

The goal is to keep a long-running (1-2h) planning session readable in real time while preserving high-signal audit telemetry.

## Decisions & Rationale

### 1) Deterministic log serialization (hybrid detail)
- Keep **tool name** as the primary scan anchor.
- Use a declarative per-tool formatter table for known `koan_*` tools.
- Unknown tools fall back to tool-name-only output.
- Field order is deterministic and curated (e.g., IDs first), not alphabetical.

**Rationale:** Users scan continuously during execution; stable order makes visual parsing faster and reduces cognitive churn between updates.

### 2) Selective detail by field type
- Arrays render as **first item + count** (`[first] +N`).
- Free-form fields (`diff`, `doc_diff`, `comments`, large narrative strings) render as **size metadata only** (`184L/9.2k`), never full body.
- Getter tools (`koan_get_*`) show target identifiers plus response size metadata (`resp:42L/3.1k`).

**Rationale:** Maintains observability without blowing out vertical space or flooding with low-value text.

### 3) Latest log as dense two-column grid
- Left column: tool name (bold accent anchor).
- Right column: compact deterministic summary.
- Column widths adapt to available terminal width + observed tool-name lengths (protecting right-column readability).
- High-value rows may wrap to 2 lines; if overflow exceeds 2 lines, the second line is re-compacted with ellipsis.
- Repeated events remain separate rows (no dedup/collapse).

**Rationale:** Preserves temporal fidelity while increasing information density and keeping the "what just happened" answer immediate, even under constrained widths.

### 4) QR is a first-class workflow section
- QR renders inline in detail pane with divider rule (no detached mini-card border).
- Visible for Plan design (and contractually for Plan execution), hidden only for Context gathering.
- QR starts directly in the **`execute`** stage for iteration 1 (non-fix mode); fix iterations reuse the same stage model.
- QR block is normalized to a fixed structure: header, phase rail, counters, divider.
- Metadata is budgeted to **64 visible chars max** and progressively compacted (`phase/iter/mode` -> `iN/M`, `d/p/f/t`) when width is constrained.
- Counter line emphasizes severity: `fail` is error-colored; `pass` is accent; others remain muted/dim.

**Rationale:** QR is not optional side telemetry; it is the acceptance loop for the plan. The UI should communicate that structural importance while remaining legible and shape-stable at smaller widths.

## Layout Overview
```
┌──────────────────────────────── Planning ────────────────────────────────────┐
│  ┃ Context gathering ┃  ┃ Plan design ┃  ┃ Plan code ┃  ┃ Plan docs ┃      │
│                                                                            │
│  ● Context gathering        qr-decompose: Step 2/13: Holistic Concerns     │
│  │      DONE               read CLAUDE.md · 41L/1709c                      │
│  │                                                                         │
│  ● Plan design             QR | phase:decompose · iter 1/6 initial         │
│  │      CURRENT            Execute → QR decompose → QR verify              │
│  │                         done:0/24 pass:0 fail:0 todo:24                 │
│  │                         ──────────────────────────────────────────────── │
│  ○ Plan code               Plan · <plan-id>                                 │
│  │      UPCOMING                                                          │
│  ○ Plan docs                                                                │
│──────────────────────────────────────────────────────────────────────────────│
│    Latest log                                                               │
│  koan_set_milestone_tests   id=M-002 · tests:["covers retries"] +7         │
│  koan_get_milestone         id=M-002 · resp:42L/3.1k                        │
│  koan_add_intent            milestone=M-002 · file=src/planner/ui/widget.ts │
│  koan_set_change_diff       id=CC-M-001-002 · diff:184L/9.2k                │
│  koan_qr_assign_group       phase=plan-design · ids:[QR-001] +11            │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Rendering Guide
1. **Canvas** – Keep using `canvasLine()` so widget content remains full-width over `toolPendingBg`.
2. **Main card** – Keep solid border + consistent inner padding via shared `renderBox()` helper.
3. **Timeline rail** – Maintain status icon/color semantics (`active=accent`, `done=dim`, `failed=error`).
4. **Detail pane** – Render in this order:
   - a dim section label (`Current step`) to create hierarchy
   - step title + optional activity
   - QR integrated section (if visible)
   - footer metadata (`Plan · ID`) pinned to bottom via dynamic padding
5. **QR section** – Use inline header + phase rail + metadata line + divider. Avoid nested border style to keep it visually native to the right pane. Keep line geometry stable (fixed 3-line payload + divider) and enforce a 64-char metadata budget before clamping to pane width.
6. **Latest log section** – Keep it inside the same outer card, separated by a horizontal divider. Reuse the same left/right column split (`timelineWidth` / `detailWidth`) and gap as the planning body so vertical alignment stays consistent.

## Data Contract Notes
- `LogLine` now carries:
  - `tool` (left column)
  - `summary` (right column)
  - `highValue` (whether 2-line wrap is allowed)
- QR state in widget includes:
  - `qrIteration`, `qrIterationsMax`, `qrMode`, `qrPhase`
  - `qrDone`, `qrTotal`, `qrPass`, `qrFail`, `qrTodo`

## Future Work (contracted, not yet implemented)
- Plan execution phase should reuse the same QR integrated section semantics.
- Optional compact mode for very narrow terminals can reduce metadata verbosity while preserving deterministic ordering.
