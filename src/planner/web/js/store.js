// Zustand store and SSE event->state handlers.
//
// store.js owns both the store shape and the event->state mapping.
// sse.js only knows event type names and raw payloads -- it imports
// named handler functions from here and never calls useStore directly.
// Changing the store shape only requires updating this file.

import { create } from 'zustand'

export const useStore = create((set) => ({
  // Server-pushed state
  phase: null,
  stories: [],
  scouts: [],
  agents: [],
  logs: [],                  // Array<{ tool, summary, highValue, inFlight }>
  currentToolCallId: null,   // string | null -- in-flight tool for the main agent
  subagent: null,
  pendingInput: null,
  intakeProgress: null,      // IntakeProgressEvent | null -- set during intake phase
  artifactFiles: [],         // ArtifactEntry[] -- epic artifact file listing

  // Workflow orchestrator state
  // frozenLogs: snapshot of the completed phase's activity, displayed dimmed
  // above the orchestrator's live activity.
  frozenLogs: [],
  // workflowChat: multi-turn conversation history with the workflow orchestrator.
  // Deliberately NOT in pendingInput — workflow-decision is the only interaction
  // type that does NOT set pendingInput, because setting it would toggle
  // isInteractive=true in App.jsx, hiding the ActivityFeed where WorkflowChat lives.
  workflowChat: [],

  // Streaming token output from the active subagent
  streamingText: "",

  // Client-only state
  notifications: [],
  pipelineEnd: null,
  showSettings: false,
  availableModels: [],
}))

// -- SSE event handlers --

const set = useStore.setState

export function handleInitEvent(d) {
  set({ availableModels: d.availableModels || [] })
}

export function handlePhaseEvent(d) {
  set({
    phase: d.phase,
    frozenLogs: [],       // phase's frozen activity no longer needed
    workflowChat: [],     // conversation belongs to the previous transition
    // Clear interaction state and intake progress when leaving intake
    ...(d.phase !== 'intake' && { pendingInput: null, intakeProgress: null }),
  })
}

export function handleIntakeProgressEvent(d) {
  set({ intakeProgress: d })
}

export function handleStoriesEvent(d) {
  set({ stories: d.stories })
}

export function handleScoutsEvent(d) {
  set({ scouts: d.scouts })
}

export function handleAgentsEvent(d) {
  set({ agents: d.agents })
}

export function handleLogsEvent(d) {
  set({ logs: d.lines, currentToolCallId: d.currentToolCallId ?? null })
}

export function handleSubagentEvent(d) {
  set({ subagent: d })
}

export function handleSubagentIdleEvent() {
  // Reset streamingText here rather than in a separate 'subagent-idle' handler
  // in sse.js: subagent-idle is the canonical signal that the active subagent
  // has finished, so all subagent-end side-effects belong in one place. Adding
  // a second handler in sse.js for the same event would split the teardown
  // logic with no benefit.
  set({ subagent: null, streamingText: "" })
}

export function handleTokenDeltaEvent(d) {
  set(s => ({ streamingText: s.streamingText + d.delta }))
}

export function handleTokenClearEvent() {
  set({ streamingText: "" })
}

export function handlePipelineEndEvent(d) {
  set(s => ({
    phase: d.success ? 'completed' : s.phase,
    pipelineEnd: d,
    intakeProgress: null,
    frozenLogs: [],
    workflowChat: [],
  }))
}

export function handleAskEvent(d) {
  set({ pendingInput: { type: 'ask', requestId: d.requestId, questions: d.questions } })
}

export function handleModelConfigEvent(d) {
  set(s => ({
    pendingInput: { type: 'model-config', requestId: d.requestId, payload: { ...d.tiers, scoutConcurrency: d.scoutConcurrency } },
    ...(d.availableModels ? { availableModels: d.availableModels } : {}),
  }))
}

export function handleModelConfigConfirmedEvent() {
  set(s => s.pendingInput?.type === 'model-config' ? { pendingInput: null } : {})
}

export function handleAskCancelledEvent(d) {
  set(s => s.pendingInput?.requestId === d.requestId
    ? { pendingInput: null, notifications: [...s.notifications, { id: Date.now(), message: 'The question was cancelled -- the subagent has exited.', level: 'warning' }] }
    : {})
}

export function handleArtifactReviewEvent(d) {
  set({
    pendingInput: {
      type: 'artifact-review',
      requestId: d.requestId,
      payload: { artifactPath: d.artifactPath, content: d.content, description: d.description },
    }
  })
}

export function handleArtifactReviewCancelledEvent(d) {
  set(s => s.pendingInput?.requestId === d.requestId
    ? { pendingInput: null, notifications: [...s.notifications, { id: Date.now(), message: 'The artifact review was cancelled.', level: 'warning' }] }
    : {})
}

export function handleFrozenLogsEvent(d) {
  set({ frozenLogs: d.lines })
}

// workflow-decision does NOT set pendingInput. Setting it would toggle
// isInteractive=true in App.jsx, switching to PhaseContent and hiding the
// ActivityFeed where WorkflowChat lives. This is intentional and unlike all
// other interaction types (ask, artifact-review, model-config).
export function handleWorkflowDecisionEvent(d) {
  set(s => ({
    workflowChat: [
      ...s.workflowChat,
      {
        role: 'orchestrator',
        requestId: d.requestId,
        statusReport: d.statusReport,
        recommendedPhases: d.recommendedPhases,
      }
    ]
  }))
}

export function handleWorkflowDecisionCancelledEvent(d) {
  // Remove the pending orchestrator turn by requestId when cancelled
  set(s => ({
    workflowChat: s.workflowChat.filter(t =>
      !(t.role === 'orchestrator' && t.requestId === d.requestId)
    )
  }))
}

export function handleArtifactsEvent(d) {
  set({ artifactFiles: d.files || [] })
}

export function handleNotificationEvent(d) {
  set(s => ({
    notifications: [...s.notifications, { id: Date.now(), message: d.message, level: d.level }],
  }))
}

export function handleConnectionError() {
  set(s => ({
    notifications: [...s.notifications, { id: Date.now(), message: 'Connection lost -- reconnecting...', level: 'warning' }],
  }))
}
