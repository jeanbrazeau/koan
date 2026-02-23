// Plan entity tools for code-phase entities: code intents and code changes.
// Uses planTool helper from entity-design (shared load-mutate-save-lock wrapper).

import { Type } from "@sinclair/typebox";
import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";

import type { PlanRef } from "../lib/dispatch.js";
import { planTool } from "./entity-design.js";
import {
  addIntent,
  setIntent,
  addChange,
  setChangeDiff,
  setChangeDocDiff,
  setChangeComments,
  setChangeFile,
  setChangeIntentRef,
} from "../plan/mutate/index.js";

export function registerPlanCodeEntityTools(
  pi: ExtensionAPI,
  planRef: PlanRef,
): void {
  // -- CodeIntent --
  planTool(pi, planRef, {
    name: "koan_add_intent",
    label: "Add code intent",
    description: "Add code intent to milestone.",
    parameters: Type.Object({
      milestone: Type.String(),
      file: Type.String(),
      function: Type.Optional(Type.String()),
      behavior: Type.String(),
      decision_refs: Type.Optional(Type.Array(Type.String())),
    }),
    execute: (p, params) => {
      const r = addIntent(p, params);
      return {
        plan: r.plan,
        message: `Added intent ${r.id} to milestone ${params.milestone}`,
      };
    },
  });

  planTool(pi, planRef, {
    name: "koan_set_intent",
    label: "Update code intent",
    description: "Update existing code intent by ID.",
    parameters: Type.Object({
      id: Type.String(),
      file: Type.Optional(Type.String()),
      function: Type.Optional(Type.String()),
      behavior: Type.Optional(Type.String()),
      decision_refs: Type.Optional(Type.Array(Type.String())),
    }),
    execute: (p, params) => {
      const updated = setIntent(p, params.id, params);
      return {
        plan: updated,
        message: `Updated intent ${params.id}`,
      };
    },
  });

  // -- CodeChange --
  planTool(pi, planRef, {
    name: "koan_add_change",
    label: "Add code change",
    description: "Add code change to milestone.",
    parameters: Type.Object({
      milestone: Type.String(),
      file: Type.String(),
      intent_ref: Type.Optional(Type.String()),
      diff: Type.Optional(Type.String()),
      doc_diff: Type.Optional(Type.String()),
      comments: Type.Optional(Type.String()),
    }),
    execute: (p, params) => {
      const r = addChange(p, params);
      return {
        plan: r.plan,
        message: `Added change ${r.id} to milestone ${params.milestone}`,
      };
    },
  });

  planTool(pi, planRef, {
    name: "koan_set_change_diff",
    label: "Set code change diff",
    description: "Update change diff.",
    parameters: Type.Object({
      id: Type.String(),
      diff: Type.String(),
    }),
    execute: (p, params) => {
      const updated = setChangeDiff(p, params.id, params.diff);
      return {
        plan: updated,
        message: `Set diff for change ${params.id}`,
      };
    },
  });

  planTool(pi, planRef, {
    name: "koan_set_change_doc_diff",
    label: "Set code change doc_diff",
    description: "Update change doc_diff.",
    parameters: Type.Object({
      id: Type.String(),
      doc_diff: Type.String(),
    }),
    execute: (p, params) => {
      const updated = setChangeDocDiff(p, params.id, params.doc_diff);
      return {
        plan: updated,
        message: `Set doc_diff for change ${params.id}`,
      };
    },
  });

  planTool(pi, planRef, {
    name: "koan_set_change_comments",
    label: "Set code change comments",
    description: "Update change comments.",
    parameters: Type.Object({
      id: Type.String(),
      comments: Type.String(),
    }),
    execute: (p, params) => {
      const updated = setChangeComments(p, params.id, params.comments);
      return {
        plan: updated,
        message: `Set comments for change ${params.id}`,
      };
    },
  });

  planTool(pi, planRef, {
    name: "koan_set_change_file",
    label: "Set code change file",
    description: "Update change file path.",
    parameters: Type.Object({
      id: Type.String(),
      file: Type.String(),
    }),
    execute: (p, params) => {
      const updated = setChangeFile(p, params.id, params.file);
      return {
        plan: updated,
        message: `Set file for change ${params.id}`,
      };
    },
  });

  planTool(pi, planRef, {
    name: "koan_set_change_intent_ref",
    label: "Set code change intent_ref",
    description: "Update change intent reference.",
    parameters: Type.Object({
      id: Type.String(),
      intent_ref: Type.String(),
    }),
    execute: (p, params) => {
      const updated = setChangeIntentRef(p, params.id, params.intent_ref);
      return {
        plan: updated,
        message: `Set intent_ref for change ${params.id}`,
      };
    },
  });
}
