// Code intent and code change mutations.
// Pure functions -- input plan in, new plan out. No side effects.

import type { Plan, CodeIntent, CodeChange } from "../types.js";
import { nextIntentId, nextChangeId } from "../types.js";

// -- CodeIntent --

export function addIntent(
  p: Plan,
  data: {
    milestone: string;
    file: string;
    function?: string;
    behavior: string;
    decision_refs?: string[];
  },
): { plan: Plan; id: string } {
  const idx = p.milestones.findIndex((m) => m.id === data.milestone);
  if (idx === -1) throw new Error(`milestone ${data.milestone} not found`);

  const m = p.milestones[idx];
  const id = nextIntentId(m);
  const intent: CodeIntent = {
    id,
    file: data.file,
    function: data.function ?? null,
    behavior: data.behavior,
    decision_refs: data.decision_refs ?? [],
  };

  const updated = [...p.milestones];
  updated[idx] = {
    ...m,
    code_intents: [...m.code_intents, intent],
  };

  return {
    plan: { ...p, milestones: updated },
    id,
  };
}

export function setIntent(
  p: Plan,
  id: string,
  data: {
    file?: string;
    function?: string;
    behavior?: string;
    decision_refs?: string[];
  },
): Plan {
  for (let i = 0; i < p.milestones.length; i++) {
    const m = p.milestones[i];
    const ciIdx = m.code_intents.findIndex((ci) => ci.id === id);
    if (ciIdx !== -1) {
      const ci = m.code_intents[ciIdx];
      const updated: CodeIntent = {
        ...ci,
        file: data.file ?? ci.file,
        function: data.function ?? ci.function,
        behavior: data.behavior ?? ci.behavior,
        decision_refs: data.decision_refs ?? ci.decision_refs,
      };

      const intents = [...m.code_intents];
      intents[ciIdx] = updated;

      const milestones = [...p.milestones];
      milestones[i] = { ...m, code_intents: intents };

      return { ...p, milestones };
    }
  }
  throw new Error(`intent ${id} not found`);
}

// -- CodeChange --

export function addChange(
  p: Plan,
  data: {
    milestone: string;
    file: string;
    intent_ref?: string;
    diff?: string;
    doc_diff?: string;
    comments?: string;
  },
): { plan: Plan; id: string } {
  const idx = p.milestones.findIndex((m) => m.id === data.milestone);
  if (idx === -1) throw new Error(`milestone ${data.milestone} not found`);

  const m = p.milestones[idx];
  const id = nextChangeId(m);
  const change: CodeChange = {
    id,
    intent_ref: data.intent_ref ?? null,
    file: data.file,
    diff: data.diff ?? "",
    doc_diff: data.doc_diff ?? "",
    comments: data.comments ?? "",
  };

  const updated = [...p.milestones];
  updated[idx] = {
    ...m,
    code_changes: [...m.code_changes, change],
  };

  return {
    plan: { ...p, milestones: updated },
    id,
  };
}

function updateChange(
  p: Plan,
  id: string,
  fn: (c: CodeChange) => CodeChange,
): Plan {
  for (let i = 0; i < p.milestones.length; i++) {
    const m = p.milestones[i];
    const ccIdx = m.code_changes.findIndex((cc) => cc.id === id);
    if (ccIdx !== -1) {
      const changes = [...m.code_changes];
      changes[ccIdx] = fn(m.code_changes[ccIdx]);

      const milestones = [...p.milestones];
      milestones[i] = { ...m, code_changes: changes };

      return { ...p, milestones };
    }
  }
  throw new Error(`code_change ${id} not found`);
}

export function setChangeDiff(p: Plan, id: string, diff: string): Plan {
  return updateChange(p, id, (c) => ({ ...c, diff }));
}

export function setChangeDocDiff(p: Plan, id: string, doc_diff: string): Plan {
  return updateChange(p, id, (c) => ({ ...c, doc_diff }));
}

export function setChangeComments(p: Plan, id: string, comments: string): Plan {
  return updateChange(p, id, (c) => ({ ...c, comments }));
}

export function setChangeFile(p: Plan, id: string, file: string): Plan {
  return updateChange(p, id, (c) => ({ ...c, file }));
}

export function setChangeIntentRef(
  p: Plan,
  id: string,
  intent_ref: string,
): Plan {
  return updateChange(p, id, (c) => ({ ...c, intent_ref }));
}
