import { useState, useEffect } from 'react'
import { useStore, Profile, Installation } from '../store/index'
import { tierSummary } from '../utils'
import * as api from '../api/client'
import { RunnerInfo } from '../api/client'

// -- Cascade dropdowns helpers ------------------------------------------------

type TierConfig = { runner_type: string; model: string; thinking: string }
type TierMap = Record<string, TierConfig>

const TIER_NAMES = ['strong', 'standard', 'cheap'] as const

function getModelsForRunner(runners: RunnerInfo[], rt: string) {
  return runners.find(r => r.runner_type === rt)?.models ?? []
}

function getThinkingModes(runners: RunnerInfo[], rt: string, model: string) {
  const models = getModelsForRunner(runners, rt)
  return models.find(m => m.alias === model)?.thinking_modes ?? []
}

// -- ProfileForm --------------------------------------------------------------

function ProfileForm({
  initialName,
  initialTiers,
  isEdit,
  runners,
  onSave,
  onCancel,
}: {
  initialName: string
  initialTiers: TierMap
  isEdit: boolean
  runners: RunnerInfo[]
  onSave: () => void
  onCancel: () => void
}) {
  const [name, setName] = useState(initialName)
  const [tiers, setTiers] = useState<TierMap>(() => {
    const t: TierMap = {}
    for (const tier of TIER_NAMES) {
      t[tier] = initialTiers[tier] ?? { runner_type: '', model: '', thinking: '' }
    }
    return t
  })
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  const setTierField = (tier: string, field: keyof TierConfig, value: string) => {
    setTiers(prev => {
      const updated = { ...prev[tier], [field]: value }
      // Reset downstream when runner changes
      if (field === 'runner_type') {
        updated.model = ''
        updated.thinking = ''
      }
      // Reset thinking when model changes
      if (field === 'model') {
        updated.thinking = ''
      }
      return { ...prev, [tier]: updated }
    })
  }

  const handleSave = async () => {
    if (!isEdit && !name.trim()) {
      setFormError('Profile name is required')
      return
    }
    const filteredTiers: TierMap = {}
    for (const tier of TIER_NAMES) {
      const t = tiers[tier]
      if (t.runner_type && t.model) {
        filteredTiers[tier] = t
      }
    }
    setSaving(true)
    try {
      let res
      if (isEdit) {
        res = await api.updateProfile(name, filteredTiers)
      } else {
        res = await api.createProfile(name.trim(), filteredTiers)
      }
      if (res.ok) {
        onSave()
      } else {
        setFormError(res.message ?? 'Failed to save profile')
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="profile-form">
      {!isEdit && (
        <div className="tier-form-row">
          <span className="tier-form-label">Name</span>
          <input
            className="model-tier-input"
            style={{ flex: 1 }}
            placeholder="profile name"
            value={name}
            onChange={e => setName(e.target.value)}
          />
        </div>
      )}
      {TIER_NAMES.map(tier => {
        const t = tiers[tier]
        const models = getModelsForRunner(runners, t.runner_type)
        const thinkingModes = getThinkingModes(runners, t.runner_type, t.model)
        return (
          <div key={tier} className="tier-form-row">
            <span className="tier-form-label">{tier}</span>
            <select
              className="model-tier-select"
              value={t.runner_type}
              onChange={e => setTierField(tier, 'runner_type', e.target.value)}
              style={{ flex: 1 }}
            >
              <option value="">-- runner --</option>
              {runners.map(r => (
                <option key={r.runner_type} value={r.runner_type}>
                  {r.runner_type}
                </option>
              ))}
            </select>
            <select
              className="model-tier-select"
              value={t.model}
              onChange={e => setTierField(tier, 'model', e.target.value)}
              style={{ flex: 1 }}
              disabled={!t.runner_type}
            >
              <option value="">-- model --</option>
              {models.map(m => (
                <option key={m.alias} value={m.alias}>
                  {m.display_name || m.alias}
                </option>
              ))}
            </select>
            <select
              className="model-tier-select"
              value={t.thinking}
              onChange={e => setTierField(tier, 'thinking', e.target.value)}
              style={{ flex: 1 }}
              disabled={!t.model}
            >
              <option value="">-- thinking --</option>
              {thinkingModes.map(tm => (
                <option key={tm} value={tm}>
                  {tm}
                </option>
              ))}
            </select>
          </div>
        )
      })}
      {formError && <div className="no-runners-msg">{formError}</div>}
      <div className="form-actions" style={{ marginTop: 12 }}>
        <button className="btn btn-secondary" onClick={onCancel} disabled={saving}>
          Cancel
        </button>
        <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
          {saving ? 'Saving...' : 'Save'}
        </button>
      </div>
    </div>
  )
}

// -- InstallationForm ---------------------------------------------------------

function InstallationForm({
  initialAlias,
  initialRunnerType,
  initialBinary,
  initialExtraArgs,
  isEdit,
  allRunners,
  onSave,
  onCancel,
}: {
  initialAlias: string
  initialRunnerType: string
  initialBinary: string
  initialExtraArgs: string[]
  isEdit: boolean
  allRunners: RunnerInfo[]
  onSave: () => void
  onCancel: () => void
}) {
  const [alias, setAlias] = useState(initialAlias)
  const [runnerType, setRunnerType] = useState(initialRunnerType)
  const [binary, setBinary] = useState(initialBinary)
  const [extraArgs, setExtraArgs] = useState(initialExtraArgs.join(' '))
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  const handleDetect = async () => {
    if (!runnerType) {
      setFormError('Select a runner type first')
      return
    }
    const res = await api.detectAgent(runnerType)
    if (res.path) {
      setBinary(res.path)
    } else {
      setFormError('Binary not found in PATH')
    }
  }

  const handleSave = async () => {
    if (!alias.trim()) {
      setFormError('Alias is required')
      return
    }
    const args = extraArgs.trim() ? extraArgs.trim().split(/\s+/) : []
    setSaving(true)
    try {
      let res
      if (isEdit) {
        res = await api.updateAgent(alias, {
          runner_type: runnerType,
          binary: binary.trim(),
          extra_args: args,
        })
      } else {
        res = await api.createAgent({
          alias: alias.trim(),
          runner_type: runnerType,
          binary: binary.trim(),
          extra_args: args,
        })
      }
      if (res.ok) {
        onSave()
      } else {
        setFormError(res.message ?? 'Failed to save installation')
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="profile-form">
      {!isEdit && (
        <div className="tier-form-row">
          <span className="tier-form-label">Alias</span>
          <input
            className="model-tier-input"
            style={{ flex: 1 }}
            placeholder="my-claude"
            value={alias}
            onChange={e => setAlias(e.target.value)}
          />
        </div>
      )}
      <div className="tier-form-row">
        <span className="tier-form-label">Runner</span>
        <select
          className="model-tier-select"
          style={{ flex: 1 }}
          value={runnerType}
          onChange={e => setRunnerType(e.target.value)}
        >
          <option value="">-- runner type --</option>
          {allRunners.map(r => (
            <option key={r.runner_type} value={r.runner_type}>
              {r.runner_type}
            </option>
          ))}
        </select>
      </div>
      <div className="tier-form-row">
        <span className="tier-form-label">Binary</span>
        <input
          className="model-tier-input"
          style={{ flex: 1 }}
          placeholder="/usr/bin/claude"
          value={binary}
          onChange={e => setBinary(e.target.value)}
        />
        <button
          className="btn btn-secondary"
          style={{ padding: '4px 10px', fontSize: 13 }}
          onClick={handleDetect}
        >
          Detect
        </button>
      </div>
      <div className="tier-form-row">
        <span className="tier-form-label">Extra args</span>
        <input
          className="model-tier-input"
          style={{ flex: 1 }}
          placeholder="--verbose"
          value={extraArgs}
          onChange={e => setExtraArgs(e.target.value)}
        />
      </div>
      {formError && <div className="no-runners-msg">{formError}</div>}
      <div className="form-actions" style={{ marginTop: 12 }}>
        <button className="btn btn-secondary" onClick={onCancel} disabled={saving}>
          Cancel
        </button>
        <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
          {saving ? 'Saving...' : 'Save'}
        </button>
      </div>
    </div>
  )
}

// -- Main overlay -------------------------------------------------------------

export function SettingsOverlay() {
  const setSettingsOpen = useStore(s => s.setSettingsOpen)
  const [loading, setLoading] = useState(true)
  const [profiles, setProfiles] = useState<Profile[]>([])
  const [installations, setInstallations] = useState<Installation[]>([])
  const [activeInstallations, setActiveInstallations] = useState<Record<string, string>>({})
  const [scoutConcurrency, setScoutConcurrency] = useState(8)
  const [availableRunners, setAvailableRunners] = useState<RunnerInfo[]>([])
  const [allRunners, setAllRunners] = useState<RunnerInfo[]>([])

  const [showNewProfile, setShowNewProfile] = useState(false)
  const [editingProfile, setEditingProfile] = useState<string | null>(null)
  const [showNewInstallation, setShowNewInstallation] = useState(false)
  const [editingInstallation, setEditingInstallation] = useState<string | null>(null)

  const loadSettings = async () => {
    setLoading(true)
    try {
      const [probeData, settingsData] = await Promise.all([
        api.getProbe(true),
        api.getSettingsBody(),
      ])
      setAvailableRunners(probeData.runners.filter(r => r.available))
      setAllRunners(probeData.runners)
      setProfiles(settingsData.profiles)
      setInstallations(settingsData.installations)
      setActiveInstallations(settingsData.activeInstallations)
      setScoutConcurrency(settingsData.scoutConcurrency)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadSettings()
  }, [])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setSettingsOpen(false)
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [setSettingsOpen])

  const handleDeleteProfile = async (name: string) => {
    const res = await api.deleteProfile(name)
    if (res.ok) loadSettings()
  }

  const handleDeleteInstallation = async (alias: string) => {
    const res = await api.deleteAgent(alias)
    if (res.ok) loadSettings()
  }

  const handleSetActive = async (runner_type: string, alias: string) => {
    const res = await api.setActiveAgent(runner_type, alias)
    if (res.ok) loadSettings()
  }

  const handleSaveScoutConcurrency = async () => {
    await api.saveScoutConcurrency(scoutConcurrency)
  }

  const editingProfileData = editingProfile
    ? profiles.find(p => p.name === editingProfile)
    : null

  const editingInstData = editingInstallation
    ? installations.find(i => i.alias === editingInstallation)
    : null

  return (
    <div className="settings-overlay">
      <div className="settings-overlay-backdrop" onClick={() => setSettingsOpen(false)}>
        <div className="settings-overlay-panel" onClick={e => e.stopPropagation()}>
          <div className="settings-overlay-header">
            <span className="settings-overlay-title">Settings</span>
            <button
              className="settings-btn"
              id="btn-close-settings"
              aria-label="Close"
              onClick={() => setSettingsOpen(false)}
            >
              &#10005;
            </button>
          </div>

          <div className="settings-overlay-body">
            {loading ? (
              <p className="settings-section-heading">Loading...</p>
            ) : (
              <>
                {/* Profiles */}
                <div className="settings-section-heading">Profiles</div>
                {profiles.map(p => (
                  <div key={p.name} className="profile-row">
                    <span className="profile-row-name">
                      {p.name}
                      {p.read_only && ' [locked]'}
                    </span>
                    <span className="profile-row-tiers">
                      {tierSummary(p.tiers)}
                    </span>
                    {!p.read_only && (
                      <span className="profile-row-actions">
                        <button
                          className="btn btn-secondary"
                          style={{ padding: '4px 10px', fontSize: 13 }}
                          onClick={() => {
                            setShowNewProfile(false)
                            setEditingProfile(p.name)
                          }}
                        >
                          Edit
                        </button>
                        <button
                          className="btn btn-secondary"
                          style={{ padding: '4px 10px', fontSize: 13 }}
                          onClick={() => handleDeleteProfile(p.name)}
                        >
                          Delete
                        </button>
                      </span>
                    )}
                  </div>
                ))}

                {editingProfile && editingProfileData && (
                  <ProfileForm
                    initialName={editingProfile}
                    initialTiers={editingProfileData.tiers}
                    isEdit
                    runners={availableRunners}
                    onSave={() => {
                      setEditingProfile(null)
                      loadSettings()
                    }}
                    onCancel={() => setEditingProfile(null)}
                  />
                )}

                {!showNewProfile ? (
                  <button
                    className="btn btn-secondary"
                    style={{ marginTop: 8 }}
                    onClick={() => {
                      setEditingProfile(null)
                      setShowNewProfile(true)
                    }}
                  >
                    + New Profile
                  </button>
                ) : (
                  <ProfileForm
                    initialName=""
                    initialTiers={{}}
                    isEdit={false}
                    runners={availableRunners}
                    onSave={() => {
                      setShowNewProfile(false)
                      loadSettings()
                    }}
                    onCancel={() => setShowNewProfile(false)}
                  />
                )}

                {/* Agent Installations */}
                <details style={{ marginTop: 24 }}>
                  <summary
                    className="settings-section-heading"
                    style={{ cursor: 'pointer' }}
                  >
                    Agent Installations
                  </summary>
                  <div className="installation-cards">
                    {installations.map(inst => {
                      const isActive =
                        activeInstallations[inst.runner_type] === inst.alias
                      return (
                        <div key={inst.alias} className="installation-card">
                          <span className="installation-card-alias">{inst.alias}</span>
                          {isActive && <span className="badge active">active</span>}
                          <span className="installation-card-meta">
                            {inst.runner_type}
                          </span>
                          <span className="installation-card-meta">
                            {inst.binary || '--'}
                          </span>
                          {inst.extra_args && inst.extra_args.length > 0 && (
                            <span className="installation-card-meta">
                              {inst.extra_args.join(' ')}
                            </span>
                          )}
                          <span className="profile-row-actions">
                            {!isActive && (
                              <button
                                className="btn btn-secondary"
                                style={{ padding: '3px 8px', fontSize: 12 }}
                                onClick={() =>
                                  handleSetActive(inst.runner_type, inst.alias)
                                }
                              >
                                Set active
                              </button>
                            )}
                            <button
                              className="btn btn-secondary"
                              style={{ padding: '3px 8px', fontSize: 12 }}
                              onClick={() => {
                                setShowNewInstallation(false)
                                setEditingInstallation(inst.alias)
                              }}
                            >
                              Edit
                            </button>
                            <button
                              className="btn btn-secondary"
                              style={{ padding: '3px 8px', fontSize: 12 }}
                              onClick={() => handleDeleteInstallation(inst.alias)}
                            >
                              Delete
                            </button>
                          </span>
                        </div>
                      )
                    })}
                  </div>

                  {editingInstallation && editingInstData && (
                    <InstallationForm
                      initialAlias={editingInstallation}
                      initialRunnerType={editingInstData.runner_type}
                      initialBinary={editingInstData.binary}
                      initialExtraArgs={editingInstData.extra_args}
                      isEdit
                      allRunners={allRunners}
                      onSave={() => {
                        setEditingInstallation(null)
                        loadSettings()
                      }}
                      onCancel={() => setEditingInstallation(null)}
                    />
                  )}

                  {!showNewInstallation ? (
                    <button
                      className="btn btn-secondary"
                      style={{ marginTop: 8 }}
                      onClick={() => {
                        setEditingInstallation(null)
                        setShowNewInstallation(true)
                      }}
                    >
                      + New Installation
                    </button>
                  ) : (
                    <InstallationForm
                      initialAlias=""
                      initialRunnerType=""
                      initialBinary=""
                      initialExtraArgs={[]}
                      isEdit={false}
                      allRunners={allRunners}
                      onSave={() => {
                        setShowNewInstallation(false)
                        loadSettings()
                      }}
                      onCancel={() => setShowNewInstallation(false)}
                    />
                  )}
                </details>

                {/* Scout Concurrency */}
                <div className="model-config-section" style={{ marginTop: 24 }}>
                  <div className="settings-section-heading">Scout Concurrency</div>
                  <div
                    style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 8 }}
                  >
                    <input
                      id="settings-scout-concurrency"
                      className="scout-concurrency-input"
                      type="number"
                      min={1}
                      max={32}
                      value={scoutConcurrency}
                      onChange={e =>
                        setScoutConcurrency(parseInt(e.target.value, 10) || 8)
                      }
                    />
                    <button
                      className="btn btn-secondary"
                      style={{ padding: '4px 12px', fontSize: 13 }}
                      onClick={handleSaveScoutConcurrency}
                    >
                      Save
                    </button>
                  </div>
                </div>

                {/* Refresh */}
                <div style={{ marginTop: 24, textAlign: 'right' }}>
                  <button className="btn btn-secondary" onClick={loadSettings}>
                    Refresh
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
