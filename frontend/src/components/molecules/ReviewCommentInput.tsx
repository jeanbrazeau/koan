import { useEffect, useRef, useState } from 'react'
import { useFileAttachment } from '../../hooks/useFileAttachment'
import { Button } from '../atoms/Button'
import { FileChip } from '../atoms/FileChip'
import './ReviewCommentInput.css'

interface ReviewCommentInputProps {
  onAdd: (text: string, attachments?: string[]) => void
  onCancel: () => void
}

const PaperclipIcon = () => (
  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.49" />
  </svg>
)

const UploadIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
    <polyline points="17 8 12 3 7 8" />
    <line x1="12" y1="3" x2="12" y2="15" />
  </svg>
)

export function ReviewCommentInput({ onAdd, onCancel }: ReviewCommentInputProps) {
  const [text, setText] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const attach = useFileAttachment()

  useEffect(() => {
    textareaRef.current?.focus()
  }, [])

  const handleAdd = () => {
    const ids = attach.fileIds.length > 0 ? attach.fileIds : undefined
    onAdd(text, ids)
    setText('')
    attach.clearFiles()
  }

  const cls = ['rci', attach.dragging && 'rci--dragging'].filter(Boolean).join(' ')

  return (
    <div className={cls} {...attach.dragProps}>
      {attach.dragging && (
        <div className="rci-drop-overlay">
          <UploadIcon />
          <span className="rci-drop-label">Drop to attach</span>
        </div>
      )}

      <div className="rci-textarea-wrap">
        <textarea
          ref={textareaRef}
          className="rci-textarea"
          value={text}
          onChange={e => setText(e.target.value)}
          onPaste={attach.onPaste}
          placeholder="Add a comment on this block..."
        />
        <button
          className="rci-attach-btn"
          onClick={attach.openPicker}
          title="Attach files"
          type="button"
        >
          <PaperclipIcon />
        </button>
        <input
          ref={attach.inputRef}
          type="file"
          multiple
          className="rci-file-input"
          onChange={attach.onInputChange}
          tabIndex={-1}
        />
      </div>

      {attach.files.length > 0 && (
        <div className="rci-chips">
          {attach.files.map(f => (
            <FileChip
              key={f.id}
              name={f.name}
              size={f.size}
              state={f.state}
              onRemove={() => attach.removeFile(f.id)}
            />
          ))}
        </div>
      )}

      <div className="rci-actions">
        <Button variant="secondary" size="xs" onClick={onCancel}>Cancel</Button>
        <Button variant="primary" size="xs" onClick={handleAdd}>Add comment</Button>
      </div>
    </div>
  )
}

export default ReviewCommentInput
