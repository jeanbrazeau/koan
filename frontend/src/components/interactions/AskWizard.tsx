import { useState } from 'react'
import { useStore, AskQuestion } from '../../store/index'
import * as api from '../../api/client'
import { Md } from '../Md'

// Normalize raw question options from LLM output. Options may arrive as strings
// or dicts with varying key names. This is data cleaning for LLM output
// variability — not business logic.
function normalizeOptions(
  rawOpts: (string | Record<string, unknown>)[] | undefined,
): { value: string; label: string; recommended?: boolean }[] {
  if (!rawOpts) return []
  return rawOpts.map(o => {
    if (typeof o === 'string') return { value: o, label: o }
    const label = String(o['label'] ?? o['text'] ?? o['value'] ?? o['option'] ?? '')
    const value = String(o['value'] ?? o['label'] ?? o['text'] ?? label)
    return { value, label, recommended: (o['recommended'] as boolean) ?? false }
  })
}

interface AnswerMap {
  [qIdx: number]: string | string[] | null
}

function collectDefaults(questions: AskQuestion[]): AnswerMap {
  const defaults: AnswerMap = {}
  questions.forEach((q, i) => {
    const recommended = q.options.filter(o => o.recommended).map(o => o.value)
    defaults[i] = q.multi ? recommended : (recommended[0] ?? null)
  })
  return defaults
}

function QuestionCard({
  question,
  qIdx,
  answer,
  onAnswer,
}: {
  question: AskQuestion
  qIdx: number
  answer: string | string[] | null
  onAnswer: (qIdx: number, val: string | string[] | null) => void
}) {
  const [otherText, setOtherText] = useState('')
  const selected = Array.isArray(answer) ? answer : answer ? [answer] : []

  const toggle = (value: string) => {
    if (value === '__other__') {
      if (question.multi) {
        const newSel = selected.includes('__other__')
          ? selected.filter(v => v !== '__other__')
          : [...selected, '__other__']
        onAnswer(qIdx, newSel)
      } else {
        onAnswer(qIdx, selected[0] === '__other__' ? null : '__other__')
      }
      return
    }
    if (question.multi) {
      const newSel = selected.includes(value)
        ? selected.filter(v => v !== value)
        : [...selected, value]
      onAnswer(qIdx, newSel)
    } else {
      onAnswer(qIdx, selected[0] === value ? null : value)
    }
  }

  // Normalize options at render time to handle LLM output variability
  const opts = normalizeOptions(question.options as (string | Record<string, unknown>)[])

  return (
    <div className="question-card">
      <div className="question-header">
        Question {qIdx + 1}
      </div>
      {question.context && (
        <div className="question-context"><Md>{question.context}</Md></div>
      )}
      <div className="question-text"><Md>{question.question}</Md></div>
      {question.multi && (
        <div className="question-multi-hint">Select all that apply</div>
      )}
      <div className="options-list">
        {opts.map(opt => (
          <div
            key={opt.value}
            className={`option${selected.includes(opt.value) ? ' selected' : ''}${opt.recommended ? ' recommended' : ''}`}
            onClick={() => toggle(opt.value)}
          >
            <span className={question.multi ? 'checkbox-dot' : 'radio-dot'} />
            <span className="option-text">{opt.label}</span>
            {opt.recommended && (
              <span className="recommended-badge">recommended</span>
            )}
          </div>
        ))}
        {question.allow_other && (
          <div
            className={`option option-other${selected.includes('__other__') ? ' selected' : ''}`}
            onClick={() => toggle('__other__')}
          >
            <span className={question.multi ? 'checkbox-dot' : 'radio-dot'} />
            <span className="option-text">Other (type your own)</span>
            {selected.includes('__other__') && (
              <input
                type="text"
                className="other-input visible"
                placeholder="Type here..."
                value={otherText}
                onChange={e => setOtherText(e.target.value)}
                onClick={e => e.stopPropagation()}
              />
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export function AskWizard() {
  const focus = useStore(s => s.run?.focus)
  const [currentIdx, setCurrentIdx] = useState(0)
  const [answers, setAnswers] = useState<AnswerMap>({})
  const [submitError, setSubmitError] = useState<string | null>(null)

  if (!focus || focus.type !== 'question') return null

  const { questions, token } = focus
  const total = questions.length

  const handleAnswer = (qIdx: number, val: string | string[] | null) => {
    setAnswers(prev => ({ ...prev, [qIdx]: val }))
  }

  const handleNext = () => {
    if (currentIdx < total - 1) setCurrentIdx(i => i + 1)
  }

  const handleBack = () => {
    if (currentIdx > 0) setCurrentIdx(i => i - 1)
  }

  const handleSubmit = async () => {
    const finalAnswers = questions.map((_, i) => answers[i] ?? null)
    const res = await api.submitAnswer(finalAnswers, token)
    if (!res.ok) {
      setSubmitError(res.message ?? 'Failed to submit answers')
    }
  }

  const handleUseDefaults = async () => {
    const defaults = collectDefaults(questions)
    const finalAnswers = questions.map((_, i) => defaults[i] ?? null)
    const res = await api.submitAnswer(finalAnswers, token)
    if (!res.ok) {
      setSubmitError(res.message ?? 'Failed to submit defaults')
    }
  }

  return (
    <div className="phase-content">
      <div className="phase-inner">
        <div className="count-progress">
          {currentIdx + 1} / {total}
        </div>

        <QuestionCard
          key={currentIdx}
          question={questions[currentIdx]}
          qIdx={currentIdx}
          answer={answers[currentIdx] ?? null}
          onAnswer={handleAnswer}
        />

        {submitError && <div className="no-runners-msg">{submitError}</div>}

        <div className="form-actions">
          {currentIdx > 0 && (
            <button className="btn btn-secondary" onClick={handleBack}>
              Back
            </button>
          )}
          <button className="btn btn-secondary" onClick={handleUseDefaults}>
            Use Defaults
          </button>
          {currentIdx < total - 1 && (
            <button className="btn btn-primary" onClick={handleNext}>
              Next
            </button>
          )}
          {currentIdx === total - 1 && (
            <button
              id="btn-submit-answers"
              className="btn btn-primary"
              onClick={handleSubmit}
            >
              Submit
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
