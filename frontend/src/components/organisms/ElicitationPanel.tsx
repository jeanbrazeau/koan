/**
 * ElicitationPanel — two-panel context/decision layout for the Deepen step.
 *
 * Presents gathered context alongside a question with selectable options.
 * Fully controlled — parent manages selection state and actions.
 *
 * Used in: elicitation interactions during the Deepen intake step.
 */

import type { ReactNode } from 'react'
import { SectionLabel } from '../atoms/SectionLabel'
import { Button } from '../atoms/Button'
import { RadioOption } from '../molecules/RadioOption'
import './ElicitationPanel.css'

interface OptionEntry {
  label: string
  recommended?: boolean
  isCustom?: boolean
}

interface ElicitationPanelProps {
  context: ReactNode
  question: string
  options: OptionEntry[]
  selectedIndex: number | null
  customText?: string
  onSelect: (index: number) => void
  onCustomTextChange?: (text: string) => void
  onSubmit: () => void
  onUseDefaults: () => void
  questionNumber?: string
}

export function ElicitationPanel({
  context,
  question,
  options,
  selectedIndex,
  customText,
  onSelect,
  onCustomTextChange,
  onSubmit,
  onUseDefaults,
  questionNumber,
}: ElicitationPanelProps) {
  return (
    <div className="ep">
      {questionNumber && (
        <div className="ep-counter">{questionNumber}</div>
      )}
      <div className="ep-grid">
        {/* Context panel */}
        <div className="ep-panel ep-panel--context">
          <SectionLabel color="teal">Context</SectionLabel>
          <div className="ep-panel-body">{context}</div>
        </div>

        {/* Decision panel */}
        <div className="ep-panel ep-panel--decision">
          <SectionLabel color="orange">Decision</SectionLabel>
          <div className="ep-question">{question}</div>
          <div className="ep-options">
            {options.map((opt, i) => (
              <RadioOption
                key={i}
                label={opt.label}
                selected={selectedIndex === i}
                recommended={opt.recommended}
                isCustom={opt.isCustom}
                customText={opt.isCustom ? customText : undefined}
                onCustomTextChange={opt.isCustom ? onCustomTextChange : undefined}
                onClick={() => onSelect(i)}
              />
            ))}
          </div>
          <div className="ep-actions">
            <Button variant="secondary" onClick={onUseDefaults}>Use Defaults</Button>
            <Button variant="primary" onClick={onSubmit}>Next</Button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default ElicitationPanel
