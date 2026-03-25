// IPC-based tools for workflow phase routing.
//
// koan_propose_workflow — presents phase transition options to the user via
//   file-based IPC. Structurally identical to koan_review_artifact: writes
//   an IPC file, polls for the response, returns the user's text. The
//   orchestrator may call this tool multiple times if the user provides
//   feedback rather than direction. The loop terminates only when the
//   orchestrator commits via koan_set_next_phase.
//
// koan_set_next_phase — commits the phase transition decision. Reads task.json
//   to obtain the list of valid phases, validates the choice, and writes
//   workflow-decision.json for the driver to read after the orchestrator exits.

import { promises as fs } from "node:fs";
import * as path from "node:path";
import * as crypto from "node:crypto";

import { Type, type Static } from "@sinclair/typebox";
import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";

import type { RuntimeContext } from "../lib/runtime-context.js";
import type { ToolResult } from "./types.js";
import {
  ipcFileExists,
  writeIpcFile,
  createWorkflowDecisionRequest,
  pollIpcUntilResponse,
  type WorkflowDecisionIpcFile,
} from "../lib/ipc.js";
import { readTaskFile } from "../lib/task.js";
import type { WorkflowOrchestratorTask } from "../lib/task.js";

// ---------------------------------------------------------------------------
// koan_propose_workflow
// ---------------------------------------------------------------------------

const ProposeWorkflowSchema = Type.Object({
  status_report: Type.String({
    description: "Markdown summary of what was accomplished in the completed phase and why these phases are available next.",
  }),
  recommended_phases: Type.Array(
    Type.Object({
      phase: Type.String({ description: "EpicPhase identifier, e.g. 'core-flows'" }),
      label: Type.String({ description: "Human-readable label, e.g. 'Define Core Flows'" }),
      context: Type.String({ description: "Why this phase is useful right now" }),
      recommended: Type.Optional(Type.Boolean({ description: "True for the most-recommended option" })),
    }),
    { description: "Phase options to present to the user, in recommendation order" },
  ),
});

type ProposeWorkflowParams = Static<typeof ProposeWorkflowSchema>;

const PROPOSE_WORKFLOW_DESCRIPTION = `
Present workflow phase options to the user for direction on what to do next.

After a phase completes, call this tool to show the user:
- A status report of what was accomplished
- Available next phases with context on why each is useful

The user's response (free-form text) is returned. You may call this tool
multiple times if the user provides feedback rather than a clear direction.
Only call koan_set_next_phase once you understand their intent.
`.trim();

export async function executeProposeWorkflow(
  params: ProposeWorkflowParams,
  subagentDir: string | null,
  signal?: AbortSignal | null,
): Promise<ToolResult> {
  if (!subagentDir) {
    return {
      content: [{ type: "text" as const, text: "Error: koan_propose_workflow is only available in subagent context." }],
      details: undefined,
    };
  }

  if (await ipcFileExists(subagentDir)) {
    return {
      content: [{ type: "text" as const, text: "Error: An IPC request is already pending. Wait for it to be resolved before calling again." }],
      details: undefined,
    };
  }

  // Read completedPhase from task.json for UI context.
  let completedPhase = "unknown";
  try {
    const task = await readTaskFile(subagentDir);
    if (task.role === "workflow-orchestrator") {
      completedPhase = (task as WorkflowOrchestratorTask).completedPhase;
    }
  } catch {
    // Non-fatal — completedPhase is for UI context only
  }

  const ipc = createWorkflowDecisionRequest({
    statusReport: params.status_report,
    recommendedPhases: params.recommended_phases,
    completedPhase,
  });
  await writeIpcFile(subagentDir, ipc);

  const { outcome, ipc: answeredIpc } = await pollIpcUntilResponse(subagentDir, ipc, signal);

  switch (outcome) {
    case "answered": {
      const workflowIpc = answeredIpc as WorkflowDecisionIpcFile;
      const feedback = workflowIpc.response?.feedback || "(no response)";
      return {
        content: [{ type: "text" as const, text: `User response:\n\n${feedback}` }],
        details: undefined,
      };
    }
    case "aborted":
      return {
        content: [{ type: "text" as const, text: "The workflow decision was aborted." }],
        details: undefined,
      };
    case "file-gone":
    default:
      return {
        content: [{ type: "text" as const, text: "The workflow decision was cancelled." }],
        details: undefined,
      };
  }
}

// ---------------------------------------------------------------------------
// koan_set_next_phase
// ---------------------------------------------------------------------------

const SetNextPhaseSchema = Type.Object({
  phase: Type.String({
    description: "The EpicPhase identifier to transition to, e.g. 'core-flows'. Must be one of the available phases from your task manifest.",
  }),
  instructions: Type.Optional(Type.String({
    description: "Optional context or focus instructions for the next phase. E.g. 'Focus on auth requirements'. Surfaced to the next phase's LLM in step 1 guidance.",
  })),
});

type SetNextPhaseParams = Static<typeof SetNextPhaseSchema>;

const SET_NEXT_PHASE_DESCRIPTION = `
Commit the next phase transition decision.

Call this after koan_propose_workflow to record which phase to run next.
The phase must be one of the valid successors listed in your task manifest.

Optionally include instructions that will be passed to the next phase's LLM
to guide its focus (e.g. "Focus on authentication requirements and OAuth flows").
`.trim();

export async function executeSetNextPhase(
  params: SetNextPhaseParams,
  subagentDir: string | null,
): Promise<ToolResult> {
  if (!subagentDir) {
    return {
      content: [{ type: "text" as const, text: "Error: koan_set_next_phase is only available in subagent context." }],
      details: undefined,
    };
  }

  // Read availablePhases from task.json (directory-as-contract).
  let availablePhases: string[] = [];
  try {
    const task = await readTaskFile(subagentDir);
    if (task.role === "workflow-orchestrator") {
      availablePhases = (task as WorkflowOrchestratorTask).availablePhases as string[];
    }
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return {
      content: [{ type: "text" as const, text: `Error: Could not read task manifest: ${msg}` }],
      details: undefined,
    };
  }

  if (availablePhases.length === 0) {
    return {
      content: [{ type: "text" as const, text: "Error: No available phases found in task manifest. This is a programming error." }],
      details: undefined,
    };
  }

  if (!availablePhases.includes(params.phase)) {
    return {
      content: [{ type: "text" as const, text:
        `Error: "${params.phase}" is not a valid next phase. ` +
        `Available phases: ${availablePhases.join(", ")}` }],
      details: undefined,
    };
  }

  // Write workflow-decision.json atomically to subagentDir.
  const decision = {
    nextPhase: params.phase,
    ...(params.instructions ? { instructions: params.instructions } : {}),
    decidedAt: new Date().toISOString(),
  };

  const decisionPath = path.join(subagentDir, "workflow-decision.json");
  const tmpPath = path.join(subagentDir, ".workflow-decision.tmp.json");
  await fs.writeFile(tmpPath, `${JSON.stringify(decision, null, 2)}\n`, "utf8");
  await fs.rename(tmpPath, decisionPath);

  const instructionNote = params.instructions
    ? `\n\nInstructions for next phase: "${params.instructions}"`
    : "";

  return {
    content: [{ type: "text" as const, text:
      `Decision committed: transitioning to "${params.phase}".${instructionNote}\n\n` +
      `Call koan_complete_step to finalize the workflow orchestrator session.` }],
    details: undefined,
  };
}

// ---------------------------------------------------------------------------
// Tool registration
// ---------------------------------------------------------------------------

export function registerWorkflowDecisionTools(pi: ExtensionAPI, ctx: RuntimeContext): void {
  pi.registerTool({
    name: "koan_propose_workflow",
    label: "Propose workflow",
    description: PROPOSE_WORKFLOW_DESCRIPTION,
    parameters: ProposeWorkflowSchema,
    async execute(_toolCallId, params, signal) {
      return executeProposeWorkflow(params as ProposeWorkflowParams, ctx.subagentDir, signal);
    },
  });

  pi.registerTool({
    name: "koan_set_next_phase",
    label: "Set next phase",
    description: SET_NEXT_PHASE_DESCRIPTION,
    parameters: SetNextPhaseSchema,
    async execute(_toolCallId, params) {
      return executeSetNextPhase(params as SetNextPhaseParams, ctx.subagentDir);
    },
  });
}
