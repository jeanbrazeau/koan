// Entry point for the koan pi extension. Serves dual roles: parent session
// (registers koan_plan tool and /koan commands) and subagent mode (dispatches
// to phase workflow via CLI flags). All tools register unconditionally at init;
// phases restrict access via tool_call blocking at runtime.
//
// RuntimeContext replaces the three separate mutable refs (PlanRef,
// SubagentRef, WorkflowDispatch) used in the previous design.

import * as path from "node:path";
import { Type } from "@sinclair/typebox";
import type { ExtensionAPI, ExtensionContext } from "@mariozechner/pi-coding-agent";

import { detectSubagentMode, dispatchPhase } from "../src/planner/phases/dispatch.js";
import { registerAllTools, createRuntimeContext } from "../src/planner/tools/index.js";
import { createLogger, setLogDir } from "../src/utils/logger.js";
import { EventLog, extractToolEvent } from "../src/planner/lib/audit.js";
import { openKoanConfig } from "../src/planner/ui/config/menu.js";
import { createEpicDirectory } from "../src/planner/epic/state.js";
import { exportConversation } from "../src/planner/conversation.js";
import { runEpicPipeline } from "../src/planner/driver.js";

function currentModelId(ctx: ExtensionContext): string | null {
  const model = ctx.model;
  if (!model) return null;
  return `${model.provider}/${model.id}`;
}

export default function koan(pi: ExtensionAPI): void {
  const log = createLogger("Koan");

  // -- Flags --
  pi.registerFlag("koan-role", {
    description: "Koan subagent role",
    type: "string",
    default: "",
  });
  pi.registerFlag("koan-epic-dir", {
    description: "Koan epic directory path",
    type: "string",
    default: "",
  });
  pi.registerFlag("koan-subagent-dir", {
    description: "Koan subagent working directory",
    type: "string",
    default: "",
  });
  pi.registerFlag("koan-story-id", {
    description: "Current story ID for per-story subagents",
    type: "string",
    default: "",
  });
  pi.registerFlag("koan-step-sequence", {
    description: "Orchestrator step sequence (pre-execution or post-execution)",
    type: "string",
    default: "",
  });
  pi.registerFlag("koan-retry-context", {
    description: "Failure context from previous execution attempt",
    type: "string",
    default: "",
  });

  // RuntimeContext: single mutable object that carries epicDir, subagentDir,
  // and the active onCompleteStep handler. Replaces the old PlanRef +
  // SubagentRef + WorkflowDispatch triple.
  const ctx = createRuntimeContext();

  registerAllTools(pi, ctx);

  let dispatched = false;
  pi.on("before_agent_start", async (_event, extCtx) => {
    if (dispatched) return;
    dispatched = true;

    const config = detectSubagentMode(pi);
    if (config) {
      // Populate RuntimeContext from CLI flags.
      if (config.epicDir) {
        ctx.epicDir = config.epicDir;
      }

      let eventLog: EventLog | undefined;
      if (config.subagentDir) {
        ctx.subagentDir = config.subagentDir;
        eventLog = new EventLog(
          config.subagentDir,
          config.role,
          config.role,
          currentModelId(extCtx),
        );
        await eventLog.open();

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

      await dispatchPhase(pi, config, ctx, log, eventLog);
    }
  });

  // -- koan_plan tool --
  // Requires an interactive terminal session: subagents use koan_ask_question
  // and koan_request_scouts, which are answered by the IPC responder running
  // in the parent session. Without a UI, no IPC responder starts and any
  // subagent calling those tools will poll ipc.json forever, hanging the
  // pipeline permanently.
  pi.registerTool({
    name: "koan_plan",
    label: "Plan",
    description: [
      "Launch a structured planning pipeline for complex, multi-file tasks.",
      "Invoke when the user asks to plan, use the planner, or when the task",
      "is too large to implement directly.",
      "",
      "The current conversation is automatically captured — it becomes the",
      "planning context. The pipeline spawns specialized agents that decompose",
      "the task into stories and execute them one at a time.",
      "",
      "This is a long-running operation. Do not invoke for simple tasks.",
    ].join("\n"),
    parameters: Type.Object({}),
    async execute(_toolCallId, _params, _signal, _onUpdate, extCtx) {
      // koan_plan requires an interactive terminal session. Subagents use
      // koan_ask_question and koan_request_scouts, which are answered by the
      // IPC responder that only starts when a UI is present. Without a UI,
      // subagents would poll ipc.json forever and the pipeline would hang.
      if (!extCtx.hasUI) {
        return {
          content: [{ type: "text" as const, text: "koan_plan requires an interactive terminal session." }],
          details: undefined,
        };
      }

      const epicInfo = await createEpicDirectory("", extCtx.cwd);
      ctx.epicDir = epicInfo.directory;
      setLogDir(epicInfo.directory);

      await exportConversation(extCtx.sessionManager, epicInfo.directory);
      log("Conversation exported", { epicDir: epicInfo.directory });

      const extensionPath = path.resolve(import.meta.dirname, "koan.ts");
      const ui = extCtx.hasUI ? extCtx.ui : null;

      const result = await runEpicPipeline(epicInfo.directory, extCtx.cwd, extensionPath, log, ui);

      return {
        content: [{ type: "text" as const, text: result.summary }],
        details: undefined,
      };
    },
  });

  // -- Commands --
  pi.registerCommand("koan", {
    description: "Koan commands. Usage: /koan config",
    handler: async (args, extCtx) => {
      const subcommand = args.trim();
      if (subcommand === "config") {
        await openKoanConfig(extCtx);
      } else if (subcommand === "") {
        extCtx.ui.notify("Usage: /koan config", "info");
      } else {
        extCtx.ui.notify(`Unknown koan subcommand: "${subcommand}". Usage: /koan config`, "warning");
      }
    },
  });

  pi.registerCommand("koan-execute", {
    description: "Execute a koan plan",
    handler: async (_args, extCtx) => {
      extCtx.ui.notify("Execution mode is not yet implemented.", "warning");
    },
  });

  pi.registerCommand("koan-status", {
    description: "Show koan workflow status",
    handler: async (_args, extCtx) => {
      extCtx.ui.notify("Status: idle", "info");
    },
  });
}
