import { useMemo } from 'react'
import { useStore, ALL_PHASES } from '../store/index'

export function PillStrip() {
  const phase = useStore(s => s.run?.phase ?? '')

  // Derive done phases locally — frontend-only computation from the phase string
  const donePhases = useMemo(() => {
    const idx = ALL_PHASES.indexOf(phase)
    return idx === -1 ? [...ALL_PHASES] : ALL_PHASES.slice(0, idx)
  }, [phase])

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
