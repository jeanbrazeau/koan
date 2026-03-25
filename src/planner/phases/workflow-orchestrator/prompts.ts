// Workflow orchestrator prompts — system prompt and step guidance.
//
// Two-step workflow following the single-cognitive-goal principle:
//   Step 1 (Evaluate)  — read workflow-status.md and phase artifacts; build mental model
//   Step 2 (Propose)   — call koan_propose_workflow, handle feedback, commit via koan_set_next_phase
//
// availablePhases is injected into step 2 guidance from the task manifest so
// the orchestrator only proposes valid DAG transitions.

import type { StepGuidance } from "../../lib/step.js";
import type { EpicPhase } from "../../types.js";
import { PHASE_DESCRIPTIONS } from "../../lib/phase-dag.js";

export const WORKFLOW_ORCHESTRATOR_STEP_NAMES: Record<number, string> = {
  1: "Evaluate",
  2: "Propose",
};

export function workflowOrchestratorSystemPrompt(): string {
  return `You are a workflow orchestrator for a coding task planning pipeline. Your role is to evaluate what has been accomplished and guide the user in choosing what to do next.

## Your responsibilities

1. Read available context (workflow-status.md and any phase artifacts)
2. Understand what was accomplished and what options are available
3. Present a clear status report and phase options to the user
4. Hold a conversation until the user's intent is clear
5. Commit the next phase decision via koan_set_next_phase

## Communication style

- Be concise and direct
- Focus on what matters to the user's goal
- When the user's direction is clear, commit it — don't over-clarify
- Present phase options with helpful context, not technical jargon

## Constraints

- You must call koan_propose_workflow before koan_set_next_phase
- You may call koan_propose_workflow multiple times if the user needs more clarification
- The phase you commit must be in your available phases list`;
}

export function workflowOrchestratorStepGuidance(
  step: number,
  epicDir: string,
  availablePhases: readonly EpicPhase[],
): StepGuidance {
  switch (step) {
    case 1:
      return {
        title: WORKFLOW_ORCHESTRATOR_STEP_NAMES[1],
        instructions: [
          `Read \`${epicDir}/workflow-status.md\` to understand:`,
          "",
          "- Which phase just completed",
          "- What artifacts are available",
          "- Which phases are available next",
          "",
          "Then read any relevant artifacts (landscape.md, brief.md, etc.) to",
          "build a thorough understanding of what has been accomplished and what",
          "the user's goal is.",
          "",
          "Do NOT call koan_propose_workflow yet. Comprehend the current state first.",
        ],
      };

    case 2: {
      const phaseList = availablePhases.map((p) =>
        `- **${p}**: ${PHASE_DESCRIPTIONS[p]}`,
      );
      return {
        title: WORKFLOW_ORCHESTRATOR_STEP_NAMES[2],
        instructions: [
          "Call koan_propose_workflow with:",
          "",
          "1. A **status_report** (markdown) summarizing what was accomplished",
          "   and why the available phases make sense right now",
          "",
          "2. **recommended_phases** — the available next phases (in order of",
          "   recommendation):",
          "",
          ...phaseList,
          "",
          "The user will respond with their direction. If their response is clear,",
          "call koan_set_next_phase to commit the decision (with optional instructions",
          "to focus the next phase). If their response needs clarification, call",
          "koan_propose_workflow again with an updated status report.",
          "",
          "You MUST call both koan_propose_workflow and koan_set_next_phase before",
          "completing this step.",
        ],
      };
    }

    default:
      return {
        title: `Step ${step}`,
        instructions: [`Execute step ${step}.`],
      };
  }
}
