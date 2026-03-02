// Plan-design fix phase -- dynamic N-step targeted repair for QR failures.
//
// totalSteps = 2 + failures.length. Step 1 reads all failures (read-only).
// Steps 2..N+1 each fix one QR item (mutations enabled). Step N+2 reviews
// all fixes (read-only). The step counter IS the item iterator:
// failures[step - 2] gives the current item.
//
// Separate class from PlanDesignPhase because the workflows diverge:
// initial = 6 steps of exploration then writing (mutations at step 6);
// fix = dynamic N steps iterating one QR item per step (mutations in
// per-item range only). Conditional branching at every method boundary
// produces worse code than two focused classes.
//
// The fix architect receives QR failures as XML in step 1. Per-item steps
// present a single failure with mutation tools enabled. The session
// orchestrator decides whether to re-run QR -- the fix phase does not
// know about iterations or severity escalation.

import * as path from "node:path";

import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";

import { loadAndValidatePlan } from "../../plan/validate.js";
import {
  loadPlanDesignSystemPrompt,
  buildPlanDesignSystemPrompt,
} from "./prompts.js";
import {
  fixStepName,
  buildFixSystemPrompt,
  fixStepGuidance,
  formatFailuresXml,
} from "./fix-prompts.js";
import { formatStep } from "../../lib/step.js";
import type { QRItem } from "../../qr/types.js";
import { createLogger, type Logger } from "../../../utils/logger.js";
import { EventLog } from "../../lib/audit.js";
import { hookDispatch, unhookDispatch, type WorkflowDispatch, type PlanRef } from "../../lib/dispatch.js";
import { checkPermission, PLAN_MUTATION_TOOLS } from "../../lib/permissions.js";

interface FixPhaseState {
  active: boolean;
  step: number;
  step1Prompt: string | null;
  systemPrompt: string | null;
}

export class PlanDesignFixPhase {
  private readonly pi: ExtensionAPI;
  private readonly planDir: string;
  private readonly failures: ReadonlyArray<QRItem>;
  private readonly log: Logger;
  private readonly state: FixPhaseState;
  private readonly eventLog: EventLog | undefined;
  private readonly dispatch: WorkflowDispatch;
  private readonly planRef: PlanRef;

  constructor(
    pi: ExtensionAPI,
    config: { planDir: string; failures: QRItem[] },
    dispatch: WorkflowDispatch,
    planRef: PlanRef,
    log?: Logger,
    eventLog?: EventLog,
  ) {
    this.pi = pi;
    this.planDir = config.planDir;
    this.failures = config.failures;
    this.dispatch = dispatch;
    this.planRef = planRef;
    this.log = log ?? createLogger("PlanDesignFix");
    this.eventLog = eventLog;

    this.state = {
      active: false,
      step: 1,
      step1Prompt: null,
      systemPrompt: null,
    };

    this.registerHandlers();
  }

  // Computed from failure count. Step 1 (understand) + N per-item steps
  // + 1 final review = 2 + N. Single source of truth for all step-range
  // checks in this class.
  private get totalSteps(): number {
    return 2 + this.failures.length;
  }

  async begin(): Promise<void> {
    let basePrompt: string;
    try {
      basePrompt = await loadPlanDesignSystemPrompt();
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      this.log("Fix phase aborted: cannot load system prompt", { error: message });
      return;
    }

    const failuresXml = formatFailuresXml(this.failures);
    // Local copy for consistent reads across this method. The getter is stable
    // (this.failures is readonly) but a local communicates "one value, many uses".
    const totalSteps = this.totalSteps;
    this.state.systemPrompt = buildFixSystemPrompt(
      buildPlanDesignSystemPrompt(basePrompt),
      this.failures.length,
      totalSteps,
    );
    const conversationPath = path.join(this.planDir, "conversation.jsonl");
    this.state.step1Prompt = formatStep(
      fixStepGuidance(1, totalSteps, { allFailuresXml: failuresXml, conversationPath }),
    );
    this.state.active = true;
    this.state.step = 1;

    hookDispatch(this.dispatch, "onCompleteStep", () => this.handleStepComplete());

    this.log("Starting plan-design fix workflow", {
      step: 1,
      totalSteps,
      failureCount: this.failures.length,
    });
    await this.eventLog?.emitPhaseStart(totalSteps);
    await this.eventLog?.emitStepTransition(
      1,
      fixStepName(1, totalSteps),
      totalSteps,
    );
  }

  private registerHandlers(): void {
    this.pi.on("before_agent_start", () => {
      if (!this.state.active || !this.state.systemPrompt) return undefined;
      return { systemPrompt: this.state.systemPrompt };
    });

    // Step 1 prompt injection. Same pattern as PlanDesignPhase: the CLI
    // message is a process trigger; the context event replaces it with
    // step 1 instructions before the initial LLM call.
    this.pi.on("context", (event) => {
      if (!this.state.active) return undefined;
      if (this.state.step !== 1 || !this.state.step1Prompt) return undefined;

      const messages = event.messages.map((m) => {
        if (m.role === "user") {
          return { ...m, content: this.state.step1Prompt! };
        }
        return m;
      });
      return { messages };
    });

    this.pi.on("tool_call", (event) => {
      if (!this.state.active) return undefined;

      const perm = checkPermission("plan-design", event.toolName);
      if (!perm.allowed) {
        return { block: true, reason: perm.reason };
      }

      // Step gate: mutation tools allowed ONLY in per-item steps (step 2
      // through totalSteps-1). Both step 1 (understand) and the final step
      // (review) are read-only. The upper bound prevents accidental mutations
      // during review that would bypass QR re-verification.
      const step = this.state.step;
      const total = this.totalSteps;
      const inItemRange = step >= 2 && step < total;
      if (!inItemRange && PLAN_MUTATION_TOOLS.has(event.toolName)) {
        return {
          block: true,
          reason: `${event.toolName} available in steps 2-${total - 1} (current: ${step})`,
        };
      }

      return undefined;
    });
  }

  private async handleStepComplete(): Promise<{ ok: boolean; prompt?: string; error?: string }> {
    const prev = this.state.step;
    const total = this.totalSteps;

    // Terminal: final step completed -> validate plan and end phase.
    if (prev === total) {
      const result = await this.handleFinalize();
      if (!result.ok) {
        await this.eventLog?.emitPhaseEnd("failed", result.errors?.join("; "));
        return { ok: false, error: result.errors?.join("; ") };
      }
      this.state.active = false;
      unhookDispatch(this.dispatch, "onCompleteStep");
      await this.eventLog?.emitPhaseEnd("completed");
      this.log("Fix phase complete, plan validation passed");
      return { ok: true, prompt: "Fix phase validation passed. Workflow complete." };
    }

    // Advance to next step. Step always increments -- no cursor, no hold.
    const next = prev + 1;
    this.state.step = next;

    // Per-item steps (2 <= next < total) pass the individual failure item
    // so fixStepGuidance generates item-specific prompts. Only the final
    // step (next === total) does not carry an item.
    const item = (next >= 2 && next < total)
      ? this.failures[next - 2]
      : undefined;
    const name = fixStepName(next, total, item);
    const prompt = formatStep(fixStepGuidance(next, total, { item }));

    this.log("Fix step complete, advancing", { from: prev, to: next, name });
    await this.eventLog?.emitStepTransition(next, name, total);

    return { ok: true, prompt };
  }

  private async handleFinalize(): Promise<{ ok: boolean; errors?: string[] }> {
    return loadAndValidatePlan(this.planDir, this.log);
  }
}
