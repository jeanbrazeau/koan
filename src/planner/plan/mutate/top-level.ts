// Top-level plan field mutations: overview, constraints, invisible knowledge.
// Pure functions -- input plan in, new plan out. No side effects.

import type { Plan, Overview, InvisibleKnowledge } from "../types.js";

export function setOverview(
  p: Plan,
  data: { problem?: string; approach?: string },
): Plan {
  const overview: Overview = {
    problem: data.problem ?? p.overview.problem,
    approach: data.approach ?? p.overview.approach,
  };
  return { ...p, overview };
}

export function setConstraints(p: Plan, constraints: string[]): Plan {
  return {
    ...p,
    planning_context: {
      ...p.planning_context,
      constraints,
    },
  };
}

export function setInvisibleKnowledge(
  p: Plan,
  data: { system?: string; invariants?: string[]; tradeoffs?: string[] },
): Plan {
  const ik: InvisibleKnowledge = {
    system: data.system ?? p.invisible_knowledge.system,
    invariants: data.invariants ?? p.invisible_knowledge.invariants,
    tradeoffs: data.tradeoffs ?? p.invisible_knowledge.tradeoffs,
  };
  return { ...p, invisible_knowledge: ik };
}
