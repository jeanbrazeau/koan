// Milestone mutations: add, and per-field setters.
// Pure functions -- input plan in, new plan out. No side effects.

import type { Plan, Milestone } from "../types.js";
import { nextMilestoneId } from "../types.js";

export function addMilestone(
  p: Plan,
  data: {
    name: string;
    files?: string[];
    flags?: string[];
    requirements?: string[];
    acceptance_criteria?: string[];
    tests?: string[];
  },
): { plan: Plan; id: string } {
  const id = nextMilestoneId(p);
  const milestone: Milestone = {
    id,
    number: p.milestones.length + 1,
    name: data.name,
    files: data.files ?? [],
    flags: data.flags ?? [],
    requirements: data.requirements ?? [],
    acceptance_criteria: data.acceptance_criteria ?? [],
    tests: data.tests ?? [],
    code_intents: [],
    code_changes: [],
    documentation: {
      module_comment: null,
      docstrings: [],
      function_blocks: [],
      inline_comments: [],
    },
    is_documentation_only: false,
    delegated_to: null,
  };
  return {
    plan: {
      ...p,
      milestones: [...p.milestones, milestone],
    },
    id,
  };
}

function updateMilestone(
  p: Plan,
  id: string,
  fn: (m: Milestone) => Milestone,
): Plan {
  const idx = p.milestones.findIndex((m) => m.id === id);
  if (idx === -1) throw new Error(`milestone ${id} not found`);

  const updated = [...p.milestones];
  updated[idx] = fn(p.milestones[idx]);
  return { ...p, milestones: updated };
}

export function setMilestoneName(p: Plan, id: string, name: string): Plan {
  return updateMilestone(p, id, (m) => ({ ...m, name }));
}

export function setMilestoneFiles(p: Plan, id: string, files: string[]): Plan {
  return updateMilestone(p, id, (m) => ({ ...m, files }));
}

export function setMilestoneFlags(p: Plan, id: string, flags: string[]): Plan {
  return updateMilestone(p, id, (m) => ({ ...m, flags }));
}

export function setMilestoneRequirements(
  p: Plan,
  id: string,
  requirements: string[],
): Plan {
  return updateMilestone(p, id, (m) => ({ ...m, requirements }));
}

export function setMilestoneAcceptanceCriteria(
  p: Plan,
  id: string,
  criteria: string[],
): Plan {
  return updateMilestone(p, id, (m) => ({ ...m, acceptance_criteria: criteria }));
}

export function setMilestoneTests(p: Plan, id: string, tests: string[]): Plan {
  return updateMilestone(p, id, (m) => ({ ...m, tests }));
}
