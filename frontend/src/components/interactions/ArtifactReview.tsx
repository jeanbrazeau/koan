import { useState } from 'react'
import { useStore } from '../../store/index'
import * as api from '../../api/client'

export function ArtifactReview() {
  const interaction = useStore(s => s.activeInteraction)
  const addNotification = useStore(s => s.addNotification)
  const [feedback, setFeedback] = useState('')

  if (!interaction || interaction.type !== 'artifact-review') return null

  const { content, description, token } = interaction

  const handleAccept = async () => {
    const res = await api.submitArtifactReview('', true, token)
    if (!res.ok) {
      addNotification({
        id: crypto.randomUUID(),
        type: 'submit_error',
        severity: 'error',
        message: res.message ?? 'Failed to accept artifact',
      })
    }
  }

  const handleSendFeedback = async () => {
    const res = await api.submitArtifactReview(feedback, false, token)
    if (!res.ok) {
      addNotification({
        id: crypto.randomUUID(),
        type: 'submit_error',
        severity: 'error',
        message: res.message ?? 'Failed to send feedback',
      })
    }
  }

  return (
    <div className="phase-content">
      <div className="phase-inner">
        <h2 className="phase-heading">Artifact Review</h2>
        {description && <p className="phase-status">{description}</p>}

        <div className="artifact-review-content">
          <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
            {content}
          </pre>
        </div>

        <textarea
          id="artifact-review-textarea"
          className="artifact-review-feedback"
          placeholder="Optional feedback..."
          value={feedback}
          onChange={e => setFeedback(e.target.value)}
        />

        <div className="form-actions">
          <button
            id="btn-send-feedback"
            className="btn btn-secondary"
            onClick={handleSendFeedback}
          >
            Send Feedback
          </button>
          <button
            id="btn-accept-artifact"
            className="btn btn-primary"
            onClick={handleAccept}
          >
            Accept
          </button>
        </div>
      </div>
    </div>
  )
}
