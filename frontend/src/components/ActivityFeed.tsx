import { useRef } from 'react'
import { useStore } from '../store/index'
import { useAutoScroll } from '../hooks/useAutoScroll'

export function ActivityFeed() {
  const activityLog = useStore(s => s.activityLog)
  const streamBuffer = useStore(s => s.streamBuffer)
  const isThinking = useStore(s => s.isThinking)
  const scrollRef = useRef<HTMLDivElement>(null)

  useAutoScroll(scrollRef)

  return (
    <div className="activity-feed-scroll" ref={scrollRef}>
      <div id="activity-feed-inner" className="activity-feed-inner">
        {/* Tool call entries — compact lines */}
        {activityLog.map((entry, i) => (
          <div
            key={i}
            className={[
              'activity-line',
              entry.inFlight ? 'activity-inflight' : 'activity-done',
            ]
              .filter(Boolean)
              .join(' ')}
          >
            <span className="activity-status">
              {entry.inFlight ? '›' : '✓'}
            </span>
            <span className="activity-tool">{entry.tool || ''}</span>
            <span className="activity-summary">
              {entry.summary || ''}
              {entry.inFlight && <span className="activity-dots">...</span>}
            </span>
          </div>
        ))}

        {/* Thinking indicator — shown when LLM is reasoning */}
        {isThinking && !streamBuffer && (
          <div className="activity-thinking-indicator">
            <span className="thinking-dot">●</span>
            <span>Thinking…</span>
          </div>
        )}

        {/* Stream output — wrapping text block for LLM output */}
        {streamBuffer && (
          <div className="stream-output">
            {streamBuffer}
            <span className="streaming-cursor" />
          </div>
        )}
      </div>
    </div>
  )
}
