// BasePhase: shared lifecycle for all six koan subagent roles.
// Subclasses define only their step structure and system prompt.
// Eliminates ~40 lines of duplicated skeleton per phase.
//
// Lifecycle:
//   constructor → registerHandlers() (hooks event listeners)
//   begin()     → activates phase, sets onCompleteStep in ctx, emits phase_start
//   handleStepComplete() → advances step counter, returns next prompt or null

import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";

import { createLogger, type Logger } from "../../utils/logger.js";
import { checkPermission } from "../lib/permissions.js";
import { formatStep, type StepGuidance } from "../lib/step.js";
import { EventLog } from "../lib/audit.js";
import type { RuntimeContext } from "../lib/runtime-context.js";

export abstract class BasePhase {
  // Subclasses declare these as readonly properties.
  protected abstract readonly role: string;
  protected abstract readonly totalSteps: number;

  // Subclasses implement these to define step content.
  protected abstract getSystemPrompt(): string;
  protected abstract getStepName(step: number): string;
  protected abstract getStepGuidance(step: number): StepGuidance;

  private step = 1;
  private active = false;
  private step1Prompt: string | null = null;

  protected readonly log: Logger;

  constructor(
    protected readonly pi: ExtensionAPI,
    protected readonly ctx: RuntimeContext,
    log?: Logger,
    protected readonly eventLog?: EventLog,
  ) {
    this.log = log ?? createLogger("Phase");
    this.registerHandlers();
  }

  // -- Event handler registration --

  private registerHandlers(): void {
    // before_agent_start: inject system prompt when this phase is active.
    this.pi.on("before_agent_start", () => {
      if (!this.active) return undefined;
      return { systemPrompt: this.getSystemPrompt() };
    });

    // context: append step 1 guidance to the spawn prompt (§9.8 append pattern).
    // Preserves context embedded by the spawn function (scout question, retry
    // context, etc.) while adding structured step instructions after a separator.
    this.pi.on("context", (event) => {
      if (!this.active || this.step !== 1 || !this.step1Prompt) return undefined;
      const messages = event.messages.map((m) => {
        if (m.role !== "user") return m;
        const existing = typeof m.content === "string" ? m.content.trim() : "";
        const combined = existing.length > 0
          ? `${existing}\n\n---\n\n${this.step1Prompt!}`
          : this.step1Prompt!;
        return { ...m, content: combined };
      });
      return { messages };
    });

    // tool_call: default-deny permission check for every tool call.
    this.pi.on("tool_call", (event) => {
      if (!this.active) return undefined;
      const perm = checkPermission(
        this.role,
        event.toolName,
        this.ctx.epicDir ?? undefined,
        event.input as Record<string, unknown>,
      );
      if (!perm.allowed) {
        return { block: true, reason: perm.reason };
      }
      return undefined;
    });
  }

  // -- Public lifecycle --

  async begin(): Promise<void> {
    this.step1Prompt = formatStep(this.getStepGuidance(1));
    this.active = true;
    this.step = 1;

    if (this.ctx.onCompleteStep !== null) {
      throw new Error(`ctx.onCompleteStep is already occupied — cannot begin ${this.role} phase`);
    }
    this.ctx.onCompleteStep = (thoughts: string) => this.handleStepComplete(thoughts);

    this.log("Starting phase", { role: this.role, step: 1, totalSteps: this.totalSteps });
    await this.eventLog?.emitPhaseStart(this.totalSteps);
    await this.eventLog?.emitStepTransition(1, this.getStepName(1), this.totalSteps);
  }

  // -- Private step progression --

  private async handleStepComplete(thoughts: string): Promise<string | null> {
    void thoughts; // captured in event log via tool_result; used by subclass prompts if needed
    const prev = this.step;

    if (prev === this.totalSteps) {
      // Phase complete.
      this.active = false;
      this.ctx.onCompleteStep = null;
      await this.eventLog?.emitPhaseEnd("completed");
      this.log("Phase complete", { role: this.role });
      return null;
    }

    // Advance to next step.
    this.step = prev + 1;
    const prompt = formatStep(this.getStepGuidance(this.step));
    await this.eventLog?.emitStepTransition(this.step, this.getStepName(this.step), this.totalSteps);
    this.log("Step transition", { role: this.role, from: prev, to: this.step });
    return prompt;
  }
}
