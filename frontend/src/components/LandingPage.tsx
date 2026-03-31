import { useState, useEffect } from 'react'
import { Profile } from '../store/index'
import * as api from '../api/client'

export function LandingPage() {
  const [task, setTask] = useState('')
  const [profile, setProfile] = useState('')
  const [scoutConcurrency, setScoutConcurrency] = useState(8)
  const [profiles, setProfiles] = useState<Profile[]>([])
  const [hasRunners, setHasRunners] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([api.getProfiles(), api.getProbe(), api.getInitialPrompt()]).then(
      ([profilesData, probeData, promptData]) => {
        setProfiles(profilesData.profiles)
        if (profilesData.profiles.length > 0) {
          setProfile(profilesData.profiles[0].name)
        }
        setHasRunners(probeData.runners.some(r => r.available))
        if (promptData.prompt) {
          setTask(promptData.prompt)
        }
      },
    )
  }, [])

  const handleStart = async () => {
    const trimmedTask = task.trim()
    if (!trimmedTask) {
      setError('Please enter a task description')
      return
    }
    if (!profile) {
      setError('Please select a profile')
      return
    }
    setError(null)
    setLoading(true)
    try {
      const result = await api.startRun(trimmedTask, profile, scoutConcurrency)
      if (!result.ok) {
        setError(result.message ?? 'Failed to start run')
      }
      // The SSE 'phase' event will flip runStarted → live view renders
    } catch {
      setError('Network error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="main-panel">
      <div className="phase-content">
        <div className="phase-inner">
          <h2 className="phase-heading">New Run</h2>

          <div className="question-card">
            <div className="question-header">Task</div>
            <textarea
              id="task-input"
              className="workflow-feedback"
              placeholder="Describe what you want to build..."
              rows={4}
              value={task}
              onChange={e => setTask(e.target.value)}
            />
          </div>

          <div className="model-config-section">
            <h3 className="model-config-section-heading">Profile</h3>
            <select
              id="profile-select"
              className="model-tier-select"
              value={profile}
              onChange={e => setProfile(e.target.value)}
            >
              {profiles.map(p => (
                <option key={p.name} value={p.name}>
                  {p.name}
                  {p.read_only ? ' (built-in)' : ''}
                </option>
              ))}
            </select>
          </div>

          <div className="model-config-section">
            <h3 className="model-config-section-heading">Scout Concurrency</h3>
            <input
              id="scout-concurrency"
              className="scout-concurrency-input"
              type="number"
              min={1}
              max={32}
              value={scoutConcurrency}
              onChange={e => setScoutConcurrency(parseInt(e.target.value, 10) || 8)}
            />
          </div>

          {error && <div className="no-runners-msg">{error}</div>}

          <div className="form-actions">
            <button
              id="btn-start-run"
              className="btn btn-primary"
              disabled={!hasRunners || loading}
              title={
                !hasRunners
                  ? 'No available runners. Install and authenticate at least one runner in Settings.'
                  : undefined
              }
              onClick={handleStart}
            >
              {loading ? 'Starting...' : 'Start Run'}
            </button>
          </div>

          {!hasRunners && (
            <span className="no-runners-msg">
              No available runners. Open Settings to install and authenticate a runner.
            </span>
          )}
        </div>
      </div>
    </div>
  )
}
