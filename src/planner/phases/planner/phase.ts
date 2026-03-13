// Planner phase: produces the detail plan for a single story.
// Three steps: analysis → plan → verification design.

import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";

import { createLogger, type Logger } from "../../../utils/logger.js";
import type { RuntimeContext } from "../../lib/runtime-context.js";
import { EventLog } from "../../lib/audit.js";
import { BasePhase } from "../base-phase.js";
import { PLANNER_STEP_NAMES, plannerSystemPrompt, plannerStepGuidance } from "./prompts.js";
import type { StepGuidance } from "../../lib/step.js";

export class PlannerPhase extends BasePhase {
  protected readonly role = "planner";
  protected readonly totalSteps = 3;

  private readonly storyId: string;

  constructor(
    pi: ExtensionAPI,
    config: { epicDir: string; storyId: string },
    ctx: RuntimeContext,
    log?: Logger,
    eventLog?: EventLog,
  ) {
    super(pi, ctx, log ?? createLogger("PlannerPhase"), eventLog);
    this.storyId = config.storyId;
  }

  protected getSystemPrompt(): string {
    return plannerSystemPrompt();
  }

  protected getStepName(step: number): string {
    return PLANNER_STEP_NAMES[step] ?? `Step ${step}`;
  }

  protected getStepGuidance(step: number): StepGuidance {
    return plannerStepGuidance(step, this.storyId);
  }
}
