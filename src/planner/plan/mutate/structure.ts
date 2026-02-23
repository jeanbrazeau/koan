// Structural plan mutations: waves, diagrams, readme entries.
// Pure functions -- input plan in, new plan out. No side effects.

import type {
  Plan,
  Wave,
  DiagramGraph,
  DiagramNode,
  DiagramEdge,
  ReadmeEntry,
} from "../types.js";
import { nextWaveId, nextDiagramId } from "../types.js";

// -- Wave --

export function addWave(
  p: Plan,
  data: { milestones: string[] },
): { plan: Plan; id: string } {
  const id = nextWaveId(p);
  const wave: Wave = {
    id,
    milestones: data.milestones,
  };
  return {
    plan: {
      ...p,
      waves: [...p.waves, wave],
    },
    id,
  };
}

export function setWaveMilestones(
  p: Plan,
  id: string,
  milestones: string[],
): Plan {
  const idx = p.waves.findIndex((w) => w.id === id);
  if (idx === -1) throw new Error(`wave ${id} not found`);

  const updated = [...p.waves];
  updated[idx] = { ...p.waves[idx], milestones };

  return { ...p, waves: updated };
}

// -- Diagram --

export function addDiagram(
  p: Plan,
  data: {
    type: "architecture" | "state" | "sequence" | "dataflow";
    scope: string;
    title: string;
  },
): { plan: Plan; id: string } {
  const id = nextDiagramId(p);
  const diagram: DiagramGraph = {
    id,
    type: data.type,
    scope: data.scope,
    title: data.title,
    nodes: [],
    edges: [],
    ascii_render: null,
  };
  return {
    plan: {
      ...p,
      diagram_graphs: [...p.diagram_graphs, diagram],
    },
    id,
  };
}

export function setDiagram(
  p: Plan,
  id: string,
  data: { title?: string; scope?: string; ascii_render?: string },
): Plan {
  const idx = p.diagram_graphs.findIndex((d) => d.id === id);
  if (idx === -1) throw new Error(`diagram ${id} not found`);

  const d = p.diagram_graphs[idx];
  const updated: DiagramGraph = {
    ...d,
    title: data.title ?? d.title,
    scope: data.scope ?? d.scope,
    ascii_render: data.ascii_render ?? d.ascii_render,
  };

  const diagrams = [...p.diagram_graphs];
  diagrams[idx] = updated;

  return { ...p, diagram_graphs: diagrams };
}

export function addDiagramNode(
  p: Plan,
  diagramId: string,
  data: { id: string; label: string; type?: string },
): Plan {
  const idx = p.diagram_graphs.findIndex((d) => d.id === diagramId);
  if (idx === -1) throw new Error(`diagram ${diagramId} not found`);

  const d = p.diagram_graphs[idx];
  const node: DiagramNode = {
    id: data.id,
    label: data.label,
    type: data.type ?? null,
  };

  const diagrams = [...p.diagram_graphs];
  diagrams[idx] = {
    ...d,
    nodes: [...d.nodes, node],
  };

  return { ...p, diagram_graphs: diagrams };
}

export function addDiagramEdge(
  p: Plan,
  diagramId: string,
  data: { source: string; target: string; label: string; protocol?: string },
): Plan {
  const idx = p.diagram_graphs.findIndex((d) => d.id === diagramId);
  if (idx === -1) throw new Error(`diagram ${diagramId} not found`);

  const d = p.diagram_graphs[idx];
  const edge: DiagramEdge = {
    source: data.source,
    target: data.target,
    label: data.label,
    protocol: data.protocol ?? null,
  };

  const diagrams = [...p.diagram_graphs];
  diagrams[idx] = {
    ...d,
    edges: [...d.edges, edge],
  };

  return { ...p, diagram_graphs: diagrams };
}

// -- ReadmeEntry --

export function setReadmeEntry(p: Plan, path: string, content: string): Plan {
  const idx = p.readme_entries.findIndex((r) => r.path === path);
  const entry: ReadmeEntry = { path, content };

  if (idx === -1) {
    return {
      ...p,
      readme_entries: [...p.readme_entries, entry],
    };
  }

  const entries = [...p.readme_entries];
  entries[idx] = entry;
  return { ...p, readme_entries: entries };
}
