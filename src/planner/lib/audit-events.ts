// Event type definitions for the audit trail. No I/O, no Node.js imports.

// -- Types --

export interface EventBase {
  ts: string;
  seq: number;
}

// -- Tool events --
// Every tool invocation produces a (tool_call, tool_result) pair in the log.
// tool_call fires when the LLM requests the tool; tool_result fires when
// the tool returns. Both carry toolCallId for correlation.

export interface ToolCallEvent extends EventBase {
  kind: "tool_call";
  toolCallId: string;
  tool: string;
  input: Record<string, unknown>;
}

export interface ToolResultEvent extends EventBase {
  kind: "tool_result";
  toolCallId: string;
  tool: string;
  error: boolean;
  // Summarized output metrics (not the full content -- too large for the log).
  lines?: number;
  chars?: number;
  // Koan tool response text preserved for projection (completionSummary, etc.).
  koanResponse?: string[];
}

// -- Lifecycle events --

export interface PhaseStartEvent extends EventBase {
  kind: "phase_start";
  phase: string;
  role: string;
  model?: string | null;
  totalSteps: number;
}

export interface StepTransitionEvent extends EventBase {
  kind: "step_transition";
  step: number;
  name: string;
  totalSteps: number;
}

export interface PhaseEndEvent extends EventBase {
  kind: "phase_end";
  outcome: "completed" | "failed";
  detail?: string;
}

export interface HeartbeatEvent extends EventBase {
  kind: "heartbeat";
}

export interface UsageEvent extends EventBase {
  kind: "usage";
  input: number;
  output: number;
  cacheRead: number;
  cacheWrite: number;
}

export interface ThinkingEvent extends EventBase {
  kind: "thinking";
  // Truncated thinking content (first 2000 chars for log size).
  text: string;
  // Original length before truncation.
  chars: number;
}

export interface ConfidenceChangeEvent extends EventBase {
  kind: "confidence_change";
  // The confidence level declared by the intake agent via koan_set_confidence.
  level: "exploring" | "low" | "medium" | "high" | "certain";
  // Which iteration of the Scout->Deliberate->Reflect loop this was declared in.
  iteration: number;
}

export interface IterationStartEvent extends EventBase {
  kind: "iteration_start";
  // The new iteration number (incremented from the previous Reflect step).
  iteration: number;
  // Maximum allowed iterations before the loop is forced to exit.
  maxIterations: number;
}

export type AuditEvent =
  | ToolCallEvent
  | ToolResultEvent
  | PhaseStartEvent
  | StepTransitionEvent
  | PhaseEndEvent
  | HeartbeatEvent
  | UsageEvent
  | ThinkingEvent
  | ConfidenceChangeEvent
  | IterationStartEvent;

// Distributive Omit -- distributes over union members so object literals
// with fields specific to one member are accepted.
type DistributiveOmit<T, K extends PropertyKey> = T extends unknown ? Omit<T, K> : never;
export type AuditEventPartial = DistributiveOmit<AuditEvent, "ts" | "seq">;

// -- Projection --
// Eagerly materialized state summary. Written atomically to state.json
// after every event so the parent (web server) can poll cheaply.

export interface Projection {
  role: string;
  phase: string;
  model: string | null;
  status: "running" | "completed" | "failed";
  step: number;
  totalSteps: number;
  stepName: string;
  lastAction: string | null;
  // toolCallId of the currently in-flight tool, null when idle.
  // Lets the UI distinguish "doing X" from "done with X".
  currentToolCallId: string | null;
  updatedAt: string;
  eventCount: number;
  error: string | null;
  completionSummary: string | null;
  tokensSent: number;
  tokensReceived: number;
  // Timestamp of the most recent tool_result event; used to track thinking gaps.
  lastToolResultAt: string | null;
  // Intake-specific: the most recent confidence level declared by koan_set_confidence.
  // Null for non-intake subagents or before any confidence is declared.
  intakeConfidence: "exploring" | "low" | "medium" | "high" | "certain" | null;
  // Intake-specific: the current loop iteration (1-based). Zero for non-intake.
  intakeIteration: number;
}

// -- Correlated tool invocations --
// Reduced view of paired (tool_call, tool_result) events.

export interface ToolInvocation {
  toolCallId: string;
  tool: string;
  input: Record<string, unknown>;
  callTs: string;
  resultTs: string | null;
  error: boolean | null;
  inFlight: boolean;
  durationMs: number | null;
  // Output metrics from the result event.
  lines?: number;
  chars?: number;
  koanResponse?: string[];
}
