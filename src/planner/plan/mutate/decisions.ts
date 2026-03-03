// Decision log mutations: decisions, rejected alternatives, risks.
// Pure functions -- input plan in, new plan out. No side effects.

import type { Plan, Decision, RejectedAlternative, Risk } from "../types.js";
import {
  nextDecisionId,
  nextRejectedAltId,
  nextRiskId,
} from "../types.js";

// -- Decision --

export function addDecision(
  p: Plan,
  data: { decision: string; reasoning: string; source?: string },
): { plan: Plan; id: string } {
  const id = nextDecisionId(p);
  const decision: Decision = {
    id,
    decision: data.decision,
    reasoning_chain: data.reasoning,
    source: data.source ?? null,
  };
  return {
    plan: {
      ...p,
      planning_context: {
        ...p.planning_context,
        decision_log: [...p.planning_context.decision_log, decision],
      },
    },
    id,
  };
}

export function setDecision(
  p: Plan,
  id: string,
  data: { decision?: string; reasoning?: string; source?: string },
): Plan {
  const idx = p.planning_context.decision_log.findIndex((d) => d.id === id);
  if (idx === -1) throw new Error(`decision ${id} not found`);

  const d = p.planning_context.decision_log[idx];
  const updated: Decision = {
    ...d,
    decision: data.decision ?? d.decision,
    reasoning_chain: data.reasoning ?? d.reasoning_chain,
    source: data.source ?? d.source,
  };

  const log = [...p.planning_context.decision_log];
  log[idx] = updated;

  return {
    ...p,
    planning_context: { ...p.planning_context, decision_log: log },
  };
}

// -- RejectedAlternative --

export function addRejectedAlternative(
  p: Plan,
  data: { alternative: string; rejection_reason: string; decision_ref: string },
): { plan: Plan; id: string } {
  const id = nextRejectedAltId(p);
  const ra: RejectedAlternative = {
    id,
    alternative: data.alternative,
    rejection_reason: data.rejection_reason,
    decision_ref: data.decision_ref,
  };
  return {
    plan: {
      ...p,
      planning_context: {
        ...p.planning_context,
        rejected_alternatives: [
          ...p.planning_context.rejected_alternatives,
          ra,
        ],
      },
    },
    id,
  };
}

export function setRejectedAlternative(
  p: Plan,
  id: string,
  data: {
    alternative?: string;
    rejection_reason?: string;
    decision_ref?: string;
  },
): Plan {
  const idx = p.planning_context.rejected_alternatives.findIndex(
    (r) => r.id === id,
  );
  if (idx === -1) throw new Error(`rejected_alternative ${id} not found`);

  const r = p.planning_context.rejected_alternatives[idx];
  const updated: RejectedAlternative = {
    ...r,
    alternative: data.alternative ?? r.alternative,
    rejection_reason: data.rejection_reason ?? r.rejection_reason,
    decision_ref: data.decision_ref ?? r.decision_ref,
  };

  const list = [...p.planning_context.rejected_alternatives];
  list[idx] = updated;

  return {
    ...p,
    planning_context: { ...p.planning_context, rejected_alternatives: list },
  };
}

// -- Risk --

export function addRisk(
  p: Plan,
  data: {
    risk: string;
    mitigation: string;
    anchor?: string;
    decision_ref?: string;
  },
): { plan: Plan; id: string } {
  const id = nextRiskId(p);
  const risk: Risk = {
    id,
    risk: data.risk,
    mitigation: data.mitigation,
    anchor: data.anchor ?? null,
    decision_ref: data.decision_ref ?? null,
  };
  return {
    plan: {
      ...p,
      planning_context: {
        ...p.planning_context,
        known_risks: [...p.planning_context.known_risks, risk],
      },
    },
    id,
  };
}

export function setRisk(
  p: Plan,
  id: string,
  data: {
    risk?: string;
    mitigation?: string;
    anchor?: string;
    decision_ref?: string;
  },
): Plan {
  const idx = p.planning_context.known_risks.findIndex((r) => r.id === id);
  if (idx === -1) throw new Error(`risk ${id} not found`);

  const r = p.planning_context.known_risks[idx];
  const updated: Risk = {
    ...r,
    risk: data.risk ?? r.risk,
    mitigation: data.mitigation ?? r.mitigation,
    anchor: data.anchor ?? r.anchor,
    decision_ref: data.decision_ref ?? r.decision_ref,
  };

  const list = [...p.planning_context.known_risks];
  list[idx] = updated;

  return {
    ...p,
    planning_context: { ...p.planning_context, known_risks: list },
  };
}
