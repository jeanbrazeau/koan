// Tool registration aggregator. Single entry point for koan.ts.
// Re-exports dispatch primitives so koan.ts needs one import for both
// tool registration and workflow infrastructure.

import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import type { WorkflowDispatch, PlanRef } from "../lib/dispatch.js";

import { registerWorkflowTools } from "./workflow.js";
import { registerPlanGetterTools } from "./getters.js";
import { registerPlanSetterTools } from "./setters.js";
import { registerPlanDesignEntityTools } from "./entity-design.js";
import { registerPlanCodeEntityTools } from "./entity-code.js";
import { registerPlanStructureEntityTools } from "./entity-structure.js";
import { registerQRTools } from "./qr.js";

export type { WorkflowDispatch, PlanRef, StepResult } from "../lib/dispatch.js";
export {
  createDispatch,
  createPlanRef,
  hookDispatch,
  unhookDispatch,
} from "../lib/dispatch.js";

export function registerAllTools(
  pi: ExtensionAPI,
  planRef: PlanRef,
  dispatch: WorkflowDispatch,
): void {
  registerWorkflowTools(pi, dispatch);
  registerPlanGetterTools(pi, planRef);
  registerPlanSetterTools(pi, planRef);
  registerPlanDesignEntityTools(pi, planRef);
  registerPlanCodeEntityTools(pi, planRef);
  registerPlanStructureEntityTools(pi, planRef);
  registerQRTools(pi, planRef);
}
