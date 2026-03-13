// Intake phase: reads conversation, extracts context, requests scouts,
// identifies gaps, asks user questions, writes context.md and decisions.md.
// Three-step sequence per §11.2.2.

import * as path from "node:path";
import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";

import { createLogger, type Logger } from "../../../utils/logger.js";
import type { RuntimeContext } from "../../lib/runtime-context.js";
import { EventLog } from "../../lib/audit.js";
import { BasePhase } from "../base-phase.js";
import { INTAKE_STEP_NAMES, intakeSystemPrompt, intakeStepGuidance } from "./prompts.js";
import type { StepGuidance } from "../../lib/step.js";

export class IntakePhase extends BasePhase {
  protected readonly role = "intake";
  protected readonly totalSteps = 3;

  private readonly conversationPath: string;

  constructor(
    pi: ExtensionAPI,
    config: { epicDir: string },
    ctx: RuntimeContext,
    log?: Logger,
    eventLog?: EventLog,
  ) {
    super(pi, ctx, log ?? createLogger("IntakePhase"), eventLog);
    this.conversationPath = path.join(config.epicDir, "conversation.jsonl");
  }

  protected getSystemPrompt(): string {
    return intakeSystemPrompt();
  }

  protected getStepName(step: number): string {
    return INTAKE_STEP_NAMES[step] ?? `Step ${step}`;
  }

  protected getStepGuidance(step: number): StepGuidance {
    return intakeStepGuidance(step, this.conversationPath);
  }
}
