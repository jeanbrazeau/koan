import { useStore } from '../store.js'

const PHASES = [
  { id: 'intake',        label: 'intake' },
  { id: 'brief',         label: 'brief' },
  { id: 'decomposition', label: 'decompose' },
  { id: 'review',        label: 'review' },
  { id: 'executing',     label: 'execute' },
]

const PHASE_ORDER = ['intake', 'brief', 'decomposition', 'review', 'executing', 'completed']

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
