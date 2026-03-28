import { useStore, ALL_PHASES } from '../store/index'

export function PillStrip() {
  const phase = useStore(s => s.phase)
  const donePhases = useStore(s => s.donePhases)

  return (
    <div className="pill-strip">
      {ALL_PHASES.map(p => {
        const isActive = p === phase
        const isDone = donePhases.includes(p)
        const cls = ['pill', isActive ? 'active' : isDone ? 'done' : ''].filter(Boolean).join(' ')
        return (
          <span key={p} className={cls} data-phase={p}>
            {p}
          </span>
        )
      })}
    </div>
  )
}
