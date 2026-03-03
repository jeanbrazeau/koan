// Plan entity tools for design-phase entities: decisions, risks, milestones.
// Exports planTool helper for shared use by entity-code and entity-structure.
// load-mutate-save wrapped in file lock; disk is single source of truth.

import { Type, type Static, type TSchema } from "@sinclair/typebox";
import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import * as path from "node:path";

import type { PlanRef } from "../lib/dispatch.js";
import { loadPlan, savePlan } from "../plan/serialize.js";
import type { Plan } from "../plan/types.js";
import { withFileLock } from "../../utils/lock.js";
import {
  addDecision,
  setDecision,
  addRejectedAlternative,
  setRejectedAlternative,
  addRisk,
  setRisk,
  addMilestone,
  setMilestoneName,
  setMilestoneFiles,
  setMilestoneFlags,
  setMilestoneRequirements,
  setMilestoneAcceptanceCriteria,
  setMilestoneTests,
} from "../plan/mutate/index.js";

export function planTool<TParams extends TSchema>(
  pi: ExtensionAPI,
  planRef: PlanRef,
  opts: {
    name: string;
    label: string;
    description: string;
    parameters: TParams;
    execute: (plan: Plan, params: Static<TParams>) => { plan: Plan; message: string };
  },
): void {
  pi.registerTool({
    name: opts.name,
    label: opts.label,
    description: opts.description,
    parameters: opts.parameters,
    async execute(_toolCallId, params) {
      if (!planRef.dir) throw new Error("No plan directory is active.");
      const planPath = path.join(planRef.dir, "plan.json");
      return withFileLock(planPath, async () => {
        const plan = await loadPlan(planRef.dir!);
        const result = opts.execute(plan, params);
        await savePlan(result.plan, planRef.dir!);
        return {
          content: [{ type: "text" as const, text: result.message }],
          details: undefined,
        };
      });
    },
  });
}

export function registerPlanDesignEntityTools(
  pi: ExtensionAPI,
  planRef: PlanRef,
): void {
  // -- Decision --
  planTool(pi, planRef, {
    name: "koan_add_decision",
    label: "Add decision",
    description: "Add decision to decision log. Source identifies where authority came from (e.g. code:src/foo.ts, docs:CLAUDE.md, user:ask, user:conversation, inference).",
    parameters: Type.Object({
      decision: Type.String(),
      reasoning: Type.String(),
      source: Type.String({ description: "Provenance: code:<path>, docs:<path>, user:ask, user:conversation, or inference" }),
    }),
    execute: (p, params) => {
      const r = addDecision(p, params);
      return {
        plan: r.plan,
        message: `Added decision ${r.id}: "${params.decision}" [source: ${params.source}]`,
      };
    },
  });

  planTool(pi, planRef, {
    name: "koan_set_decision",
    label: "Update decision",
    description: "Update existing decision by ID. Omitting source preserves the existing value.",
    parameters: Type.Object({
      id: Type.String(),
      decision: Type.Optional(Type.String()),
      reasoning: Type.Optional(Type.String()),
      source: Type.Optional(Type.String({ description: "Provenance: code:<path>, docs:<path>, user:ask, user:conversation, or inference" })),
    }),
    execute: (p, params) => {
      const updated = setDecision(p, params.id, params);
      return {
        plan: updated,
        message: `Updated decision ${params.id}`,
      };
    },
  });

  // -- RejectedAlternative --
  planTool(pi, planRef, {
    name: "koan_add_rejected_alternative",
    label: "Add rejected alternative",
    description: "Add rejected alternative to decision log.",
    parameters: Type.Object({
      alternative: Type.String(),
      rejection_reason: Type.String(),
      decision_ref: Type.String(),
    }),
    execute: (p, params) => {
      const r = addRejectedAlternative(p, params);
      return {
        plan: r.plan,
        message: `Added rejected alternative ${r.id}`,
      };
    },
  });

  planTool(pi, planRef, {
    name: "koan_set_rejected_alternative",
    label: "Update rejected alternative",
    description: "Update existing rejected alternative by ID.",
    parameters: Type.Object({
      id: Type.String(),
      alternative: Type.Optional(Type.String()),
      rejection_reason: Type.Optional(Type.String()),
      decision_ref: Type.Optional(Type.String()),
    }),
    execute: (p, params) => {
      const updated = setRejectedAlternative(p, params.id, params);
      return {
        plan: updated,
        message: `Updated rejected alternative ${params.id}`,
      };
    },
  });

  // -- Risk --
  planTool(pi, planRef, {
    name: "koan_add_risk",
    label: "Add risk",
    description: "Add risk to known risks.",
    parameters: Type.Object({
      risk: Type.String(),
      mitigation: Type.String(),
      anchor: Type.Optional(Type.String()),
      decision_ref: Type.Optional(Type.String()),
    }),
    execute: (p, params) => {
      const r = addRisk(p, params);
      return {
        plan: r.plan,
        message: `Added risk ${r.id}: "${params.risk}"`,
      };
    },
  });

  planTool(pi, planRef, {
    name: "koan_set_risk",
    label: "Update risk",
    description: "Update existing risk by ID.",
    parameters: Type.Object({
      id: Type.String(),
      risk: Type.Optional(Type.String()),
      mitigation: Type.Optional(Type.String()),
      anchor: Type.Optional(Type.String()),
      decision_ref: Type.Optional(Type.String()),
    }),
    execute: (p, params) => {
      const updated = setRisk(p, params.id, params);
      return {
        plan: updated,
        message: `Updated risk ${params.id}`,
      };
    },
  });

  // -- Milestone --
  planTool(pi, planRef, {
    name: "koan_add_milestone",
    label: "Add milestone",
    description: "Create new milestone.",
    parameters: Type.Object({
      name: Type.String(),
      files: Type.Optional(Type.Array(Type.String())),
      flags: Type.Optional(Type.Array(Type.String())),
      requirements: Type.Optional(Type.Array(Type.String())),
      acceptance_criteria: Type.Optional(Type.Array(Type.String())),
      tests: Type.Optional(Type.Array(Type.String())),
    }),
    execute: (p, params) => {
      const r = addMilestone(p, params);
      return {
        plan: r.plan,
        message: `Added milestone ${r.id}: "${params.name}"`,
      };
    },
  });

  planTool(pi, planRef, {
    name: "koan_set_milestone_name",
    label: "Set milestone name",
    description: "Update milestone name.",
    parameters: Type.Object({
      id: Type.String(),
      name: Type.String(),
    }),
    execute: (p, params) => {
      const updated = setMilestoneName(p, params.id, params.name);
      return {
        plan: updated,
        message: `Set name for milestone ${params.id}`,
      };
    },
  });

  planTool(pi, planRef, {
    name: "koan_set_milestone_files",
    label: "Set milestone files",
    description: "Update milestone files list.",
    parameters: Type.Object({
      id: Type.String(),
      files: Type.Array(Type.String()),
    }),
    execute: (p, params) => {
      const updated = setMilestoneFiles(p, params.id, params.files);
      return {
        plan: updated,
        message: `Set files for milestone ${params.id} (${params.files.length} files)`,
      };
    },
  });

  planTool(pi, planRef, {
    name: "koan_set_milestone_flags",
    label: "Set milestone flags",
    description: "Update milestone flags list.",
    parameters: Type.Object({
      id: Type.String(),
      flags: Type.Array(Type.String()),
    }),
    execute: (p, params) => {
      const updated = setMilestoneFlags(p, params.id, params.flags);
      return {
        plan: updated,
        message: `Set flags for milestone ${params.id}`,
      };
    },
  });

  planTool(pi, planRef, {
    name: "koan_set_milestone_requirements",
    label: "Set milestone requirements",
    description: "Update milestone requirements list.",
    parameters: Type.Object({
      id: Type.String(),
      requirements: Type.Array(Type.String()),
    }),
    execute: (p, params) => {
      const updated = setMilestoneRequirements(p, params.id, params.requirements);
      return {
        plan: updated,
        message: `Set requirements for milestone ${params.id} (${params.requirements.length} items)`,
      };
    },
  });

  planTool(pi, planRef, {
    name: "koan_set_milestone_acceptance_criteria",
    label: "Set milestone acceptance criteria",
    description: "Update milestone acceptance criteria list.",
    parameters: Type.Object({
      id: Type.String(),
      acceptance_criteria: Type.Array(Type.String()),
    }),
    execute: (p, params) => {
      const updated = setMilestoneAcceptanceCriteria(
        p,
        params.id,
        params.acceptance_criteria,
      );
      return {
        plan: updated,
        message: `Set acceptance criteria for milestone ${params.id} (${params.acceptance_criteria.length} items)`,
      };
    },
  });

  planTool(pi, planRef, {
    name: "koan_set_milestone_tests",
    label: "Set milestone tests",
    description: "Update milestone tests list.",
    parameters: Type.Object({
      id: Type.String(),
      tests: Type.Array(Type.String()),
    }),
    execute: (p, params) => {
      const updated = setMilestoneTests(p, params.id, params.tests);
      return {
        plan: updated,
        message: `Set tests for milestone ${params.id} (${params.tests.length} tests)`,
      };
    },
  });
}
