import { useState, useEffect } from 'react'
import { useStore } from '../store/index'
import type { ModelRegistryEntry, ProviderStatus } from '../store/index'
import { tierSummary } from '../utils'
import * as api from '../api/client'
import './SettingsOverlay.css'

// -- ProfileForm helpers ------------------------------------------------------

type TierConfig = { provider: string; model: string; thinking: string }
type TierMap = Record<string, TierConfig>

const TIER_NAMES = ['strong', 'standard', 'cheap'] as const

/** Distinct provider IDs found in the model registry. */
function providersInRegistry(registry: ModelRegistryEntry[]): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const e of registry) {
    if (!seen.has(e.provider)) {
      seen.add(e.provider)
      out.push(e.provider)
    }
  }
  return out
}

/** Registry entries for a given provider. */
function modelsForProvider(registry: ModelRegistryEntry[], provider: string): ModelRegistryEntry[] {
  return registry.filter(e => e.provider === provider)
}

/** Thinking modes for a given (provider, model) pair. */
function thinkingModesForModel(registry: ModelRegistryEntry[], provider: string, model: string): string[] {
  return registry.find(e => e.provider === provider && e.model === model)?.thinkingModes ?? []
}

// -- ProfileForm --------------------------------------------------------------

/**
 * Form for creating or editing a user profile.
 *
 * Sources tier options entirely from modelRegistry (M3): provider dropdown lists
 * distinct registry providers; model dropdown is filtered by chosen provider;
 * thinking dropdown comes from the chosen model's thinkingModes. Cascading reset
 * clears downstream selections when an upstream value changes.
 */
function ProfileForm({
  initialName,
  isEdit,
  modelRegistry,
  onSave,
  onCancel,
}: {
  initialName: string
  isEdit: boolean
  modelRegistry: ModelRegistryEntry[]
  onSave: () => void
  onCancel: () => void
}) {
  const [name, setName] = useState(initialName)
  const [tiers, setTiers] = useState<TierMap>(() => {
    const t: TierMap = {}
    for (const tier of TIER_NAMES) {
      t[tier] = { provider: '', model: '', thinking: '' }
    }
    return t
  })
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  const providers = providersInRegistry(modelRegistry)

  const setTierField = (tier: string, field: keyof TierConfig, value: string) => {
    setTiers(prev => {
      const updated = { ...prev[tier], [field]: value }
      // Cascade: changing provider clears model and thinking; changing model clears thinking.
      if (field === 'provider') {
        updated.model = ''
        updated.thinking = ''
      }
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
      if (t.provider && t.model) {
        filteredTiers[tier] = t
      }
    }
    setSaving(true)
    try {
      const res = isEdit
        ? await api.updateProfile(name, filteredTiers)
        : await api.createProfile(name.trim(), filteredTiers)
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
        const models = modelsForProvider(modelRegistry, t.provider)
        const thinkingModes = thinkingModesForModel(modelRegistry, t.provider, t.model)
        return (
          <div key={tier} className="tier-form-row">
            <span className="tier-form-label">{tier}</span>
            <select
              className="model-tier-select"
              value={t.provider}
              onChange={e => setTierField(tier, 'provider', e.target.value)}
              style={{ flex: 1 }}
            >
              <option value="">-- provider --</option>
              {providers.map(p => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
            <select
              className="model-tier-select"
              value={t.model}
              onChange={e => setTierField(tier, 'model', e.target.value)}
              style={{ flex: 1 }}
              disabled={!t.provider}
            >
              <option value="">-- model --</option>
              {models.map(m => (
                <option key={m.model} value={m.model}>
                  {m.displayName || m.model}
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
              <option value="disabled">disabled</option>
              {thinkingModes.map(tm => (
                <option key={tm} value={tm}>{tm}</option>
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

// -- ProviderCredentials ------------------------------------------------------

/**
 * Displays per-provider credential presence and a local Validate action.
 *
 * Reads providerStatus from props (sourced from the store's Settings.providerStatus).
 * Validate calls POST /api/settings/validate-provider which is a local construction
 * check (no live provider call). Never prompts for or stores secrets.
 */
function ProviderCredentials({ providerStatus }: { providerStatus: ProviderStatus[] }) {
  const [results, setResults] = useState<Record<string, { valid: boolean; reason?: string } | null>>({})
  const [validating, setValidating] = useState<Record<string, boolean>>({})

  const handleValidate = async (provider: string) => {
    setValidating(prev => ({ ...prev, [provider]: true }))
    try {
      const res = await api.validateProvider(provider)
      setResults(prev => ({ ...prev, [provider]: res }))
    } finally {
      setValidating(prev => ({ ...prev, [provider]: false }))
    }
  }

  if (providerStatus.length === 0) {
    return <div className="so-no-providers">No providers configured.</div>
  }

  return (
    <div className="so-provider-list">
      {providerStatus.map(ps => {
        const result = results[ps.provider]
        const busy = validating[ps.provider] ?? false
        return (
          <div key={ps.provider} className="install-row">
            <div className="install-row-info">
              <span className="install-row-alias">{ps.provider}</span>
              {ps.available
                ? <span className="install-row-badge so-badge-present">credential present</span>
                : <span className="install-row-badge so-badge-missing">no credential</span>
              }
            </div>
            <span className="install-row-path so-env-keys">
              {ps.envKeys.join(', ')}
            </span>
            <span className="profile-row-actions">
              <button
                className="btn btn-secondary"
                style={{ padding: '4px 10px', fontSize: 13 }}
                disabled={busy}
                onClick={() => handleValidate(ps.provider)}
              >
                {busy ? 'Checking...' : 'Validate'}
              </button>
              {result !== null && result !== undefined && (
                <span className={result.valid ? 'so-result-valid' : 'so-result-invalid'}>
                  {result.valid ? 'valid' : (result.reason ?? 'invalid')}
                </span>
              )}
            </span>
          </div>
        )
      })}
    </div>
  )
}

// -- Main overlay -------------------------------------------------------------

export function SettingsOverlay() {
  const setSettingsOpen = useStore(s => s.setSettingsOpen)

  // Read all config from the store (fed by SSE projection events -- always current).
  const profilesDict = useStore(s => s.settings.profiles)
  const scoutConcurrency = useStore(s => s.settings.defaultScoutConcurrency)
  // M3: provider availability and model registry come from the projection store
  // (populated by M2 initial events). No separate /api/probe fetch needed.
  const providerStatus = useStore(s => s.settings.providerStatus)
  const modelRegistry = useStore(s => s.settings.modelRegistry)

  const profiles = Object.values(profilesDict)

  // Local UI state for forms
  const [localScoutConcurrency, setLocalScoutConcurrency] = useState(scoutConcurrency)
  const [showNewProfile, setShowNewProfile] = useState(false)
  const [editingProfile, setEditingProfile] = useState<string | null>(null)

  // Sync local scout concurrency when store changes
  useEffect(() => {
    setLocalScoutConcurrency(scoutConcurrency)
  }, [scoutConcurrency])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setSettingsOpen(false)
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [setSettingsOpen])

  const handleDeleteProfile = async (name: string) => {
    await api.deleteProfile(name)
    // SSE event updates the store automatically
  }

  const handleSaveScoutConcurrency = async () => {
    await api.saveScoutConcurrency(localScoutConcurrency)
  }

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
            {/* Profiles */}
            <div className="settings-section-heading">Profiles</div>
            {profiles.map(p => (
              <div key={p.name} className="profile-row">
                <span className="profile-row-name">
                  {p.name}
                  {p.readOnly && ' [locked]'}
                </span>
                <span className="profile-row-tiers">
                  {tierSummary(p.tiers)}
                </span>
                {!p.readOnly && (
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

            {editingProfile && (
              <ProfileForm
                initialName={editingProfile}
                isEdit
                modelRegistry={modelRegistry}
                onSave={() => setEditingProfile(null)}
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
                isEdit={false}
                modelRegistry={modelRegistry}
                onSave={() => setShowNewProfile(false)}
                onCancel={() => setShowNewProfile(false)}
              />
            )}

            {/* Provider Credentials (replaces Agent Installations in M3) */}
            <div className="settings-section-heading" style={{ marginTop: 24 }}>
              Provider Credentials
            </div>
            <ProviderCredentials providerStatus={providerStatus} />

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
                  value={localScoutConcurrency}
                  onChange={e =>
                    setLocalScoutConcurrency(parseInt(e.target.value, 10) || 8)
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
          </div>
        </div>
      </div>
    </div>
  )
}
