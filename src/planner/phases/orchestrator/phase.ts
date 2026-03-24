// Orchestrator phase: judgment calls at execution boundaries.
// Two step sequences: pre-execution (2 steps) and post-execution (4 steps).
// Orchestrator uses koan_ask_question for all user communication. See docs/state.md -- "No escalated status".

import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";

import { createLogger, type Logger } from "../../../utils/logger.js";
import type { RuntimeContext } from "../../lib/runtime-context.js";
import { EventLog } from "../../lib/audit.js";
import { BasePhase } from "../base-phase.js";
import {
  ORCHESTRATOR_PRE_STEP_NAMES,
  ORCHESTRATOR_POST_STEP_NAMES,
  orchestratorSystemPrompt,
  orchestratorPreStepGuidance,
  orchestratorPostStepGuidance,
} from "./prompts.js";
import type { StepGuidance } from "../../lib/step.js";

const PRE_TOTAL_STEPS = 2;
const POST_TOTAL_STEPS = 4;

export class OrchestratorPhase extends BasePhase {
  protected readonly role = "orchestrator";
  protected readonly totalSteps: number;

  private readonly stepSequence: "pre-execution" | "post-execution";
  private readonly storyId: string | undefined;

  constructor(
    pi: ExtensionAPI,
    config: { epicDir: string; stepSequence: "pre-execution" | "post-execution"; storyId?: string },
    ctx: RuntimeContext,
    log?: Logger,
    eventLog?: EventLog,
  ) {
    super(pi, ctx, log ?? createLogger("OrchestratorPhase"), eventLog);
    this.stepSequence = config.stepSequence;
    this.storyId = config.storyId;
    this.totalSteps = config.stepSequence === "pre-execution" ? PRE_TOTAL_STEPS : POST_TOTAL_STEPS;
  }

  protected getSystemPrompt(): string {
    return orchestratorSystemPrompt(this.stepSequence);
  }

  protected getStepName(step: number): string {
    const names = this.stepSequence === "pre-execution"
      ? ORCHESTRATOR_PRE_STEP_NAMES
      : ORCHESTRATOR_POST_STEP_NAMES;
    return names[step] ?? `Step ${step}`;
  }

  protected getStepGuidance(step: number): StepGuidance {
    return this.stepSequence === "pre-execution"
      ? orchestratorPreStepGuidance(step, this.ctx.epicDir!)
      : orchestratorPostStepGuidance(step, this.ctx.epicDir!, this.storyId);
  }
}
