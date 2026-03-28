import { useStore } from '../store/index'
import { formatSize } from '../utils'

export function Completion() {
  const completion = useStore(s => s.completion)

  if (!completion) return null

  return (
    <div className="phase-content">
      <div className="phase-inner">
        {completion.success ? (
          <>
            <h2 className="phase-heading">Run Complete</h2>
            <p className="phase-status">
              {completion.summary || 'All phases completed successfully.'}
            </p>
            {(completion.artifacts ?? []).length > 0 && (
              <div className="summary-list">
                {completion.artifacts.map(a => (
                  <div key={a.path} className="summary-item">
                    <span className="icon-done">[OK]</span>
                    <span>
                      {a.path} ({formatSize(a.size)})
                    </span>
                  </div>
                ))}
              </div>
            )}
          </>
        ) : (
          <>
            <h2 className="phase-heading" style={{ color: 'var(--red)' }}>
              Run Failed
            </h2>
            <p className="phase-status">{completion.error || 'An error occurred.'}</p>
            {completion.phase && (
              <p className="phase-status" style={{ color: 'var(--text-muted)' }}>
                Failed during: {completion.phase}
              </p>
            )}
          </>
        )}
      </div>
    </div>
  )
}
