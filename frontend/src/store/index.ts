import { create } from 'zustand'

export const ALL_PHASES = [
  'intake', 'brief-generation', 'core-flows', 'tech-plan',
  'ticket-breakdown', 'cross-artifact-validation',
  'execution', 'implementation-validation',
]

// -- Domain types ------------------------------------------------------------

export interface AgentInfo {
  agentId: string
  role: string
  model: string | null
  step: number
  stepName: string
  startedAt: number   // UTC epoch milliseconds
  tokensSent: number
  tokensReceived: number
}

export interface ArtifactFile {
  path: string
  size: number
  modifiedAt: number  // UTC epoch milliseconds
}

export interface CompletionInfo {
  success: boolean
  summary: string
  error: string
  phase: string
  artifacts: ArtifactFile[]
}

export interface NotificationEntry {
  id: string
  type: string
  severity: 'error' | 'warning' | 'info'
  message: string
  detail?: string
}

export interface ActivityEntry {
  tool: string
  summary: string
  inFlight: boolean
  ts?: string
}

export interface AskOption {
  value: string
  label: string
  recommended?: boolean
}

export interface AskQuestion {
  question: string
  multi: boolean
  options: AskOption[]
  allow_other?: boolean
  context?: string
}

export interface ChatTurn {
  role: 'orchestrator' | 'user'
  status_report?: string
  recommended_phases?: { phase: string; context?: string; recommended?: boolean }[]
  message?: string
}

export type Interaction =
  | { type: 'ask'; questions: AskQuestion[]; token: string }
  | { type: 'artifact-review'; content: string; description?: string; token: string }
  | { type: 'workflow-decision'; chat_turns: ChatTurn[]; token: string }

export interface ProfileTierConfig {
  runner_type: string
  model: string
  thinking: string
}

export interface Profile {
  name: string
  read_only: boolean
  tiers: Record<string, ProfileTierConfig>
}

export interface Installation {
  alias: string
  runner_type: string
  binary: string
  extra_args: string[]
  is_active?: boolean
}

// -- Store -------------------------------------------------------------------

interface KoanState {
  // Connection
  connected: boolean

  // Run state
  runStarted: boolean
  phase: string
  donePhases: string[]

  // Primary agent (phase-level)
  primaryAgent: AgentInfo | null

  // Intake sub-phase progress
  intakeProgress: { subPhase: string; confidence: string | null; summary: string } | null

  // Scout agents — keyed by agentId
  scouts: Record<string, AgentInfo>

  // Activity feed
  activityLog: ActivityEntry[]
  streamBuffer: string

  // Notifications
  notifications: NotificationEntry[]

  // Active interaction (at most one at a time)
  activeInteraction: Interaction | null

  // Artifacts
  artifacts: ArtifactFile[]

  // Pipeline completion
  completion: CompletionInfo | null

  // Settings
  settingsOpen: boolean
  profiles: Profile[]
  installations: Installation[]

  // Actions
  setConnected: (v: boolean) => void
  setPhase: (phase: string) => void
  setPrimaryAgent: (agent: AgentInfo | null) => void
  setIntakeProgress: (p: KoanState['intakeProgress']) => void
  setScouts: (scouts: Record<string, AgentInfo>) => void
  appendLog: (entry: ActivityEntry) => void
  appendStreamDelta: (delta: string) => void
  clearStream: () => void
  addNotification: (n: NotificationEntry) => void
  dismissNotification: (id: string) => void
  setInteraction: (interaction: Interaction | null) => void
  setArtifacts: (artifacts: ArtifactFile[]) => void
  setCompletion: (info: CompletionInfo) => void
  setSettingsOpen: (v: boolean) => void
  setProfiles: (profiles: Profile[]) => void
  setInstallations: (installations: Installation[]) => void
}

export const useStore = create<KoanState>((set) => ({
  connected: false,
  runStarted: false,
  phase: '',
  donePhases: [],
  primaryAgent: null,
  intakeProgress: null,
  scouts: {},
  activityLog: [],
  streamBuffer: '',
  notifications: [],
  activeInteraction: null,
  artifacts: [],
  completion: null,
  settingsOpen: false,
  profiles: [],
  installations: [],

  setConnected: (v) => set({ connected: v }),

  // setPhase also sets runStarted=true (any phase event means a run is active)
  // and derives donePhases (all known phases before current). This is critical
  // for page reloads mid-run: the replayed 'phase' event flips runStarted,
  // so the user sees the live view instead of the landing page.
  setPhase: (phase) => set(() => {
    const idx = ALL_PHASES.indexOf(phase)
    const donePhases = idx === -1 ? [...ALL_PHASES] : ALL_PHASES.slice(0, idx)
    return { phase, runStarted: true, donePhases }
  }),

  setPrimaryAgent: (agent) => set({ primaryAgent: agent }),
  setIntakeProgress: (p) => set({ intakeProgress: p }),
  setScouts: (scouts) => set({ scouts }),
  appendLog: (entry) => set((s) => ({ activityLog: [...s.activityLog, entry] })),
  appendStreamDelta: (delta) => set((s) => ({ streamBuffer: s.streamBuffer + delta })),
  clearStream: () => set({ streamBuffer: '' }),
  addNotification: (n) => set((s) => ({ notifications: [...s.notifications, n] })),
  dismissNotification: (id) => set((s) => ({
    notifications: s.notifications.filter((n) => n.id !== id),
  })),
  setInteraction: (interaction) => set({ activeInteraction: interaction }),
  setArtifacts: (artifacts) => set({ artifacts }),
  setCompletion: (info) => set({ completion: info }),
  setSettingsOpen: (v) => set({ settingsOpen: v }),
  setProfiles: (profiles) => set({ profiles }),
  setInstallations: (installations) => set({ installations }),
}))

export type KoanStore = typeof useStore
