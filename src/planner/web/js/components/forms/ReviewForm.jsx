import { useState, useRef, useEffect } from 'preact/hooks'
import { useStore } from '../../store.js'
import { submitReview } from '../../lib/api.js'

function StoryCard({ story, isApproved, onToggle }) {
  const [expanded, setExpanded] = useState(false)
  const bodyRef = useRef(null)
  const [isClamped, setIsClamped] = useState(false)

  useEffect(() => {
    const el = bodyRef.current
    if (el) setIsClamped(el.scrollHeight > el.clientHeight + 2)
  }, [story.content, expanded])

  function handleCheckbox(e) {
    e.stopPropagation()
    onToggle()
  }

  function handleExpand() {
    if (story.content) setExpanded(v => !v)
  }

  return (
    <div class={`review-card ${isApproved ? 'review-card-approved' : ''}`}>
      <div class="review-card-header" onClick={handleExpand}>
        <div class="review-card-checkbox" onClick={handleCheckbox}>
          <div class={`review-checkbox ${isApproved ? 'checked' : ''}`} />
        </div>
        <div class="review-card-title">
          <span class="review-card-id">{story.storyId}</span>
          <span class="review-card-desc">{story.title}</span>
        </div>
        {story.content && (
          <span class="review-card-chevron">{expanded ? '▾' : '▸'}</span>
        )}
      </div>
      {story.content && (
        <>
          <div
            ref={bodyRef}
            class={`review-card-body${expanded ? ' expanded' : ''}`}
          >
            {story.content}
          </div>
          {!expanded && isClamped && (
            <div class="review-card-more" onClick={handleExpand}>
              show spec ▸
            </div>
          )}
        </>
      )}
    </div>
  )
}

export function ReviewForm({ token }) {
  const { requestId, payload: stories } = useStore(s => s.pendingInput)
  const [approved, setApproved] = useState(() => new Set(stories.map(s => s.storyId)))

  function toggle(storyId) {
    setApproved(prev => {
      const next = new Set(prev)
      if (next.has(storyId)) next.delete(storyId)
      else next.add(storyId)
      return next
    })
  }

  function approveAll() {
    setApproved(new Set(stories.map(s => s.storyId)))
  }

  function submit() {
    const approvedList = stories.filter(s => approved.has(s.storyId)).map(s => s.storyId)
    const skippedList  = stories.filter(s => !approved.has(s.storyId)).map(s => s.storyId)
    submitReview({ token, requestId, approved: approvedList, skipped: skippedList })
  }

  return (
    <div class="phase-inner">
      <h2 class="phase-heading">Review story sketches</h2>
      <p class="phase-status">
        Review stories before execution begins. Click a story to inspect its specification.
      </p>

      {stories.map(story => (
        <StoryCard
          key={story.storyId}
          story={story}
          isApproved={approved.has(story.storyId)}
          onToggle={() => toggle(story.storyId)}
        />
      ))}

      <div class="form-actions">
        <button class="btn btn-secondary" onClick={approveAll}>Approve All</button>
        <button class="btn btn-primary" onClick={submit}>Submit</button>
      </div>
    </div>
  )
}
