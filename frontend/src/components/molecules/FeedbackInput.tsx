/**
 * FeedbackInput — text input for sending feedback/messages to the agent.
 *
 * Sits at the bottom of the content stream. Enter sends, Shift+Enter
 * inserts a newline. Uses the Button atom for the send action.
 *
 * Used in: activity feed footer, phase-boundary prompts.
 */

import { useState, useRef, type KeyboardEvent } from 'react'
import { Button } from '../atoms/Button'
import './FeedbackInput.css'

interface FeedbackInputProps {
  placeholder?: string
  onSend?: (text: string) => void
  disabled?: boolean
}

export function FeedbackInput({
  placeholder = 'Send feedback...',
  onSend,
  disabled = false,
}: FeedbackInputProps) {
  const [text, setText] = useState('')
  const ref = useRef<HTMLTextAreaElement>(null)

  const send = () => {
    const trimmed = text.trim()
    if (!trimmed || disabled) return
    onSend?.(trimmed)
    setText('')
    ref.current?.focus()
  }

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  return (
    <div className={`fi${disabled ? ' fi--disabled' : ''}`}>
      <textarea
        ref={ref}
        className="fi-textarea"
        placeholder={placeholder}
        value={text}
        onChange={e => setText(e.target.value)}
        onKeyDown={onKey}
        disabled={disabled}
        rows={1}
      />
      <div className="fi-footer">
        <span className="fi-hint">Enter to send · Shift+Enter for newline</span>
        <Button
          variant="primary"
          size="sm"
          onClick={send}
          disabled={disabled || !text.trim()}
        >
          Send
        </Button>
      </div>
    </div>
  )
}

export default FeedbackInput
