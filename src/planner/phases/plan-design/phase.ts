// Plan-design phase -- 6-step architect workflow that produces plan.json
// from captured context. Step gate: mutation tools blocked before step 6
// (blocklist pattern). Validation runs at step-6 completion.

import * as path from "node:path";

import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";

import { loadAndValidatePlan } from "../../plan/validate.js";
import {
  loadPlanDesignSystemPrompt,
  buildPlanDesignSystemPrompt,
  planDesignStepGuidance,
  STEP_NAMES,
} from "./prompts.js";
import { formatStep } from "../../lib/step.js";
import { createLogger, type Logger } from "../../../utils/logger.js";
import { EventLog } from "../../lib/audit.js";
import { hookDispatch, unhookDispatch, type WorkflowDispatch, type PlanRef } from "../../lib/dispatch.js";
import { checkPermission, PLAN_MUTATION_TOOLS } from "../../lib/permissions.js";

type PlanDesignStep = 1 | 2 | 3 | 4 | 5 | 6;

interface PlanDesignState {
  active: boolean;
  step: PlanDesignStep;
  step1Prompt: string | null;
  systemPrompt: string | null;
}

const TOTAL_STEPS = 6;

export class PlanDesignPhase {
  private readonly pi: ExtensionAPI;
  private readonly planDir: string;
  private readonly log: Logger;
  private readonly state: PlanDesignState;
  private readonly eventLog: EventLog | undefined;
  private readonly dispatch: WorkflowDispatch;
  private readonly planRef: PlanRef;

  constructor(
    pi: ExtensionAPI,
    config: { planDir: string },
    dispatch: WorkflowDispatch,
    planRef: PlanRef,
    log?: Logger,
    eventLog?: EventLog,
  ) {
    this.pi = pi;
    this.planDir = config.planDir;
    this.dispatch = dispatch;
    this.planRef = planRef;
    this.log = log ?? createLogger("PlanDesign");
    this.eventLog = eventLog;

    this.state = {
      active: false,
      step: 1,
      step1Prompt: null,
      systemPrompt: null,
    };

    this.registerHandlers();
  }

  async begin(): Promise<void> {
    let basePrompt: string;
    try {
      basePrompt = await loadPlanDesignSystemPrompt();
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      this.log("Failed to load plan-design system prompt", { error: message });
      return;
    }

    this.state.systemPrompt = buildPlanDesignSystemPrompt(basePrompt);
    const conversationPath = path.join(this.planDir, "conversation.jsonl");
    this.state.step1Prompt = formatStep(planDesignStepGuidance(1, conversationPath));
    this.state.active = true;
    this.state.step = 1;

    // No koan_store_plan tool. Each mutation writes to disk immediately.
    // Step 6 ends with koan_complete_step, which runs validation. Removes
    // the two-step 'build then finalize' pattern that caused LLM to skip
    // intermediate tools.
    hookDispatch(this.dispatch, "onCompleteStep", () => this.handleStepComplete());

    this.log("Starting plan-design workflow", { step: 1 });
    await this.eventLog?.emitPhaseStart(TOTAL_STEPS);
    await this.eventLog?.emitStepTransition(1, STEP_NAMES[1], TOTAL_STEPS);
  }

  private registerHandlers(): void {
    this.pi.on("before_agent_start", () => {
      if (!this.state.active || !this.state.systemPrompt) return undefined;
      return { systemPrompt: this.state.systemPrompt };
    });

    // Step 1 prompt injection. The CLI message is a process trigger --
    // the context event fires before each LLM call and replaces the
    // user message with the actual step 1 instructions. Messages are
    // structuredCloned before reaching this handler (runner.ts:660),
    // so stored history is unaffected. Handler is a no-op once the
    // step advances past 1.
    //
    // Why context event instead of sendUserMessage? Step 1 has no
    // preceding tool call (no tool result to inject prompt into).
    // Context event injects the prompt before the initial LLM call.
    // pi structuredClones messages, so modifications here are isolated.
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

      // Step gate: mutation tools are step-6-only. Blocklist (not whitelist)
      // so read tools and future pi-native tools pass through after
      // checkPermission approves them.
      const step = this.state.step;
      if (step < 6 && PLAN_MUTATION_TOOLS.has(event.toolName)) {
        return {
          block: true,
          reason: `${event.toolName} available in step 6 (current: ${step})`,
        };
      }

      return undefined;
    });

  }

  private async handleStepComplete(): Promise<{ ok: boolean; prompt?: string; error?: string }> {
    const prev = this.state.step;

    if (prev === 6) {
      const result = await this.handleFinalize();
      if (!result.ok) {
        await this.eventLog?.emitPhaseEnd("failed", result.errors?.join("; "));
        return { ok: false, error: result.errors?.join("; ") };
      }
      this.state.active = false;
      unhookDispatch(this.dispatch, "onCompleteStep");
      await this.eventLog?.emitPhaseEnd("completed");
      this.log("Plan finalized, workflow complete");
      return { ok: true, prompt: "Plan validation passed. Workflow complete." };
    }

    this.state.step = (prev + 1) as PlanDesignStep;
    const nextName = STEP_NAMES[this.state.step];
    const prompt = formatStep(planDesignStepGuidance(this.state.step));

    this.log("Step complete, advancing", { from: prev, to: this.state.step, name: nextName });
    await this.eventLog?.emitStepTransition(this.state.step, nextName, TOTAL_STEPS);

    return { ok: true, prompt };
  }

  private async handleFinalize(): Promise<{ ok: boolean; errors?: string[] }> {
    return loadAndValidatePlan(this.planDir, this.log);
  }
}
