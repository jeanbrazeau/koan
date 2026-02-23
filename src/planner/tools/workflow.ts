// Workflow tool registration: koan_complete_step and koan_store_context.
// Tools register once at init; execute callbacks read from the mutable
// dispatch at call time, decoupling static registration from phase routing.

import { Type } from "@sinclair/typebox";
import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";

import { ContextStoreSchema } from "./context-store.js";
import { createLogger } from "../../utils/logger.js";
import type { WorkflowDispatch } from "../lib/dispatch.js";

const log = createLogger("Dispatch");

// Registers workflow tools. Called once at init in koan.ts,
// before pi's _buildRuntime() snapshot. Tool execute callbacks read
// from the dispatch at call time -- the dispatch is mutable, the
// tool list is not.
//
// Why register all tools unconditionally? Flags are unavailable during
// init (getFlag() returns undefined before _buildRuntime() sets flagValues),
// so conditional registration based on role/phase is impossible. Tools
// registered after _buildRuntime() are invisible to the LLM.
export function registerWorkflowTools(
  pi: ExtensionAPI,
  dispatch: WorkflowDispatch,
): void {
  // -- koan_complete_step --
  // The `thoughts` parameter captures the model's work output (analysis,
  // review, findings) as a tool parameter instead of as text output.
  // This ensures models that cannot mix text + tool_call in one response
  // (e.g. GPT-5-codex) still advance the workflow reliably.
  pi.registerTool({
    name: "koan_complete_step",
    label: "Complete current workflow step",
    description: [
      "Signal completion of the current workflow step.",
      "Put your analysis, findings, or review in the `thoughts` parameter.",
      "DO NOT call this tool until the step instructions explicitly tell you to.",
    ].join(" "),
    parameters: Type.Object({
      thoughts: Type.Optional(Type.String({
        description: "Your analysis, findings, or work output for this step.",
      })),
    }),
    async execute(_toolCallId, params) {
      if (!dispatch.onCompleteStep) {
        throw new Error("No workflow phase is active.");
      }
      const thoughts = (params as { thoughts?: string }).thoughts;
      const r = await dispatch.onCompleteStep(thoughts);
      if (!r.ok) {
        throw new Error(r.error ?? "Step transition failed.");
      }
      return {
        content: [{ type: "text" as const, text: r.prompt ?? "Step complete." }],
        details: undefined,
      };
    },
  });

  // -- koan_store_context --
  pi.registerTool({
    name: "koan_store_context",
    label: "Store planning context",
    description: [
      "Store structured planning context.",
      "DO NOT call this tool until the step instructions explicitly tell you to.",
      "Each field is a string array -- encode structure within strings, not as nested objects.",
    ].join(" "),
    parameters: ContextStoreSchema,
    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      if (!dispatch.onStoreContext) {
        throw new Error("Context capture is not active.");
      }
      const r = await dispatch.onStoreContext(params, ctx);
      if (!r.ok) {
        log("Context store rejected", { errors: r.errors });
        throw new Error(r.message);
      }
      log("Context stored");
      return {
        content: [{ type: "text" as const, text: r.message }],
        details: undefined,
      };
    },
  });
}
