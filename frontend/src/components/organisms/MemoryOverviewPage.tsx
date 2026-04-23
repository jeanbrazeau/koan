import './MemoryOverviewPage.css'
import type { ReactNode } from 'react'
import { useFileAttachment } from '../../hooks/useFileAttachment'
import TextInput from '../atoms/TextInput'
import { FileChip } from '../atoms/FileChip'
import Button from '../atoms/Button'
import StatStrip from '../molecules/StatStrip'
import ActivityRow from '../molecules/ActivityRow'
import MemorySidebar from './MemorySidebar'

type MemoryType = 'decision' | 'lesson' | 'context' | 'procedure'
type FilterValue = 'all' | MemoryType
type EntryOutline = 'cited' | 'retrieving' | 'outgoing' | 'incoming' | null

interface SidebarEntry {
  seq: string
  type: MemoryType
  title: string
  current?: boolean
  outline?: EntryOutline
  onClick?: () => void
}

interface Counts {
  entries: number
  decisions: number
  lessons: number
  context: number
  procedures: number
}

interface SummaryPanelProps {
  subtitle?: string
  children: ReactNode
}

interface ReflectStarterPanelProps {
  lead?: string
  placeholder?: string
  value: string
  onChange: (v: string) => void
  onAsk: (v: string, attachments?: string[]) => void
}

const PaperclipIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.49" />
  </svg>
)

interface MemoryOverviewPageProps {
  counts: Counts
  summarySubtitle?: string
  summary: ReactNode
  reflect: ReflectStarterPanelProps
  activity: { time: string; body: ReactNode }[]
  onSeeAllActivity?: () => void
  sidebar: {
    count: number
    search: string
    onSearchChange: (v: string) => void
    filter: FilterValue
    onFilterChange: (v: FilterValue) => void
    entries: SidebarEntry[]
    emptyHint?: string
  }
}

function SummaryPanel({ subtitle, children }: SummaryPanelProps) {
  return (
    <div className="mop-summary">
      <div className="mop-summary-eyebrow">Summary</div>
      {subtitle && <h2 className="mop-summary-subtitle">{subtitle}</h2>}
      <div className="mop-summary-body">{children}</div>
    </div>
  )
}

function ReflectStarterPanel({ lead, placeholder, value, onChange, onAsk }: ReflectStarterPanelProps) {
  const defaultLead = 'Ask anything about your memory -- what you\'ve decided, what you\'ve learned, and how it all connects.'
  const defaultPlaceholder = 'e.g. What\'s our testing strategy for LLM-driven code?'
  const attach = useFileAttachment()
  return (
    <div className="mop-reflect">
      <div className="mop-reflect-eyebrow">Reflect</div>
      <p className="mop-reflect-lead">{lead || defaultLead}</p>
      <div className="mop-reflect-spacer" />
      <label className="mop-reflect-sr-only" htmlFor="reflect-input">Reflect question</label>
      <div className="mop-reflect-textarea-wrap" {...attach.dragProps}>
        <TextInput
          as="textarea"
          value={value}
          onChange={onChange}
          placeholder={placeholder || defaultPlaceholder}
          className="mop-reflect-textarea"
        />
        <button className="mop-reflect-attach-btn" onClick={attach.openPicker} title="Attach files" type="button">
          <PaperclipIcon />
        </button>
        <input ref={attach.inputRef} type="file" multiple className="mop-reflect-file-input" onChange={attach.onInputChange} tabIndex={-1} />
      </div>
      {attach.files.length > 0 && (
        <div className="mop-reflect-chips">
          {attach.files.map(f => (
            <FileChip key={f.id} name={f.name} size={f.size} state={f.state} onRemove={() => attach.removeFile(f.id)} />
          ))}
        </div>
      )}
      <div className="mop-reflect-actions">
        <Button
          variant="primary"
          size="sm"
          disabled={!value.trim()}
          onClick={() => {
            const ids = attach.fileIds.length > 0 ? attach.fileIds : undefined
            onAsk(value, ids)
          }}
        >
          Ask {'\u2192'}
        </Button>
      </div>
    </div>
  )
}

export function MemoryOverviewPage({
  counts,
  summarySubtitle,
  summary,
  reflect,
  activity,
  onSeeAllActivity,
  sidebar,
}: MemoryOverviewPageProps) {
  const statCells = [
    { value: String(counts.entries), label: 'entries' },
    { value: String(counts.decisions), label: 'decisions' },
    { value: String(counts.lessons), label: 'lessons' },
    { value: String(counts.context), label: 'context' },
    { value: String(counts.procedures), label: 'procedures' },
  ]

  return (
    <div className="mop">
      <main>
        <div className="mop-head">
          <h1 className="mop-title">Memory</h1>
          <span className="mop-count-meta">
            {counts.entries} entries &middot; {counts.decisions} decisions &middot; {counts.lessons} lessons
          </span>
        </div>

        <div className="mop-split">
          <SummaryPanel subtitle={summarySubtitle}>{summary}</SummaryPanel>
          <ReflectStarterPanel {...reflect} />
        </div>

        <div className="mop-stats">
          <StatStrip cells={statCells} size="lg" dividers />
        </div>

        <div className="mop-activity">
          <div className="mop-activity-head">
            <span className="mop-activity-label">Recent activity</span>
            {onSeeAllActivity && (
              <Button variant="text" onClick={onSeeAllActivity}>See all {'\u2192'}</Button>
            )}
          </div>
          {activity.length === 0 ? (
            <div className="mop-activity-empty">No recent activity.</div>
          ) : (
            <div className="mop-activity-list">
              {activity.map((a, i) => (
                <ActivityRow key={i} time={a.time} body={a.body} />
              ))}
            </div>
          )}
        </div>
      </main>

      <MemorySidebar {...sidebar} />
    </div>
  )
}

export default MemoryOverviewPage
