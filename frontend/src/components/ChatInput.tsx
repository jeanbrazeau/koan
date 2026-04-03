import { useState, KeyboardEvent } from 'react'
import { useStore } from '../store/index'
import { sendChatMessage } from '../api/client'

export function ChatInput() {
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)

  const run = useStore(s => s.run)
  const isDisabled = !run || run.completion !== null || sending

  async function handleSend() {
    const msg = text.trim()
    if (!msg || isDisabled) return

    setSending(true)
    try {
      await sendChatMessage(msg)
      setText('')
    } catch (e) {
      // Silently ignore network errors; message may still be buffered
    } finally {
      setSending(false)
    }
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="chat-input">
      <textarea
        className="chat-input-textarea"
        value={text}
        onChange={e => setText(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={isDisabled ? 'No active run' : 'Message the orchestrator… (Enter to send, Shift+Enter for newline)'}
        disabled={isDisabled}
        rows={2}
      />
      <button
        className="chat-input-send"
        onClick={handleSend}
        disabled={isDisabled || !text.trim()}
      >
        Send
      </button>
    </div>
  )
}
