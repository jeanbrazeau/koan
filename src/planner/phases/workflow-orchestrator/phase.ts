// WorkflowOrchestratorPhase: evaluates completed phase context and guides the
// user in choosing the next phase via a multi-turn conversation.
//
// Two-step workflow:
//   Step 1 (Evaluate)  — read workflow-status.md and artifacts, build mental model
//   Step 2 (Propose)   — call koan_propose_workflow, address feedback, commit via koan_set_next_phase
//
// Step 2 validation gate blocks koan_complete_step unless both
// koan_propose_workflow and koan_set_next_phase have been called successfully.
// This ensures:
//   - The orchestrator cannot silently commit a transition without presenting
//     options to the user (proposalMade gate)
//   - The orchestrator cannot exit without committing a decision (nextPhaseSet gate)
//
// Uses event.isError (not event.error) matching ReviewablePhase convention.

import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";

import { createLogger, type Logger } from "../../../utils/logger.js";
import type { RuntimeContext } from "../../lib/runtime-context.js";
import { EventLog } from "../../lib/audit.js";
import { BasePhase } from "../base-phase.js";
import {
  WORKFLOW_ORCHESTRATOR_STEP_NAMES,
  workflowOrchestratorSystemPrompt,
  workflowOrchestratorStepGuidance,
} from "./prompts.js";
import type { StepGuidance } from "../../lib/step.js";
import type { EpicPhase } from "../../types.js";

/** Config extracted from WorkflowOrchestratorTask by dispatch.ts.
 *  Keeps the constructor signature clean and type-safe. */
export interface WorkflowOrchestratorConfig {
  completedPhase: EpicPhase;
  availablePhases: readonly EpicPhase[];
}

export class WorkflowOrchestratorPhase extends BasePhase {
  protected readonly role = "workflow-orchestrator";
  protected readonly totalSteps = 2;

  private readonly completedPhase: EpicPhase;
  private readonly availablePhases: readonly EpicPhase[];

  // Validation gates for step 2.
  // Both must be true before koan_complete_step advances past step 2.
  private proposalMade = false;
  private nextPhaseSet = false;

  constructor(
    pi: ExtensionAPI,
    config: WorkflowOrchestratorConfig,
    ctx: RuntimeContext,
    log?: Logger,
    eventLog?: EventLog,
  ) {
    super(pi, ctx, log ?? createLogger("WorkflowOrchestratorPhase"), eventLog);
    this.completedPhase = config.completedPhase;
    this.availablePhases = config.availablePhases;

    // Track successful tool calls to enforce step 2 validation gate.
    // event.isError matches ReviewablePhase convention — not event.error.
    pi.on("tool_result", (event) => {
      if (event.toolName === "koan_propose_workflow" && !event.isError) {
        this.proposalMade = true;
      }
      if (event.toolName === "koan_set_next_phase" && !event.isError) {
        this.nextPhaseSet = true;
      }
      return undefined;
    });
  }

  protected getSystemPrompt(): string {
    return workflowOrchestratorSystemPrompt();
  }

  protected getStepName(step: number): string {
    return WORKFLOW_ORCHESTRATOR_STEP_NAMES[step] ?? `Step ${step}`;
  }

  protected getStepGuidance(step: number): StepGuidance {
    return workflowOrchestratorStepGuidance(
      step,
      this.ctx.epicDir!,
      this.availablePhases,
    );
  }

  protected async validateStepCompletion(step: number): Promise<string | null> {
    if (step === 2 && !this.proposalMade) {
      return (
        "You must call koan_propose_workflow to present options to the user " +
        "before committing a phase transition. " +
        "Call koan_propose_workflow first, then koan_set_next_phase."
      );
    }
    if (step === 2 && !this.nextPhaseSet) {
      return (
        "You must call koan_set_next_phase before completing this step. " +
        "Call koan_propose_workflow again if you still need user input, " +
        "then commit the decision with koan_set_next_phase."
      );
    }
    return super.validateStepCompletion(step);
  }
}
