// Executor phase: implements a story plan.
// Two steps: comprehension → implementation.

import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";

import { createLogger, type Logger } from "../../../utils/logger.js";
import type { RuntimeContext } from "../../lib/runtime-context.js";
import { EventLog } from "../../lib/audit.js";
import { BasePhase } from "../base-phase.js";
import { EXECUTOR_STEP_NAMES, executorSystemPrompt, executorStepGuidance } from "./prompts.js";
import type { StepGuidance } from "../../lib/step.js";

export class ExecutorPhase extends BasePhase {
  protected readonly role = "executor";
  protected readonly totalSteps = 2;

  private readonly storyId: string;
  private readonly retryContext: string | undefined;

  constructor(
    pi: ExtensionAPI,
    config: { epicDir: string; storyId: string; retryContext?: string },
    ctx: RuntimeContext,
    log?: Logger,
    eventLog?: EventLog,
  ) {
    super(pi, ctx, log ?? createLogger("ExecutorPhase"), eventLog);
    this.storyId = config.storyId;
    this.retryContext = config.retryContext;
  }

  protected getSystemPrompt(): string {
    return executorSystemPrompt();
  }

  protected getStepName(step: number): string {
    return EXECUTOR_STEP_NAMES[step] ?? `Step ${step}`;
  }

  protected getStepGuidance(step: number): StepGuidance {
    return executorStepGuidance(step, this.storyId, this.retryContext);
  }
}
