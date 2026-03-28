import { useStore } from '../store/index'
import { useElapsed } from '../hooks/useElapsed'
import { formatTokens } from '../utils'

function AgentSection() {
  const agent = useStore(s => s.primaryAgent)
  const elapsed = useElapsed(agent?.startedAt ?? Date.now())

  if (!agent) return null

  return (
    <>
      <div className="sidebar-agent">
        <div className="sidebar-agent-role">{agent.role}</div>
        <div className="sidebar-agent-model">{agent.model ?? '--'}</div>
        <div className="sidebar-agent-step">{agent.stepName || `step ${agent.step}`}</div>
        <div className="sidebar-agent-stats">
          <span>{formatTokens(agent.tokensSent, agent.tokensReceived)}</span>
          <span className="elapsed-value">{elapsed}</span>
        </div>
      </div>
      <div className="sidebar-divider" />
    </>
  )
}

export function StatusSidebar() {
  const phase = useStore(s => s.phase)
  const primaryAgent = useStore(s => s.primaryAgent)
  const intakeProgress = useStore(s => s.intakeProgress)

  const hasContent = primaryAgent !== null || phase

  return (
    <aside className="status-sidebar">
      <AgentSection />

      {phase && (
        <div className="sidebar-section">
          <div className="sidebar-label">Phase</div>
          <div className="sidebar-value">{phase}</div>
        </div>
      )}

      {intakeProgress?.subPhase && (
        <div className="sidebar-section">
          <div className="sidebar-label">Sub-phase</div>
          <div className="sidebar-value">{intakeProgress.subPhase}</div>
        </div>
      )}

      {intakeProgress?.summary && (
        <>
          <div className="sidebar-divider" />
          <div className="sidebar-summary">{intakeProgress.summary}</div>
        </>
      )}

      {!hasContent && (
        <>
          <div className="sidebar-heading">Status</div>
          <div className="sidebar-value" style={{ color: 'var(--text-ghost)' }}>
            Waiting...
          </div>
        </>
      )}
    </aside>
  )
}
