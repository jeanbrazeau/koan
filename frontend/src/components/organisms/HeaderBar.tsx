/**
 * HeaderBar — the fixed navy bar at the top of every view.
 *
 * Contains the logo mark + wordmark, a vertical divider, breadcrumb
 * navigation with progress segments, orchestrator status, elapsed
 * time, and a settings button.
 *
 * Used in: app shell, rendered above all content views.
 */

import { LogoMark } from '../atoms/LogoMark'
import { StatusDot } from '../atoms/StatusDot'
import { BreadcrumbNav } from '../molecules/BreadcrumbNav'
import './HeaderBar.css'

interface HeaderBarProps {
  phase: string
  step: string
  totalSteps: number
  currentStep: number
  orchestratorModel?: string
  elapsed?: string
  onSettingsClick?: () => void
}

const GearIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <circle cx="12" cy="12" r="3"
      stroke="rgba(240,232,216,0.6)" strokeWidth="2" /* warm off-white gear stroke — from design-system.md header spec */ />
    <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"
      stroke="rgba(240,232,216,0.6)" strokeWidth="2" strokeLinecap="round" /* same warm off-white */ />
  </svg>
)

export function HeaderBar({
  phase,
  step,
  totalSteps,
  currentStep,
  orchestratorModel = 'opus',
  elapsed,
  onSettingsClick,
}: HeaderBarProps) {
  return (
    <header className="hb">
      <div className="hb-inner">
      <div className="hb-left">
        <div className="hb-logo">
          <LogoMark />
          <span className="hb-wordmark">koan</span>
        </div>
        <span className="hb-divider" />
        <BreadcrumbNav
          phase={phase}
          step={step}
          totalSteps={totalSteps}
          currentStep={currentStep}
        />
      </div>

      <div className="hb-right">
        <div className="hb-orchestrator">
          <StatusDot status="done" size="sm" />
          <span className="hb-model">{orchestratorModel}</span>
        </div>
        {elapsed && <span className="hb-elapsed">{elapsed}</span>}
        <button
          className="hb-settings"
          onClick={onSettingsClick}
          aria-label="Settings"
        >
          <GearIcon />
        </button>
      </div>
      </div>
    </header>
  )
}

export default HeaderBar
