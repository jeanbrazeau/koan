import { useRef } from 'react'
import { useStore } from '../store/index'
import { useAutoScroll } from '../hooks/useAutoScroll'

export function ActivityFeed() {
  const activityLog = useStore(s => s.activityLog)
  const streamBuffer = useStore(s => s.streamBuffer)
  const scrollRef = useRef<HTMLDivElement>(null)

  useAutoScroll(scrollRef)

  return (
    <div className="activity-feed-scroll" ref={scrollRef}>
      <div id="activity-feed-inner" className="activity-feed-inner">
        {activityLog.map((entry, i) => (
          <div
            key={i}
            className={[
              'activity-line',
              entry.inFlight ? 'activity-inflight' : '',
            ]
              .filter(Boolean)
              .join(' ')}
          >
            <span className="activity-tool">{entry.tool || ''}</span>
            <span className="activity-summary">
              {entry.summary || ''}
              {entry.inFlight && <span className="activity-dots">...</span>}
            </span>
          </div>
        ))}

        {streamBuffer && (
          <div className="activity-line activity-inflight">
            <span className="activity-tool thinking-dot">&#8226;</span>
            <span className="activity-summary">
              {streamBuffer}
              <span className="streaming-cursor" />
            </span>
          </div>
        )}
      </div>
    </div>
  )
}
