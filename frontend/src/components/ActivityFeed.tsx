import { useRef, useState } from 'react'
import { useStore, ActivityEntry } from '../store/index'
import { useAutoScroll } from '../hooks/useAutoScroll'
import { useElapsedBetween } from '../hooks/useElapsed'

// -- Thinking ------------------------------------------------------------------

function ThinkingCard({ entry }: { entry: ActivityEntry }) {
  const [expanded, setExpanded] = useState(false)
  const elapsed = useElapsedBetween(entry.thinkingStartedAt, entry.thinkingEndedAt)
  const content = entry.thinkingContent || ''
  const isLong = content.length > 300

  return (
    <div className="activity-card activity-card-thinking">
      <div className="activity-card-header">
        <span className="activity-card-tool">thinking</span>
        {elapsed && <span className="activity-card-meta thinking-timer">{elapsed}</span>}
      </div>
      {content && (
        <div className={`activity-card-body ${expanded ? 'expanded' : ''}`}>
          {content}
        </div>
      )}
      {isLong && !expanded && (
        <div className="activity-card-more" onClick={() => setExpanded(true)}>
          show more
        </div>
      )}
    </div>
  )
}

function ActiveThinkingCard() {
  const thinkingBuffer = useStore(s => s.thinkingBuffer)
  const thinkingStartedAt = useStore(s => s.thinkingStartedAt)
  const elapsed = useElapsedBetween(thinkingStartedAt, null)

  if (!thinkingBuffer) return null

  return (
    <div className="activity-card activity-card-thinking activity-card-active">
      <div className="activity-card-header">
        <span className="activity-card-tool">thinking</span>
        {elapsed && <span className="activity-card-meta thinking-timer">{elapsed}</span>}
      </div>
      <div className="activity-card-body expanded">
        {thinkingBuffer}
      </div>
    </div>
  )
}

// -- Step header ---------------------------------------------------------------

function StepHeader({ entry }: { entry: ActivityEntry }) {
  const label = entry.totalSteps
    ? `step ${entry.step}/${entry.totalSteps}`
    : `step ${entry.step}`

  return (
    <div className="step-header">
      <span className="step-header-label">{label}</span>
      {entry.stepName && <span className="step-header-name">{entry.stepName}</span>}
    </div>
  )
}

// -- Text block ----------------------------------------------------------------

function TextBlock({ entry }: { entry: ActivityEntry }) {
  return (
    <div className="stream-output">
      {entry.textContent}
    </div>
  )
}

// -- Tool lines ----------------------------------------------------------------

function statusIcon(inFlight: boolean) {
  return inFlight ? '›' : '✓'
}

function statusClass(inFlight: boolean) {
  return inFlight ? 'activity-inflight' : 'activity-done'
}

function ToolLine({ entry }: { entry: ActivityEntry }) {
  return (
    <div className={`activity-line ${statusClass(entry.inFlight)}`}>
      <span className="activity-status">{statusIcon(entry.inFlight)}</span>
      <span className="activity-tool">{entry.tool || ''}</span>
      <span className="activity-summary">
        {entry.summary || ''}
        {entry.inFlight && <span className="activity-dots">...</span>}
      </span>
    </div>
  )
}

function ReadLine({ entry }: { entry: ActivityEntry }) {
  const detail = entry.lines ? `${entry.file}:${entry.lines}` : (entry.file || '')
  return (
    <div className={`activity-line ${statusClass(entry.inFlight)}`}>
      <span className="activity-status">{statusIcon(entry.inFlight)}</span>
      <span className="activity-tool">read</span>
      <span className="activity-detail">{detail}</span>
      {entry.inFlight && <span className="activity-dots">...</span>}
    </div>
  )
}

function WriteLine({ entry }: { entry: ActivityEntry }) {
  return (
    <div className={`activity-line ${statusClass(entry.inFlight)}`}>
      <span className="activity-status">{statusIcon(entry.inFlight)}</span>
      <span className="activity-tool">write</span>
      <span className="activity-detail">{entry.file || ''}</span>
      {entry.inFlight && <span className="activity-dots">...</span>}
    </div>
  )
}

function EditLine({ entry }: { entry: ActivityEntry }) {
  return (
    <div className={`activity-line ${statusClass(entry.inFlight)}`}>
      <span className="activity-status">{statusIcon(entry.inFlight)}</span>
      <span className="activity-tool">edit</span>
      <span className="activity-detail">{entry.file || ''}</span>
      {entry.inFlight && <span className="activity-dots">...</span>}
    </div>
  )
}

function BashLine({ entry }: { entry: ActivityEntry }) {
  return (
    <div className={`activity-line ${statusClass(entry.inFlight)}`}>
      <span className="activity-status">{statusIcon(entry.inFlight)}</span>
      <span className="activity-tool">bash</span>
      <span className="activity-detail">{entry.command || ''}</span>
      {entry.inFlight && <span className="activity-dots">...</span>}
    </div>
  )
}

function GrepLine({ entry }: { entry: ActivityEntry }) {
  return (
    <div className={`activity-line ${statusClass(entry.inFlight)}`}>
      <span className="activity-status">{statusIcon(entry.inFlight)}</span>
      <span className="activity-tool">grep</span>
      <span className="activity-detail">{entry.pattern || ''}</span>
      {entry.inFlight && <span className="activity-dots">...</span>}
    </div>
  )
}

function LsLine({ entry }: { entry: ActivityEntry }) {
  return (
    <div className={`activity-line ${statusClass(entry.inFlight)}`}>
      <span className="activity-status">{statusIcon(entry.inFlight)}</span>
      <span className="activity-tool">ls</span>
      <span className="activity-detail">{entry.path || ''}</span>
      {entry.inFlight && <span className="activity-dots">...</span>}
    </div>
  )
}

// -- Feed ----------------------------------------------------------------------

function renderEntry(entry: ActivityEntry, i: number) {
  switch (entry.type) {
    case 'thinking':   return <ThinkingCard key={i} entry={entry} />
    case 'step':       return <StepHeader   key={i} entry={entry} />
    case 'text':       return <TextBlock    key={i} entry={entry} />
    case 'tool_read':  return <ReadLine     key={i} entry={entry} />
    case 'tool_write': return <WriteLine    key={i} entry={entry} />
    case 'tool_edit':  return <EditLine     key={i} entry={entry} />
    case 'tool_bash':  return <BashLine     key={i} entry={entry} />
    case 'tool_grep':  return <GrepLine     key={i} entry={entry} />
    case 'tool_ls':    return <LsLine       key={i} entry={entry} />
    default:           return <ToolLine     key={i} entry={entry} />
  }
}

export function ActivityFeed() {
  const activityLog = useStore(s => s.activityLog)
  const streamBuffer = useStore(s => s.streamBuffer)
  const isThinking = useStore(s => s.isThinking)
  const thinkingBuffer = useStore(s => s.thinkingBuffer)
  const scrollRef = useRef<HTMLDivElement>(null)

  useAutoScroll(scrollRef)

  return (
    <div className="activity-feed-scroll" ref={scrollRef}>
      <div id="activity-feed-inner" className="activity-feed-inner">
        {activityLog.map(renderEntry)}

        {/* Active thinking card — shown while LLM is reasoning */}
        {isThinking && thinkingBuffer && <ActiveThinkingCard />}

        {/* Thinking indicator — no content yet */}
        {isThinking && !thinkingBuffer && (
          <div className="activity-thinking-indicator">
            <span className="thinking-dot">●</span>
            <span>Thinking…</span>
          </div>
        )}

        {/* Active stream output — text being produced right now */}
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
