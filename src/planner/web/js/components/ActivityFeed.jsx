import { useRef, useEffect, useState, useCallback } from 'preact/hooks'
import { useStore } from '../store.js'

function ThinkingTimer({ since }) {
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    const start = new Date(since).getTime()
    const tick = () => setElapsed(Math.floor((Date.now() - start) / 1000))
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [since])

  const text = elapsed < 60
    ? `${elapsed}s`
    : `${Math.floor(elapsed / 60)}m ${elapsed % 60}s`

  return <span class="thinking-timer">{text}</span>
}

/** Card for thinking entries — shows expandable thought content */
function ThinkingCard({ line, isInFlight, isFlashing }) {
  const [expanded, setExpanded] = useState(false)
  const bodyRef = useRef(null)
  const [isClamped, setIsClamped] = useState(false)

  // Detect whether the body text is actually clamped (more content than visible)
  useEffect(() => {
    const el = bodyRef.current
    if (el) setIsClamped(el.scrollHeight > el.clientHeight + 2)
  }, [line.body, expanded])

  // While in-flight with streaming body, treat as always expanded so the
  // user sees tokens appear. Clamping only applies to completed thoughts.
  const isStreaming = isInFlight && !!line.body
  const showExpanded = expanded || isStreaming

  const cls = [
    'activity-card',
    'activity-card-thinking',
    isInFlight  ? 'activity-card-active' : '',
    isFlashing  ? 'activity-flash' : '',
  ].filter(Boolean).join(' ')

  return (
    <div class={cls}>
      <div class="activity-card-header">
        <span class={`activity-card-tool${isInFlight ? ' thinking-dot' : ''}`}>thinking</span>
        <span class="activity-card-meta">
          {isInFlight
            ? <ThinkingTimer since={line.ts} />
            : line.summary
          }
        </span>
      </div>
      {line.body && (
        <>
          <div
            ref={bodyRef}
            class={`activity-card-body${showExpanded ? ' expanded' : ''}`}
          >
            {line.body}{isStreaming && <span class="streaming-cursor" />}
          </div>
          {(!isStreaming && isClamped && !expanded) && (
            <div class="activity-card-more" onClick={() => setExpanded(true)}>
              show more ▸
            </div>
          )}
          {(!isStreaming && expanded) && (
            <div class="activity-card-more" onClick={() => setExpanded(false)}>
              show less ▴
            </div>
          )}
        </>
      )}
    </div>
  )
}

/** Card for koan_request_scouts — shows dispatched scouts with name + role */
function ScoutCard({ line, isInFlight, isFlashing }) {
  const scouts = line.scouts || []
  const cls = [
    'activity-card',
    'activity-card-scouts',
    isInFlight  ? 'activity-card-active' : '',
    isFlashing  ? 'activity-flash' : '',
  ].filter(Boolean).join(' ')

  return (
    <div class={cls}>
      <div class="activity-card-header">
        <span class="activity-card-tool">
          dispatching {scouts.length} scout{scouts.length !== 1 ? 's' : ''}
        </span>
        {isInFlight && <span class="activity-card-meta"><span class="activity-dots">…</span></span>}
      </div>
      <div class="scout-list">
        {scouts.map((s, i) => (
          <div key={i} class="scout-entry">
            <span class="scout-name">{s.id}</span>
            <span class="scout-role">{s.role}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

/** Standard line for tool calls and lifecycle events */
function ActivityLine({ line, isInFlight, isFlashing }) {
  const cls = [
    'activity-line',
    line.highValue ? 'activity-high' : '',
    isInFlight     ? 'activity-inflight' : '',
    isFlashing     ? 'activity-flash' : '',
  ].filter(Boolean).join(' ')

  return (
    <>
      <div class={cls}>
        <span class="activity-tool">{line.tool}</span>
        <span class="activity-summary">
          {line.summary || ''}
          {isInFlight && <span class="activity-dots">...</span>}
        </span>
      </div>
      {line.details?.map((d, j) => (
        <div key={j} class={`activity-line activity-detail${isInFlight ? ' activity-inflight' : ''}`}>
          <span class="activity-tool" />
          <span class="activity-summary">{d}</span>
        </div>
      ))}
    </>
  )
}

export function ActivityFeed() {
  const logs = useStore(s => s.logs)
  const streamingText = useStore(s => s.streamingText)
  const containerRef = useRef(null)
  const stickRef = useRef(true)

  // Track previous last-line to detect in-flight → completed transitions.
  const prevLastRef = useRef(null)
  const [flashIndex, setFlashIndex] = useState(-1)

  // Auto-scroll to bottom when new logs arrive or streaming text grows,
  // but only if already at bottom.
  useEffect(() => {
    const el = containerRef.current
    if (el && stickRef.current) {
      el.scrollTop = el.scrollHeight
    }
  }, [logs, streamingText])

  // Detect when the last line transitions from in-flight to completed and flash it.
  useEffect(() => {
    const lastLine = logs[logs.length - 1]
    if (prevLastRef.current?.inFlight && lastLine && !lastLine.inFlight) {
      const idx = logs.length - 1
      setFlashIndex(idx)
      setTimeout(() => setFlashIndex(-1), 400)
    }
    prevLastRef.current = lastLine ? { ...lastLine } : null
  }, [logs])

  const onScroll = useCallback(() => {
    const el = containerRef.current
    if (!el) return
    stickRef.current = el.scrollTop + el.clientHeight >= el.scrollHeight - 30
  }, [])

  if (logs.length === 0) return null

  return (
    <div class="activity-feed-scroll" ref={containerRef} onScroll={onScroll}>
      <div class="activity-feed-inner">
        {logs.map((line, i) => {
          const isInFlight = !!line.inFlight && i === logs.length - 1
          const isFlashing = i === flashIndex

          if (line.tool === 'thinking') {
            // While in-flight, feed streaming tokens into the thinking card's
            // body so the user sees thinking text appear in realtime. When the
            // turn completes, the official thinking text from events.jsonl
            // replaces the streamed version via the normal audit poll path.
            const thinkingLine = (isInFlight && streamingText)
              ? { ...line, body: streamingText.replace(/\n{3,}/g, '\n\n') }
              : line
            return (
              <ThinkingCard
                key={i}
                line={thinkingLine}
                isInFlight={isInFlight}
                isFlashing={isFlashing}
              />
            )
          }

          if (line.scouts) {
            return (
              <ScoutCard
                key={i}
                line={line}
                isInFlight={isInFlight}
                isFlashing={isFlashing}
              />
            )
          }

          return (
            <ActivityLine
              key={i}
              line={line}
              isInFlight={isInFlight}
              isFlashing={isFlashing}
            />
          )
        })}
      </div>
    </div>
  )
}
