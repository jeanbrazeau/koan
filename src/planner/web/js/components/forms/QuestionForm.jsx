import { useState, useCallback } from 'preact/hooks'
import { useStore } from '../../store.js'
import { submitAnswers } from '../../lib/api.js'
import { QuestionCard } from './QuestionCard.jsx'

export function QuestionForm({ token }) {
  const { requestId, questions } = useStore(s => s.pendingInput)
  const total = questions.length

  // Collected answers: array of { questionId, selectedOptions, customInput? } or null
  const [answers, setAnswers] = useState(() => Array(total).fill(null))
  const [currentIndex, setCurrentIndex] = useState(0)
  // Per-question selection state (what the user has selected but not yet confirmed)
  const [selection, setSelection] = useState(null)

  const currentQuestion = questions[currentIndex]
  const currentAnswer = answers[currentIndex]
  const hasSelection = selection !== null && (selection.selectedOptions?.length > 0 || selection.customInput)

  // Confirm the current question's answer and advance
  const confirmAndNext = useCallback(() => {
    if (!hasSelection) return
    const answer = {
      questionId: currentQuestion.id,
      ...(selection || { selectedOptions: [] }),
    }
    const next = [...answers]
    next[currentIndex] = answer
    setAnswers(next)
    setSelection(null)

    if (currentIndex < total - 1) {
      setCurrentIndex(currentIndex + 1)
    }
  }, [hasSelection, selection, currentQuestion, answers, currentIndex, total])

  // Go back to a previous question
  const goBack = useCallback(() => {
    if (currentIndex > 0) {
      setSelection(null)
      setCurrentIndex(currentIndex - 1)
    }
  }, [currentIndex])

  // Submit all answers
  const submitAll = useCallback(() => {
    // For the current (last) question, include the current selection
    const finalAnswers = [...answers]
    if (hasSelection) {
      finalAnswers[currentIndex] = {
        questionId: currentQuestion.id,
        ...(selection || { selectedOptions: [] }),
      }
    }

    // Filter out any unanswered questions (shouldn't happen, but be safe)
    const validAnswers = finalAnswers.filter(Boolean)
    submitAnswers({ token, requestId, answers: validAnswers })
  }, [answers, hasSelection, currentIndex, currentQuestion, selection, token, requestId])

  // Use defaults for all questions
  function acceptDefaults() {
    const defaultAnswers = questions.map((q) => {
      const idx = q.recommended ?? 0
      const label = q.options[idx]?.label
      return {
        questionId: q.id,
        selectedOptions: label ? [label] : [],
      }
    })
    submitAnswers({ token, requestId, answers: defaultAnswers })
  }

  const isLast = currentIndex === total - 1
  const allPreviousAnswered = answers.slice(0, currentIndex).every(Boolean)
  // Can submit only if we're on the last question and all previous are answered and current has selection
  const canSubmit = isLast && allPreviousAnswered && (hasSelection || currentAnswer !== null)

  return (
    <div class="phase-inner">
      <h2 class="phase-heading">
        {total > 1 ? 'Questions to shape the plan' : 'A question to shape the plan'}
      </h2>

      {total > 1 && (
        <div class="count-progress">
          Question {currentIndex + 1} of {total}
        </div>
      )}

      <QuestionCard
        key={currentQuestion.id}
        question={currentQuestion}
        onSelect={setSelection}
      />

      {total > 1 && currentIndex > 0 && (
        <div class="context-section-label">Previously answered</div>
      )}
      {total > 1 && currentIndex > 0 && (
        <ul class="context-items">
          {answers.slice(0, currentIndex).filter(Boolean).map((a) => {
            const q = questions.find(qq => qq.id === a.questionId)
            const display = a.selectedOptions.length > 0
              ? a.selectedOptions.join(', ')
              : (a.customInput || '(no selection)')
            return <li key={a.questionId}><strong>{q?.id || a.questionId}:</strong> {display}</li>
          })}
        </ul>
      )}

      <div class="form-actions">
        {currentIndex > 0 && (
          <button class="btn btn-secondary" onClick={goBack}>← Back</button>
        )}
        <button class="btn btn-secondary" onClick={acceptDefaults}>Use Defaults</button>

        {!isLast ? (
          <button class="btn btn-primary" disabled={!hasSelection} onClick={confirmAndNext}>
            Next →
          </button>
        ) : (
          <button class="btn btn-primary" disabled={!canSubmit && !hasSelection} onClick={submitAll}>
            Submit {total > 1 ? 'All' : 'Answer'}
          </button>
        )}

        {!hasSelection && (
          <span class="form-helper">Choose an option or provide custom input</span>
        )}
      </div>
    </div>
  )
}
