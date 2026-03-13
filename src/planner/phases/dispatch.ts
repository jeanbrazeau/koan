// Phase dispatch: detects subagent mode from CLI flags and routes to the
// appropriate phase class based on role. Flags are unavailable at extension
// init (getFlag returns undefined before _buildRuntime), so detection is
// deferred to before_agent_start.

import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";

import { createLogger, type Logger } from "../../utils/logger.js";
import type { RuntimeContext } from "../lib/runtime-context.js";
import type { EventLog } from "../lib/audit.js";
import type { SubagentRole, StepSequence } from "../types.js";
import { IntakePhase } from "./intake/phase.js";
import { ScoutPhase } from "./scout/phase.js";
import { DecomposerPhase } from "./decomposer/phase.js";
import { OrchestratorPhase } from "./orchestrator/phase.js";
import { PlannerPhase } from "./planner/phase.js";
import { ExecutorPhase } from "./executor/phase.js";

// -- Config --

export interface SubagentConfig {
  role: SubagentRole;
  epicDir: string;
  subagentDir: string;
  storyId: string | null;
  stepSequence: StepSequence | null;
}

// -- Detection --

// Detects subagent mode by reading flags set via CLI
// (pi -p --koan-role intake --koan-epic-dir /path ...).
// Must be called from before_agent_start or later; flags are
// undefined before _buildRuntime() runs.
export function detectSubagentMode(pi: ExtensionAPI): SubagentConfig | null {
  const role = pi.getFlag("koan-role");
  if (!role || typeof role !== "string" || role.trim().length === 0) {
    return null;
  }

  const epicDir = pi.getFlag("koan-epic-dir");
  const subagentDir = pi.getFlag("koan-subagent-dir");
  const storyId = pi.getFlag("koan-story-id");
  const stepSequence = pi.getFlag("koan-step-sequence");

  return {
    role: role.trim() as SubagentRole,
    epicDir: typeof epicDir === "string" ? epicDir.trim() : "",
    subagentDir: typeof subagentDir === "string" ? subagentDir.trim() : "",
    storyId: typeof storyId === "string" && storyId.trim().length > 0 ? storyId.trim() : null,
    stepSequence: typeof stepSequence === "string" && stepSequence.trim().length > 0
      ? stepSequence.trim() as StepSequence
      : null,
  };
}

// -- Dispatch --

export async function dispatchPhase(
  pi: ExtensionAPI,
  config: SubagentConfig,
  ctx: RuntimeContext,
  log?: Logger,
  eventLog?: EventLog,
): Promise<void> {
  const logger = log ?? createLogger("Dispatch");

  switch (config.role) {
    case "intake": {
      const phase = new IntakePhase(pi, { epicDir: config.epicDir }, ctx, logger, eventLog);
      await phase.begin();
      break;
    }
    case "scout": {
      const phase = new ScoutPhase(pi, { epicDir: config.epicDir }, ctx, logger, eventLog);
      await phase.begin();
      break;
    }
    case "decomposer": {
      const phase = new DecomposerPhase(pi, { epicDir: config.epicDir }, ctx, logger, eventLog);
      await phase.begin();
      break;
    }
    case "orchestrator": {
      const stepSequence = config.stepSequence ?? "pre-execution";
      const phase = new OrchestratorPhase(
        pi,
        { epicDir: config.epicDir, stepSequence, storyId: config.storyId ?? undefined },
        ctx, logger, eventLog,
      );
      await phase.begin();
      break;
    }
    case "planner": {
      // Fail-fast: missing storyId produces malformed paths like stories//plan/plan.md (§12.4.3).
      if (!config.storyId) throw new Error("planner phase requires --koan-story-id flag");
      const phase = new PlannerPhase(
        pi,
        { epicDir: config.epicDir, storyId: config.storyId },
        ctx, logger, eventLog,
      );
      await phase.begin();
      break;
    }
    case "executor": {
      // Fail-fast: missing storyId produces malformed paths like stories//plan/plan.md (§12.4.3).
      if (!config.storyId) throw new Error("executor phase requires --koan-story-id flag");
      const retryContext = pi.getFlag("koan-retry-context");
      const phase = new ExecutorPhase(
        pi,
        {
          epicDir: config.epicDir,
          storyId: config.storyId,
          retryContext: typeof retryContext === "string" && retryContext.length > 0 ? retryContext : undefined,
        },
        ctx, logger, eventLog,
      );
      await phase.begin();
      break;
    }
    default:
      logger("Unknown role", { role: config.role });
  }
}
