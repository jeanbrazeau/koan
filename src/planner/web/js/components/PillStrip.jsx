import { useStore } from '../store.js'

const PHASES = [
  { id: 'intake',                    label: 'intake' },
  { id: 'brief-generation',          label: 'brief' },
  { id: 'core-flows',                label: 'core flows' },
  { id: 'tech-plan',                 label: 'tech plan' },
  { id: 'ticket-breakdown',          label: 'tickets' },
  { id: 'cross-artifact-validation', label: 'validation' },
  { id: 'execution',                 label: 'execute' },
  { id: 'implementation-validation', label: 'verify' },
]

const PHASE_ORDER = [
  'intake', 'brief-generation', 'core-flows', 'tech-plan',
  'ticket-breakdown', 'cross-artifact-validation', 'execution',
  'implementation-validation', 'completed',
]

export function PillStrip() {
  const phase = useStore(s => s.phase)
  if (!phase) return null

  const phaseIdx = PHASE_ORDER.indexOf(phase)

  return (
    <div id="pill-strip">
      {PHASES.map(({ id, label }) => {
        const pillIdx = PHASE_ORDER.indexOf(id)
        const cls = phase === 'completed' || phaseIdx > pillIdx ? 'pill done'
                  : phase === id                                ? 'pill active'
                  : 'pill pending'
        return <span key={id} class={cls}>{label}</span>
      })}
    </div>
  )
}
