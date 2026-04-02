import { useState } from 'react'
import { useStore } from '../../store/index'
import * as api from '../../api/client'
import { Md } from '../Md'

export function ArtifactReview() {
  const focus = useStore(s => s.run?.focus)
  const [feedback, setFeedback] = useState('')
  const [submitError, setSubmitError] = useState<string | null>(null)

  if (!focus || focus.type !== 'review') return null

  const { content, description, token } = focus

  const handleAccept = async () => {
    const res = await api.submitArtifactReview('', true, token)
    if (!res.ok) {
      setSubmitError(res.message ?? 'Failed to accept artifact')
    }
  }

  const handleSendFeedback = async () => {
    const res = await api.submitArtifactReview(feedback, false, token)
    if (!res.ok) {
      setSubmitError(res.message ?? 'Failed to send feedback')
    }
  }

  return (
    <div className="phase-content">
      <div className="phase-inner">
        <h2 className="phase-heading">Artifact Review</h2>
        {description && <p className="phase-status">{description}</p>}

        <div className="artifact-review-content">
          <Md>{content}</Md>
        </div>

        <textarea
          id="artifact-review-textarea"
          className="artifact-review-feedback"
          placeholder="Optional feedback..."
          value={feedback}
          onChange={e => setFeedback(e.target.value)}
        />

        {submitError && <div className="no-runners-msg">{submitError}</div>}

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
