---
title: Provider config reshaped to ModelSpec + ProviderAuth with credential-based
  availability, replacing runner_type profiles and binary probing
type: decision
created: '2026-06-04T14:12:03Z'
modified: '2026-06-04T14:12:03Z'
related:
- 0152-koans-agent-layer-is-one-native-pydanticai.md
- 0008-three-tier-model-system-strongstandardcheap-over.md
---

koan's provider/model configuration in `koan/config.py` is built on `ModelSpec{provider, model, thinking, settings, caching}` together with `ProviderAuth` for credentials. Provider availability is resolved from environment credentials -- `provider_available` over the `DEFAULT_PROVIDER_ENV_KEYS` map (for example, Gemini counts as available when `GOOGLE_API_KEY` or `GEMINI_API_KEY` is set) -- rather than by detecting an installed CLI binary, which carries no meaning once agents reach providers directly by API and no binary needs to exist. This replaces the earlier CLI-installation model: `ProfileTier` keyed on a `runner_type`, `AgentInstallation` records, and binary detection via `probe_all_runners`. Leon directed a big-bang reshape with no backwards compatibility, deleting the old schema outright rather than bridging it, because the credential model and the binary-installation model share no fields worth translating. Alternatives rejected: an auto-upgrader that rewrites old config files (carries dead schema for one-time value), and shipping the new profiles while making users re-pick their models (user friction with no durable benefit).
