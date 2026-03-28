import { useState } from 'react'
import { useStore } from '../../store/index'
import * as api from '../../api/client'

export function WorkflowDecision() {
  const interaction = useStore(s => s.activeInteraction)
  const addNotification = useStore(s => s.addNotification)
  const [selectedPhase, setSelectedPhase] = useState<string | null>(null)
  const [context, setContext] = useState('')

  if (!interaction || interaction.type !== 'workflow-decision') return null

  const { chat_turns, token } = interaction

  const handleContinue = async () => {
    if (!selectedPhase) {
      addNotification({
        id: crypto.randomUUID(),
        type: 'validation',
        severity: 'warning',
        message: 'Please select a phase before continuing',
      })
      return
    }
    const res = await api.submitWorkflowDecision(selectedPhase, context, token)
    if (!res.ok) {
      addNotification({
        id: crypto.randomUUID(),
        type: 'submit_error',
        severity: 'error',
        message: res.message ?? 'Failed to submit decision',
      })
    }
  }

  return (
    <div className="phase-content">
      <div className="phase-inner">
        <div className="workflow-chat">
          {chat_turns.map((turn, i) => (
            <div key={i} className="workflow-turn">
              {turn.role === 'orchestrator' ? (
                <>
                  <div className="workflow-turn-orchestrator">
                    <div className="workflow-turn-header">
                      <span className="workflow-turn-role">Orchestrator</span>
                    </div>
                    <div className="workflow-turn-body">{turn.status_report}</div>
                  </div>
                  {turn.recommended_phases && turn.recommended_phases.length > 0 && (
                    <div className="workflow-options">
                      {turn.recommended_phases.map(rp => (
                        <button
                          key={rp.phase}
                          className={[
                            'workflow-option',
                            rp.recommended ? 'recommended' : '',
                            selectedPhase === rp.phase ? 'selected' : '',
                          ]
                            .filter(Boolean)
                            .join(' ')}
                          data-phase={rp.phase}
                          onClick={() => setSelectedPhase(rp.phase)}
                        >
                          <span className="workflow-option-label">{rp.phase}</span>
                          {rp.context && (
                            <span className="workflow-option-context">{rp.context}</span>
                          )}
                        </button>
                      ))}
                    </div>
                  )}
                </>
              ) : (
                <div className="workflow-turn-user">{turn.message}</div>
              )}
            </div>
          ))}

          <div className="workflow-chat-input">
            <textarea
              className="workflow-feedback"
              placeholder={
                selectedPhase
                  ? `Optional context for ${selectedPhase}...`
                  : 'Optional context for the chosen phase...'
              }
              value={context}
              onChange={e => setContext(e.target.value)}
            />
            <div className="form-actions">
              <button
                id="btn-workflow-continue"
                className="btn btn-primary"
                onClick={handleContinue}
              >
                Continue
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
