// Plan entity tools for structural entities: waves, diagrams, readme entries.
// Uses planTool helper from entity-design (shared load-mutate-save-lock wrapper).

import { Type } from "@sinclair/typebox";
import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";

import type { PlanRef } from "../lib/dispatch.js";
import { planTool } from "./entity-design.js";
import {
  addWave,
  setWaveMilestones,
  addDiagram,
  setDiagram,
  addDiagramNode,
  addDiagramEdge,
  setReadmeEntry,
} from "../plan/mutate/index.js";

export function registerPlanStructureEntityTools(
  pi: ExtensionAPI,
  planRef: PlanRef,
): void {
  // -- Wave --
  planTool(pi, planRef, {
    name: "koan_add_wave",
    label: "Add wave",
    description: "Create wave with milestone list.",
    parameters: Type.Object({
      milestones: Type.Array(Type.String()),
    }),
    execute: (p, params) => {
      const r = addWave(p, params);
      return {
        plan: r.plan,
        message: `Added wave ${r.id} with ${params.milestones.length} milestones`,
      };
    },
  });

  planTool(pi, planRef, {
    name: "koan_set_wave_milestones",
    label: "Set wave milestones",
    description: "Update wave milestones list.",
    parameters: Type.Object({
      id: Type.String(),
      milestones: Type.Array(Type.String()),
    }),
    execute: (p, params) => {
      const updated = setWaveMilestones(p, params.id, params.milestones);
      return {
        plan: updated,
        message: `Set milestones for wave ${params.id}`,
      };
    },
  });

  // -- Diagram --
  planTool(pi, planRef, {
    name: "koan_add_diagram",
    label: "Add diagram",
    description: "Create diagram graph.",
    parameters: Type.Object({
      type: Type.Union([
        Type.Literal("architecture"),
        Type.Literal("state"),
        Type.Literal("sequence"),
        Type.Literal("dataflow"),
      ]),
      scope: Type.String(),
      title: Type.String(),
    }),
    execute: (p, params) => {
      const r = addDiagram(p, params);
      return {
        plan: r.plan,
        message: `Added diagram ${r.id}: "${params.title}"`,
      };
    },
  });

  planTool(pi, planRef, {
    name: "koan_set_diagram",
    label: "Update diagram",
    description: "Update diagram properties.",
    parameters: Type.Object({
      id: Type.String(),
      title: Type.Optional(Type.String()),
      scope: Type.Optional(Type.String()),
      ascii_render: Type.Optional(Type.String()),
    }),
    execute: (p, params) => {
      const updated = setDiagram(p, params.id, params);
      return {
        plan: updated,
        message: `Updated diagram ${params.id}`,
      };
    },
  });

  planTool(pi, planRef, {
    name: "koan_add_diagram_node",
    label: "Add diagram node",
    description: "Add node to diagram.",
    parameters: Type.Object({
      diagram_id: Type.String(),
      id: Type.String(),
      label: Type.String(),
      type: Type.Optional(Type.String()),
    }),
    execute: (p, params) => {
      const updated = addDiagramNode(p, params.diagram_id, params);
      return {
        plan: updated,
        message: `Added node ${params.id} to diagram ${params.diagram_id}`,
      };
    },
  });

  planTool(pi, planRef, {
    name: "koan_add_diagram_edge",
    label: "Add diagram edge",
    description: "Add edge to diagram.",
    parameters: Type.Object({
      diagram_id: Type.String(),
      source: Type.String(),
      target: Type.String(),
      label: Type.String(),
      protocol: Type.Optional(Type.String()),
    }),
    execute: (p, params) => {
      const updated = addDiagramEdge(p, params.diagram_id, params);
      return {
        plan: updated,
        message: `Added edge ${params.source}->${params.target} to diagram ${params.diagram_id}`,
      };
    },
  });

  // -- ReadmeEntry --
  planTool(pi, planRef, {
    name: "koan_set_readme_entry",
    label: "Set readme entry",
    description: "Upsert readme entry by path.",
    parameters: Type.Object({
      path: Type.String(),
      content: Type.String(),
    }),
    execute: (p, params) => {
      const updated = setReadmeEntry(p, params.path, params.content);
      return {
        plan: updated,
        message: `Set readme entry for ${params.path}`,
      };
    },
  });
}
