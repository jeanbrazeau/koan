// Brief-writer phase: reads intake context and produces brief.md.
// Three-step workflow with a review gate:
//
//   Step 1 (Read)          -- comprehend landscape.md; no file writes
//   Step 2 (Draft & Review) -- write brief.md, invoke koan_review_artifact;
//                             revise on feedback; advance only after acceptance
//   Step 3 (Finalize)      -- phase complete
//
// Step 2 is the review gate. Extends ReviewablePhase which provides the
// review-tracking state and listeners. validateStepCompletion() is inherited --
// koan_complete_step is rejected unless the last review response was ACCEPTED.

import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";

import { createLogger, type Logger } from "../../../utils/logger.js";
import type { RuntimeContext } from "../../lib/runtime-context.js";
import { EventLog } from "../../lib/audit.js";
import { ReviewablePhase } from "../reviewable-phase.js";
import { BRIEF_WRITER_STEP_NAMES, briefWriterSystemPrompt, briefWriterStepGuidance } from "./prompts.js";
import type { StepGuidance } from "../../lib/step.js";

export class BriefWriterPhase extends ReviewablePhase {
  protected readonly role = "brief-writer";
  protected readonly totalSteps = 3;
  protected readonly reviewGatedStep = 2;
  protected readonly reviewedArtifactName = "brief.md";

  constructor(
    pi: ExtensionAPI,
    ctx: RuntimeContext,
    log?: Logger,
    eventLog?: EventLog,
  ) {
    super(pi, ctx, log ?? createLogger("BriefWriterPhase"), eventLog);
  }

  protected getSystemPrompt(): string {
    return briefWriterSystemPrompt();
  }

  protected getStepName(step: number): string {
    return BRIEF_WRITER_STEP_NAMES[step] ?? `Step ${step}`;
  }

  protected getStepGuidance(step: number): StepGuidance {
    return briefWriterStepGuidance(step, this.ctx.epicDir!, this.ctx.phaseInstructions);
  }

}
