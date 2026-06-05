# Unit tests for M1 config schema and adapter: ModelSpec resolution,
# built-in profile computation, config round-trip, and credential resolution.

from __future__ import annotations

import asyncio
import json
import os

import pytest

from koan.agents.adapter import resolve_credentials
from koan.agents.registry import AgentRegistry, compute_builtin_profiles
from koan.config import KoanConfig, load_koan_config, save_koan_config
from koan.types import (
    CachingPolicy,
    ModelSpec,
    Profile,
    ProfileTier,
    ProviderAuth,
)


# -- resolve_model_spec --------------------------------------------------------

class TestResolveModelSpec:
    def _make_config(self, profile: Profile) -> KoanConfig:
        """Build a KoanConfig with a single profile and no provider_auth."""
        return KoanConfig(profiles=[], active_profile=profile.name)

    def _gemini_profile(self, name: str) -> Profile:
        """Build a simple Gemini profile with strong/standard/cheap tiers."""
        return Profile(name=name, tiers={
            "strong":   ProfileTier(model=ModelSpec(provider="google", model="gemini-pro",   thinking="high")),
            "standard": ProfileTier(model=ModelSpec(provider="google", model="gemini-flash", thinking="medium")),
            "cheap":    ProfileTier(model=ModelSpec(provider="google", model="gemini-lite",  thinking="disabled")),
        })

    def test_orchestrator_resolves_strong_tier(self):
        """Orchestrator maps to 'strong' tier and returns its ModelSpec."""
        profile = self._gemini_profile("balanced")
        config = KoanConfig(active_profile="balanced")
        reg = AgentRegistry()
        spec = reg.resolve_model_spec("orchestrator", config, builtin_profiles={"balanced": profile})
        assert spec.provider == "google"
        assert spec.model == "gemini-pro"
        assert spec.thinking == "high"

    def test_intake_resolves_strong_tier(self):
        """Intake role maps to 'strong' tier."""
        profile = self._gemini_profile("balanced")
        config = KoanConfig(active_profile="balanced")
        reg = AgentRegistry()
        spec = reg.resolve_model_spec("intake", config, builtin_profiles={"balanced": profile})
        assert spec.model == "gemini-pro"

    def test_planner_resolves_strong_tier(self):
        """Planner role maps to 'strong' tier."""
        profile = self._gemini_profile("balanced")
        config = KoanConfig(active_profile="balanced")
        reg = AgentRegistry()
        spec = reg.resolve_model_spec("planner", config, builtin_profiles={"balanced": profile})
        assert spec.model == "gemini-pro"

    def test_executor_resolves_standard_tier(self):
        """Executor role maps to 'standard' tier."""
        profile = self._gemini_profile("balanced")
        config = KoanConfig(active_profile="balanced")
        reg = AgentRegistry()
        spec = reg.resolve_model_spec("executor", config, builtin_profiles={"balanced": profile})
        assert spec.model == "gemini-flash"
        assert spec.thinking == "medium"

    def test_scout_resolves_cheap_tier(self):
        """Scout role maps to 'cheap' tier."""
        profile = self._gemini_profile("balanced")
        config = KoanConfig(active_profile="balanced")
        reg = AgentRegistry()
        spec = reg.resolve_model_spec("scout", config, builtin_profiles={"balanced": profile})
        assert spec.model == "gemini-lite"
        assert spec.thinking == "disabled"

    def test_missing_profile_raises_agent_error(self):
        """Missing active profile raises AgentError with code 'no_profile'."""
        from koan.agents.base import AgentError
        config = KoanConfig(active_profile="nonexistent")
        reg = AgentRegistry()
        with pytest.raises(AgentError) as exc:
            reg.resolve_model_spec("orchestrator", config, builtin_profiles={})
        assert exc.value.diagnostic.code == "no_profile"


# -- compute_builtin_profiles --------------------------------------------------

class TestComputeBuiltinProfiles:
    def test_returns_balanced_and_frontier(self):
        """compute_builtin_profiles returns at least balanced and frontier profiles."""
        profiles = compute_builtin_profiles()
        assert "balanced" in profiles
        assert "frontier" in profiles

    def test_balanced_tiers_are_google_provider(self):
        """All balanced profile tiers use provider='google'."""
        profiles = compute_builtin_profiles()
        balanced = profiles["balanced"]
        for tier in ("strong", "standard", "cheap"):
            assert tier in balanced.tiers, f"Missing tier: {tier}"
            assert balanced.tiers[tier].model.provider == "google"

    def test_frontier_tiers_are_google_provider(self):
        """All frontier profile tiers use provider='google'."""
        profiles = compute_builtin_profiles()
        frontier = profiles["frontier"]
        for tier in ("strong", "standard", "cheap"):
            assert tier in frontier.tiers, f"Missing tier: {tier}"
            assert frontier.tiers[tier].model.provider == "google"

    def test_probe_results_ignored(self):
        """M2: compute_builtin_profiles takes no argument; probe_results param removed."""
        # Both calls return identical results (probe_results was vestigial and is now gone).
        profiles_a = compute_builtin_profiles()
        profiles_b = compute_builtin_profiles()
        assert profiles_a["balanced"].tiers.keys() == profiles_b["balanced"].tiers.keys()
        for tier in ("strong", "standard", "cheap"):
            assert (
                profiles_a["balanced"].tiers[tier].model.provider
                == profiles_b["balanced"].tiers[tier].model.provider
            )


# -- Config round-trip ---------------------------------------------------------

class TestConfigRoundTrip:
    @pytest.mark.anyio
    async def test_provider_auth_and_model_spec_round_trip(self, tmp_path, monkeypatch):
        """KoanConfig with provider_auth and a ModelSpec profile round-trips through save/load."""
        config_path = tmp_path / "config.json"
        monkeypatch.setattr("koan.config.CONFIG_PATH", config_path)
        monkeypatch.setattr("koan.config._config_write_lock", None)

        spec = ModelSpec(
            provider="google",
            model="gemini-pro",
            thinking="high",
            settings={"temperature": 0.2},
            caching=CachingPolicy(mode="auto", ttl="5m"),
            context_window=1_000_000,
        )
        auth = ProviderAuth(
            provider="google",
            env_keys=["GOOGLE_API_KEY", "GEMINI_API_KEY"],
        )
        profile = Profile(name="my-profile", tiers={
            "strong": ProfileTier(model=spec),
        })
        original = KoanConfig(
            provider_auth=[auth],
            profiles=[profile],
            active_profile="my-profile",
            scout_concurrency=4,
        )

        await save_koan_config(original)
        loaded = await load_koan_config()

        assert loaded.active_profile == "my-profile"
        assert loaded.scout_concurrency == 4
        assert len(loaded.provider_auth) == 1
        pa = loaded.provider_auth[0]
        assert pa.provider == "google"
        assert pa.env_keys == ["GOOGLE_API_KEY", "GEMINI_API_KEY"]
        assert len(loaded.profiles) == 1
        p = loaded.profiles[0]
        assert p.name == "my-profile"
        tier = p.tiers["strong"]
        assert tier.model.provider == "google"
        assert tier.model.model == "gemini-pro"
        assert tier.model.thinking == "high"
        assert tier.model.context_window == 1_000_000

    @pytest.mark.anyio
    async def test_legacy_agent_installations_key_stripped_on_save(self, tmp_path, monkeypatch):
        """Saving a KoanConfig strips the legacy agentInstallations key from existing files."""
        config_path = tmp_path / "config.json"
        monkeypatch.setattr("koan.config.CONFIG_PATH", config_path)
        monkeypatch.setattr("koan.config._config_write_lock", None)

        # Write a legacy-format file with agentInstallations key.
        config_path.write_text(json.dumps({
            "agentInstallations": [{"alias": "old-claude", "runnerType": "claude", "binary": "/bin/claude"}],
            "scoutConcurrency": 8,
        }), "utf-8")

        config = KoanConfig()
        await save_koan_config(config)

        saved = json.loads(config_path.read_text("utf-8"))
        assert "agentInstallations" not in saved
        assert "providerAuth" in saved


# -- resolve_credentials -------------------------------------------------------

class TestResolveCredentials:
    def test_raises_when_env_vars_unset(self, monkeypatch):
        """resolve_credentials raises AgentError when no env var is populated."""
        from koan.agents.base import AgentError
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        auth = ProviderAuth(provider="google", env_keys=["GOOGLE_API_KEY", "GEMINI_API_KEY"])
        with pytest.raises(AgentError) as exc:
            resolve_credentials(auth)
        assert exc.value.diagnostic.code == "missing_credentials"
        assert "GOOGLE_API_KEY" in exc.value.diagnostic.message

    def test_returns_when_google_api_key_set(self, monkeypatch):
        """resolve_credentials returns api_key when GOOGLE_API_KEY is set."""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key-value")
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        auth = ProviderAuth(provider="google", env_keys=["GOOGLE_API_KEY", "GEMINI_API_KEY"])
        creds = resolve_credentials(auth)
        assert creds.get("api_key") == "test-key-value"

    def test_returns_when_gemini_api_key_set(self, monkeypatch):
        """resolve_credentials falls back to GEMINI_API_KEY when GOOGLE_API_KEY is absent."""
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.setenv("GEMINI_API_KEY", "gemini-key-value")
        auth = ProviderAuth(provider="google", env_keys=["GOOGLE_API_KEY", "GEMINI_API_KEY"])
        creds = resolve_credentials(auth)
        assert creds.get("api_key") == "gemini-key-value"

    def test_no_error_when_no_env_keys_configured(self, monkeypatch):
        """resolve_credentials returns empty dict when env_keys is empty (no key required)."""
        auth = ProviderAuth(provider="bedrock", env_keys=[])
        creds = resolve_credentials(auth)
        assert "api_key" not in creds
