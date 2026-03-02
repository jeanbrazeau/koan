export type WorkflowPhase =
  | "idle"
  | "architect-running"
  | "architect-failed"
  | "plan-design-complete"
  | "plan-code-running"
  | "plan-code-complete"
  | "plan-docs-running"
  | "plan-docs-complete"
  | "qr-decompose-running"
  | "qr-decompose-failed"
  | "qr-verify-running"
  | "qr-verify-failed"
  | "qr-complete";

export interface PlanInfo {
  id: string;
  directory: string;
  createdAt: string;
  metadataPath: string;
}

export interface WorkflowState {
  phase: WorkflowPhase;
  taskDescription: string | null;
  plan: PlanInfo | null;
}

export function createInitialState(): WorkflowState {
  return {
    phase: "idle",
    taskDescription: null,
    plan: null,
  };
}

export function initializePlanState(state: WorkflowState, plan: PlanInfo, taskDescription: string): void {
  state.plan = plan;
  state.taskDescription = taskDescription;
}
