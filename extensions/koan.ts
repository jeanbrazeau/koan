// Entry point for the koan pi extension. Serves dual roles: parent session
// (registers koan_plan tool and /koan-execute, /koan-status, /koan commands)
// and subagent mode (dispatches to phase workflow via CLI flags). All tools
// register unconditionally at init; phases restrict access via tool_call
// blocking at runtime.

import { Type } from "@sinclair/typebox";
import type { ExtensionAPI, ExtensionContext } from "@mariozechner/pi-coding-agent";

import { createSession } from "../src/planner/session.js";
import { detectSubagentMode, dispatchPhase } from "../src/planner/phases/dispatch.js";
import { registerAllTools, createDispatch, createPlanRef } from "../src/planner/tools/index.js";
import { createLogger } from "../src/utils/logger.js";
import { EventLog, extractToolEvent } from "../src/planner/lib/audit.js";
import { openKoanConfig } from "../src/planner/ui/config/menu.js";

function currentModelId(ctx: ExtensionContext): string | null {
  const model = ctx.model;
  if (!model) return null;
  return `${model.provider}/${model.id}`;
}

export default function koan(pi: ExtensionAPI): void {
  const log = createLogger("Koan");

  pi.registerFlag("koan-role", {
    description: "Koan subagent role (reserved)",
    type: "string",
    default: "",
  });

  pi.registerFlag("koan-phase", {
    description: "Koan workflow phase (reserved)",
    type: "string",
    default: "",
  });

  pi.registerFlag("koan-plan-dir", {
    description: "Koan plan directory path",
    type: "string",
    default: "",
  });

  pi.registerFlag("koan-subagent-dir", {
    description: "Koan subagent working directory",
    type: "string",
    default: "",
  });

  pi.registerFlag("koan-qr-item", {
    description: "QR item ID for reviewer subagent",
    type: "string",
    default: "",
  });

  pi.registerFlag("koan-fix", {
    description: "QR phase to fix (e.g. plan-design)",
    type: "string",
    default: "",
  });

  // Pi snapshots tools during _buildRuntime() at init. All 44 tools
  // register here unconditionally. Phases restrict access via tool_call
  // blocking at runtime.
  const dispatch = createDispatch();
  const planRef = createPlanRef();

  registerAllTools(pi, planRef, dispatch);

  // Subagent detection runs at before_agent_start (flags
  // are unavailable during init).
  let dispatched = false;
  pi.on("before_agent_start", async (_event, ctx) => {
    if (dispatched) return;
    dispatched = true;
    const config = detectSubagentMode(pi);
    if (config) {
      const planDir = pi.getFlag("koan-plan-dir") as string;
      if (planDir) {
        planRef.dir = planDir;
      }

      // EventLog exists only in subagent mode. Parent mode has no audit log.
      // Model identity is captured by the subagent itself and persisted in
      // state.json for parent widget rendering.
      let eventLog: EventLog | undefined;
      if (config.subagentDir) {
        eventLog = new EventLog(config.subagentDir, config.role, config.phase, currentModelId(ctx));
        await eventLog.open();

        // Capture all tool results for the audit trail. Graduated detail:
        // file paths for read/edit/write, binary name for bash, full
        // input+response for koan_* tools, name-only for everything else.
        pi.on("tool_result", (event) => {
          void eventLog!.append(extractToolEvent(event as {
            toolName: string;
            input: Record<string, unknown>;
            content: Array<{ type: string; text?: string }>;
            isError: boolean;
          }));
        });

        pi.on("session_shutdown", () => {
          void eventLog!.close();
        });
      }

      await dispatchPhase(pi, config, dispatch, planRef, log, eventLog);
    }
  });

  // Session: parent-mode workflow engine.
  const session = createSession(pi, dispatch, planRef);

  pi.registerTool({
    name: "koan_plan",
    label: "Plan",
    description: [
      "Launch a structured planning pipeline for complex, multi-file tasks.",
      "Invoke when the user asks to plan, use the planner, or when the task",
      "is too large to implement directly.",
      "",
      "The current conversation is automatically captured — it becomes the",
      "planning context. The pipeline spawns specialized agents (architect,",
      "developer, writer) that read the conversation history to understand",
      "the task, then produce a structured plan with milestones, code intents,",
      "and quality review.",
      "",
      "This is a long-running operation (5-15 minutes). Do not invoke for",
      "simple tasks that can be done in a single pass.",
    ].join("\n"),
    parameters: Type.Object({}),
    async execute(toolCallId, params, signal, onUpdate, ctx) {
      return await session.plan(ctx);
    },
  });

  pi.registerCommand("koan", {
    description: "Koan commands. Usage: /koan config",
    handler: async (args, ctx) => {
      const subcommand = args.trim();
      if (subcommand === "config") {
        await openKoanConfig(ctx);
      } else if (subcommand === "") {
        ctx.ui.notify("Usage: /koan config", "info");
      } else {
        ctx.ui.notify(`Unknown koan subcommand: "${subcommand}". Usage: /koan config`, "warning");
      }
    },
  });

  pi.registerCommand("koan-execute", {
    description: "Execute a koan plan",
    handler: async (_args, ctx) => { await session.execute(ctx); },
  });

  pi.registerCommand("koan-status", {
    description: "Show koan workflow status",
    handler: async (_args, ctx) => { await session.status(ctx); },
  });
}
