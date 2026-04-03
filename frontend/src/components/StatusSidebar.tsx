import { useMemo } from 'react'
import { useStore } from '../store/index'
import { useElapsed } from '../hooks/useElapsed'

function toTitleCase(phase: string): string {
  return phase
    .split('-')
    .map(w => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

function fmt(n: number): string {
  if (!n) return '--'
  if (n < 1000) return String(n)
  return (n / 1000).toFixed(1).replace(/\.0$/, '') + 'k'
}

export function StatusSidebar() {
  const phase = useStore(s => s.run?.phase ?? '')
  const agents = useStore(s => s.run?.agents)

  const primary = useMemo(
    () => agents ? Object.values(agents).find(a => a.isPrimary && a.status === 'running') : null,
    [agents]
  )

  // Derive totalSteps from the last StepEntry in the conversation
  const totalSteps = useMemo(() => {
    if (!primary) return null
    const entries = primary.conversation.entries
    for (let i = entries.length - 1; i >= 0; i--) {
      const e = entries[i]
      if (e.type === 'step' && e.totalSteps != null) return e.totalSteps
    }
    return null
  }, [primary])

  const elapsed = useElapsed(primary?.startedAtMs ?? Date.now())

  const barPct = (totalSteps && primary && primary.step > 0)
    ? Math.min(100, (primary.step / totalSteps) * 100)
    : 0

  const hasContent = !!phase || !!primary

  if (!hasContent) {
    return (
      <aside className="status-sidebar">
        <div className="sidebar-waiting">Waiting…</div>
      </aside>
    )
  }

  return (
    <aside className="status-sidebar">
      {phase && (
        <div className="sidebar-phase-section">
          <div className="sidebar-section-label">Phase</div>
          <div className="sidebar-phase-name">{toTitleCase(phase)}</div>

          {primary && primary.step > 0 && (
            <div className="sidebar-step-block">
              <div className="sidebar-step-meta">
                <span>{primary.stepName || `step ${primary.step}`}</span>
                {totalSteps != null && (
                  <span>{primary.step}&thinsp;/&thinsp;{totalSteps}</span>
                )}
              </div>
              {totalSteps != null && (
                <div className="sidebar-step-bar">
                  <div className="sidebar-step-fill" style={{ width: `${barPct}%` }} />
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {primary && (
        <>
          <div className="sidebar-divider" />
          <div className="sidebar-agent-section">
            <div className="sidebar-section-label">Orchestrator</div>
            <div className="sidebar-model-row">
              <span className="sidebar-model-dot" />
              <span className="sidebar-model-name">{primary.model ?? '--'}</span>
            </div>
            <div className="sidebar-metrics">
              <div className="sidebar-metric-row">
                <span>tokens in</span>
                <span>{fmt(primary.conversation.inputTokens)}</span>
              </div>
              <div className="sidebar-metric-row">
                <span>tokens out</span>
                <span>{fmt(primary.conversation.outputTokens)}</span>
              </div>
              <div className="sidebar-metric-row">
                <span>elapsed</span>
                <span>{elapsed}</span>
              </div>
            </div>
          </div>
        </>
      )}
    </aside>
  )
}
