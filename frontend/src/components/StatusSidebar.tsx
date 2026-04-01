import { useMemo } from 'react'
import { useStore } from '../store/index'
import { useElapsed } from '../hooks/useElapsed'
import { formatTokens } from '../utils'

function AgentSection() {
  const agents = useStore(s => s.run?.agents)
  const primary = useMemo(
    () => agents ? Object.values(agents).find(a => a.isPrimary && a.status === 'running') : null,
    [agents]
  )
  const elapsed = useElapsed(primary?.startedAtMs ?? Date.now())

  if (!primary) return null

  return (
    <>
      <div className="sidebar-agent">
        <div className="sidebar-agent-role">{primary.role}</div>
        <div className="sidebar-agent-model">{primary.model ?? '--'}</div>
        <div className="sidebar-agent-step">{primary.stepName || `step ${primary.step}`}</div>
        <div className="sidebar-agent-stats">
          <span>{formatTokens(primary.conversation.inputTokens, primary.conversation.outputTokens)}</span>
          <span className="elapsed-value">{elapsed}</span>
        </div>
      </div>
      <div className="sidebar-divider" />
    </>
  )
}

export function StatusSidebar() {
  const phase = useStore(s => s.run?.phase ?? '')
  const agents = useStore(s => s.run?.agents)
  const hasPrimary = useMemo(
    () => agents ? Object.values(agents).some(a => a.isPrimary && a.status === 'running') : false,
    [agents]
  )

  const hasContent = hasPrimary || phase

  return (
    <aside className="status-sidebar">
      <AgentSection />

      {phase && (
        <div className="sidebar-section">
          <div className="sidebar-label">Phase</div>
          <div className="sidebar-value">{phase}</div>
        </div>
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
