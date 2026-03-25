// Intake phase: reads conversation, scouts codebase, asks clarifying questions,
// and writes landscape.md — the sole input for all downstream phases.
//
// Five-step linear workflow:
//
//   Step 1 (Extract) — read-only comprehension of conversation.jsonl
//   Step 2 (Scout)   — dispatch codebase scouts, analyze results
//   Step 3 (Ask)     — enumerate knowns/unknowns, ask questions, follow up
//   Step 4 (Reflect) — verify completeness, scout or ask if gaps remain
//   Step 5 (Write)   — write landscape.md, present for user review
//
// Steps progress linearly — no loops. Within-step follow-ups (reading files,
// asking follow-up questions) are handled by the LLM naturally rather than
// by driver-level iteration.
//
// Step 1 is read-only: the permission fence blocks koan_request_scouts,
// koan_ask_question, write, and edit during that step, enforced via
// ctx.currentStep which BasePhase.onStepUpdated() keeps in sync.
//
// Step 5 enforces that koan_review_artifact is called before koan_complete_step
// via validateStepCompletion(). This ensures landscape.md is presented for user
// review before the phase advances.

import * as path from "node:path";
import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";

import { createLogger, type Logger } from "../../../utils/logger.js";
import type { RuntimeContext } from "../../lib/runtime-context.js";
import { EventLog } from "../../lib/audit.js";
import { ReviewablePhase } from "../reviewable-phase.js";
import { INTAKE_STEP_NAMES, intakeSystemPrompt, intakeStepGuidance } from "./prompts.js";
import type { StepGuidance } from "../../lib/step.js";

export class IntakePhase extends ReviewablePhase {
  protected readonly role = "intake";
  protected readonly totalSteps = 5;
  protected readonly reviewGatedStep = 5;
  protected readonly reviewedArtifactName = "landscape.md";

  private readonly conversationPath: string;

  constructor(
    pi: ExtensionAPI,
    ctx: RuntimeContext,
    log?: Logger,
    eventLog?: EventLog,
  ) {
    super(pi, ctx, log ?? createLogger("IntakePhase"), eventLog);
    this.conversationPath = path.join(ctx.epicDir!, "conversation.jsonl");
  }

  protected getSystemPrompt(): string {
    return intakeSystemPrompt();
  }

  protected getStepName(step: number): string {
    return INTAKE_STEP_NAMES[step] ?? `Step ${step}`;
  }

  protected getStepGuidance(step: number): StepGuidance {
    return intakeStepGuidance(step, this.conversationPath, this.ctx.epicDir!, this.ctx.phaseInstructions);
  }

  // Reset the review gate when entering step 5 so only step-5 reviews
  // count toward the validateStepCompletion gate. Without this, a spurious
  // koan_review_artifact call during earlier steps would satisfy the gate
  // before the LLM has written landscape.md.
  protected override onStepUpdated(step: number): void {
    super.onStepUpdated(step);
    if (step === 5) {
      this.resetReviewGate();
    }
  }
}
