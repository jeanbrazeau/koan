// Scout phase: answers one narrow codebase question and writes findings.
// Single-step, cheap model, no user interaction.

import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";

import { createLogger, type Logger } from "../../../utils/logger.js";
import type { RuntimeContext } from "../../lib/runtime-context.js";
import { EventLog } from "../../lib/audit.js";
import { BasePhase } from "../base-phase.js";
import { SCOUT_STEP_NAMES, scoutSystemPrompt, scoutStepGuidance } from "./prompts.js";
import type { StepGuidance } from "../../lib/step.js";

export class ScoutPhase extends BasePhase {
  protected readonly role = "scout";
  protected readonly totalSteps = 1;

  constructor(
    pi: ExtensionAPI,
    config: { epicDir: string },
    ctx: RuntimeContext,
    log?: Logger,
    eventLog?: EventLog,
  ) {
    super(pi, ctx, log ?? createLogger("ScoutPhase"), eventLog);
    void config; // epicDir used via ctx.epicDir for permission scoping
  }

  protected getSystemPrompt(): string {
    return scoutSystemPrompt();
  }

  protected getStepName(step: number): string {
    return SCOUT_STEP_NAMES[step] ?? `Step ${step}`;
  }

  protected getStepGuidance(_step: number): StepGuidance {
    return scoutStepGuidance();
  }
}
