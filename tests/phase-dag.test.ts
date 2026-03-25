// Tests for lib/phase-dag.ts: transition DAG, query functions, and type guards.

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  PHASE_TRANSITIONS,
  IMPLEMENTED_PHASES,
  PHASE_DESCRIPTIONS,
  getSuccessorPhases,
  isAutoAdvance,
  isStubPhase,
  isValidTransition,
} from "../src/planner/lib/phase-dag.js";
import type { EpicPhase } from "../src/planner/types.js";

// ---------------------------------------------------------------------------
// PHASE_TRANSITIONS completeness
// ---------------------------------------------------------------------------

describe("PHASE_TRANSITIONS", () => {
  const ALL_PHASES: EpicPhase[] = [
    "intake", "brief-generation", "core-flows", "tech-plan",
    "ticket-breakdown", "cross-artifact-validation", "execution",
    "implementation-validation", "completed",
  ];

  it("has an entry for every EpicPhase", () => {
    for (const phase of ALL_PHASES) {
      assert.ok(phase in PHASE_TRANSITIONS, `Missing entry for phase: ${phase}`);
    }
  });

  it("completed has no successors (terminal marker)", () => {
    assert.equal(PHASE_TRANSITIONS["completed"].length, 0);
  });

  it("intake has two successors (brief-generation and core-flows)", () => {
    const successors = PHASE_TRANSITIONS["intake"];
    assert.equal(successors.length, 2);
    assert.ok(successors.includes("brief-generation"));
    assert.ok(successors.includes("core-flows"));
  });

  it("brief-generation has exactly one successor (core-flows)", () => {
    const successors = PHASE_TRANSITIONS["brief-generation"];
    assert.equal(successors.length, 1);
    assert.equal(successors[0], "core-flows");
  });

  it("all successor entries are valid EpicPhase values", () => {
    const allPhaseSet = new Set<string>(ALL_PHASES);
    for (const [phase, successors] of Object.entries(PHASE_TRANSITIONS)) {
      for (const succ of successors) {
        assert.ok(allPhaseSet.has(succ), `Successor "${succ}" of "${phase}" is not a valid EpicPhase`);
      }
    }
  });
});

// ---------------------------------------------------------------------------
// getSuccessorPhases
// ---------------------------------------------------------------------------

describe("getSuccessorPhases", () => {
  it("returns correct successors for intake (multi-successor phase)", () => {
    const successors = getSuccessorPhases("intake");
    assert.equal(successors.length, 2);
    assert.equal(successors[0], "brief-generation"); // recommended first
    assert.equal(successors[1], "core-flows");
  });

  it("returns correct successor for brief-generation (single-successor phase)", () => {
    const successors = getSuccessorPhases("brief-generation");
    assert.equal(successors.length, 1);
    assert.equal(successors[0], "core-flows");
  });

  it("returns empty array for completed (terminal phase)", () => {
    const successors = getSuccessorPhases("completed");
    assert.equal(successors.length, 0);
  });

  it("returns successors in recommendation priority order (first = most recommended)", () => {
    // intake: brief-generation is recommended, core-flows is alternative
    const successors = getSuccessorPhases("intake");
    assert.equal(successors[0], "brief-generation");
  });
});

// ---------------------------------------------------------------------------
// isAutoAdvance
// ---------------------------------------------------------------------------

describe("isAutoAdvance", () => {
  it("returns false for intake (2 successors — requires orchestrator)", () => {
    assert.equal(isAutoAdvance("intake"), false);
  });

  it("returns true for brief-generation (1 successor)", () => {
    assert.equal(isAutoAdvance("brief-generation"), true);
  });

  it("returns true for core-flows (1 successor)", () => {
    assert.equal(isAutoAdvance("core-flows"), true);
  });

  it("returns true for all single-successor phases", () => {
    const singleSuccessorPhases: EpicPhase[] = [
      "brief-generation", "core-flows", "tech-plan", "ticket-breakdown",
      "cross-artifact-validation", "execution", "implementation-validation",
    ];
    for (const phase of singleSuccessorPhases) {
      assert.equal(isAutoAdvance(phase), true, `Expected isAutoAdvance(${phase}) to be true`);
    }
  });

  it("returns false for completed (0 successors — terminal)", () => {
    // completed has 0 successors, not 1, so isAutoAdvance should be false
    assert.equal(isAutoAdvance("completed"), false);
  });
});

// ---------------------------------------------------------------------------
// isStubPhase
// ---------------------------------------------------------------------------

describe("isStubPhase", () => {
  it("returns false for implemented phases", () => {
    assert.equal(isStubPhase("intake"), false);
    assert.equal(isStubPhase("brief-generation"), false);
  });

  it("returns true for stub phases", () => {
    const stubPhases: EpicPhase[] = [
      "core-flows", "tech-plan", "ticket-breakdown",
      "cross-artifact-validation", "execution", "implementation-validation",
    ];
    for (const phase of stubPhases) {
      assert.equal(isStubPhase(phase), true, `Expected isStubPhase(${phase}) to be true`);
    }
  });

  it("returns false for completed (terminal marker, not a stub)", () => {
    // completed is excluded by the `phase !== 'completed'` guard in isStubPhase
    assert.equal(isStubPhase("completed"), false);
  });

  it("IMPLEMENTED_PHASES contains intake and brief-generation", () => {
    assert.ok(IMPLEMENTED_PHASES.has("intake"));
    assert.ok(IMPLEMENTED_PHASES.has("brief-generation"));
  });

  it("IMPLEMENTED_PHASES does not contain stub phases", () => {
    const stubPhases: EpicPhase[] = [
      "core-flows", "tech-plan", "ticket-breakdown",
      "cross-artifact-validation", "execution", "implementation-validation",
    ];
    for (const phase of stubPhases) {
      assert.equal(IMPLEMENTED_PHASES.has(phase), false, `${phase} should not be in IMPLEMENTED_PHASES`);
    }
  });
});

// ---------------------------------------------------------------------------
// isValidTransition
// ---------------------------------------------------------------------------

describe("isValidTransition", () => {
  it("returns true for valid DAG transitions", () => {
    assert.equal(isValidTransition("intake", "brief-generation"), true);
    assert.equal(isValidTransition("intake", "core-flows"), true);
    assert.equal(isValidTransition("brief-generation", "core-flows"), true);
    assert.equal(isValidTransition("implementation-validation", "completed"), true);
  });

  it("returns false for invalid transitions (non-successor phases)", () => {
    // Cannot skip from intake directly to ticket-breakdown
    assert.equal(isValidTransition("intake", "ticket-breakdown"), false);
    // Cannot go backward
    assert.equal(isValidTransition("brief-generation", "intake"), false);
    // Cannot transition from completed to anything
    assert.equal(isValidTransition("completed", "intake"), false);
    assert.equal(isValidTransition("completed", "brief-generation"), false);
  });

  it("returns false when 'to' is not a successor of 'from'", () => {
    assert.equal(isValidTransition("core-flows", "intake"), false);
    assert.equal(isValidTransition("execution", "brief-generation"), false);
  });

  it("validates the complete linear path after intake", () => {
    // The linear path: brief-generation → core-flows → tech-plan → ...
    const linearPath: Array<[EpicPhase, EpicPhase]> = [
      ["brief-generation", "core-flows"],
      ["core-flows", "tech-plan"],
      ["tech-plan", "ticket-breakdown"],
      ["ticket-breakdown", "cross-artifact-validation"],
      ["cross-artifact-validation", "execution"],
      ["execution", "implementation-validation"],
      ["implementation-validation", "completed"],
    ];
    for (const [from, to] of linearPath) {
      assert.equal(isValidTransition(from, to), true, `Expected valid: ${from} → ${to}`);
    }
  });
});

// ---------------------------------------------------------------------------
// PHASE_DESCRIPTIONS
// ---------------------------------------------------------------------------

describe("PHASE_DESCRIPTIONS", () => {
  const ALL_PHASES: EpicPhase[] = [
    "intake", "brief-generation", "core-flows", "tech-plan",
    "ticket-breakdown", "cross-artifact-validation", "execution",
    "implementation-validation", "completed",
  ];

  it("has a description for every EpicPhase", () => {
    for (const phase of ALL_PHASES) {
      assert.ok(phase in PHASE_DESCRIPTIONS, `Missing description for: ${phase}`);
      assert.ok(typeof PHASE_DESCRIPTIONS[phase] === "string", `Description for ${phase} must be a string`);
      assert.ok(PHASE_DESCRIPTIONS[phase].length > 0, `Description for ${phase} must not be empty`);
    }
  });
});
