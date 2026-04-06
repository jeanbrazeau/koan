/**
 * NewRunForm — standalone form page for starting a new koan run.
 *
 * Centered column of form sections: workflow selection, description
 * textarea, configuration (profile, agent, concurrency), and a
 * submit button. No sidebar, no scout bar.
 *
 * Used in: landing page when no run is active.
 */

import { SectionLabel } from '../atoms/SectionLabel'
import { Button } from '../atoms/Button'
import { Badge } from '../atoms/Badge'
import { StatusDot } from '../atoms/StatusDot'
import './NewRunForm.css'

interface NewRunFormProps {
  projectPath: string
  description: string
  onDescriptionChange: (text: string) => void
  workflow: 'plan' | 'milestones'
  onWorkflowChange: (workflow: 'plan' | 'milestones') => void
  profile: string
  agentName: string
  agentInstallation: string
  scoutConcurrency: number
  onScoutConcurrencyChange: (n: number) => void
  onSubmit: () => void
}

const ChevronDown = () => (
  <svg width="12" height="8" viewBox="0 0 12 8" fill="none" aria-hidden="true">
    <path d="M1 1l5 5 5-5" stroke="var(--text-muted)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
)

export function NewRunForm({
  projectPath, description, onDescriptionChange,
  workflow, onWorkflowChange,
  profile, agentName, agentInstallation,
  scoutConcurrency, onScoutConcurrencyChange,
  onSubmit,
}: NewRunFormProps) {
  return (
    <div className="nrf">
      {/* Title + project */}
      <div className="nrf-header">
        <h1 className="nrf-title">New Run</h1>
        <div className="nrf-project">{projectPath}</div>
      </div>

      {/* Workflow */}
      <div className="nrf-card">
        <SectionLabel>Workflow</SectionLabel>
        <div className="nrf-wf-grid">
          <button
            className={`nrf-wf-option${workflow === 'plan' ? ' nrf-wf-option--selected' : ''}`}
            onClick={() => onWorkflowChange('plan')}
          >
            <span className={`nrf-wf-radio${workflow === 'plan' ? ' nrf-wf-radio--selected' : ''}`}>
              {workflow === 'plan' && <span className="nrf-wf-radio-inner" />}
            </span>
            <span className="nrf-wf-info">
              <span className="nrf-wf-name">Plan</span>
              <span className="nrf-wf-desc">Plan an approach, review it, then execute</span>
            </span>
          </button>
          <button className="nrf-wf-option nrf-wf-option--disabled" disabled>
            <span className="nrf-wf-radio" />
            <span className="nrf-wf-info">
              <span className="nrf-wf-name">
                Milestones <Badge variant="neutral">coming soon</Badge>
              </span>
              <span className="nrf-wf-desc">Break work into milestones with phased delivery</span>
            </span>
          </button>
        </div>
      </div>

      {/* Description */}
      <div className="nrf-card">
        <SectionLabel>Description</SectionLabel>
        <div className="nrf-helper">What should this run accomplish?</div>
        <textarea
          className="nrf-textarea"
          value={description}
          onChange={e => onDescriptionChange(e.target.value)}
          rows={4}
        />
      </div>

      {/* Configuration */}
      <div className="nrf-card">
        <SectionLabel>Configuration</SectionLabel>
        <div className="nrf-config-fields">
          {/* Profile */}
          <div className="nrf-field">
            <div className="nrf-field-label">Profile</div>
            <div className="nrf-select">
              <span>{profile}</span>
              <ChevronDown />
            </div>
          </div>

          {/* Agent */}
          <div className="nrf-field">
            <div className="nrf-field-label">Agent Installations</div>
            <div className="nrf-agent-row">
              <span className="nrf-agent-chip">
                <span className="nrf-agent-name">{agentName}</span>
                <StatusDot status="done" size="sm" />
              </span>
              <div className="nrf-select nrf-select--flex">
                <span>{agentInstallation}</span>
                <ChevronDown />
              </div>
            </div>
          </div>

          {/* Scout concurrency */}
          <div className="nrf-field">
            <div className="nrf-field-label">Scout Concurrency</div>
            <div className="nrf-concurrency-row">
              <input
                className="nrf-concurrency-input"
                type="number"
                min={1}
                max={32}
                value={scoutConcurrency}
                onChange={e => onScoutConcurrencyChange(parseInt(e.target.value, 10) || 1)}
              />
              <span className="nrf-concurrency-hint">max parallel scout agents</span>
            </div>
          </div>
        </div>
      </div>

      {/* Submit */}
      <Button variant="primary" onClick={onSubmit}>Start Run</Button>
    </div>
  )
}

export default NewRunForm
