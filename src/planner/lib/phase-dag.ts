// Phase transition DAG — the single source of truth for valid epic phase transitions.
//
// Consulted by:
//   - the driver (to decide whether to spawn the orchestrator or auto-advance)
//   - koan_set_next_phase (to validate the committed transition)
//   - WorkflowOrchestratorPhase step 2 guidance (lists available phases)
//
// Updating the DAG here is sufficient when adding new successor edges.
// Promoting a stub phase to a real implementation additionally requires the
// Phase Promotion Checklist in docs/architecture.md.

import type { EpicPhase } from "../types.js";

/** Valid successor phases for each phase. Order = recommendation priority.
 *  The first entry is the most-recommended default path when the orchestrator
 *  presents options. */
export const PHASE_TRANSITIONS: Readonly<Record<EpicPhase, readonly EpicPhase[]>> = {
  "intake":                     ["brief-generation", "core-flows"],
  "brief-generation":           ["core-flows"],
  "core-flows":                 ["tech-plan"],
  "tech-plan":                  ["ticket-breakdown"],
  "ticket-breakdown":           ["cross-artifact-validation"],
  "cross-artifact-validation":  ["execution"],
  "execution":                  ["implementation-validation"],
  "implementation-validation":  ["completed"],
  "completed":                  [],
};

/** Phases that have a real implementation (subagent-backed).
 *  All other phases are stubs that auto-advance when reached.
 *  Add a phase here when promoting its stub to a real implementation. */
export const IMPLEMENTED_PHASES: ReadonlySet<EpicPhase> = new Set<EpicPhase>([
  "intake",
  "brief-generation",
]);

/** Returns valid next phases from the DAG. */
export function getSuccessorPhases(phase: EpicPhase): readonly EpicPhase[] {
  return PHASE_TRANSITIONS[phase] ?? [];
}

/** True when the driver can auto-advance without consulting the orchestrator.
 *  A single successor means the transition is unambiguous — spawning an
 *  orchestrator would add latency and LLM cost with no user value. */
export function isAutoAdvance(phase: EpicPhase): boolean {
  return getSuccessorPhases(phase).length === 1;
}

/** True when the phase has no subagent implementation and should be skipped.
 *  Stubs log a placeholder message and carry forward pendingInstructions. */
export function isStubPhase(phase: EpicPhase): boolean {
  return phase !== "completed" && !IMPLEMENTED_PHASES.has(phase);
}

/** Validates that a proposed transition is legal before committing.
 *  Called by koan_set_next_phase to prevent the orchestrator from
 *  hallucinating a phase name not in the DAG. */
export function isValidTransition(from: EpicPhase, to: EpicPhase): boolean {
  return getSuccessorPhases(from).includes(to);
}

/** Human-readable one-line description of each phase.
 *  Used by writeWorkflowStatus() and the orchestrator's step 2 guidance. */
export const PHASE_DESCRIPTIONS: Readonly<Record<EpicPhase, string>> = {
  "intake":                     "Multi-round codebase exploration and structured Q&A to align on requirements",
  "brief-generation":           "Distill intake context into a compact product-level epic brief",
  "core-flows":                 "Define user journeys with sequence diagrams",
  "tech-plan":                  "Specify technical architecture: approach, data model, component design",
  "ticket-breakdown":           "Generate story-sized implementation tickets with dependency diagrams",
  "cross-artifact-validation":  "Validate cross-boundary consistency across all spec artifacts",
  "execution":                  "Implement tickets through a supervised batch process with verification",
  "implementation-validation":  "Post-execution review evaluating alignment and correctness against specs",
  "completed":                  "Pipeline complete",
};
