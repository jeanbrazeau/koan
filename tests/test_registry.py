# Unit tests for koan.runners.registry -- RunnerRegistry and compute_balanced_profile.

import asyncio
import json

import pytest

from koan.config import KoanConfig, save_koan_config
from koan.probe import ProbeResult
from koan.runners.base import RunnerError
from koan.runners.registry import RunnerRegistry, compute_balanced_profile
from koan.types import AgentInstallation, Profile, ProfileTier


# -- compute_balanced_profile --------------------------------------------------

class TestComputeBalancedProfile:
    def test_all_available(self):
        probes = [
            ProbeResult(runner_type="claude", available=True),
            ProbeResult(runner_type="codex", available=True),
            ProbeResult(runner_type="gemini", available=True),
        ]
        p = compute_balanced_profile(probes)
        assert p.name == "balanced"
        assert p.tiers["strong"].runner_type == "codex"
        assert p.tiers["strong"].model == "gpt-5"
        assert p.tiers["strong"].thinking == "high"
        assert p.tiers["standard"].runner_type == "claude"
        assert p.tiers["standard"].model == "sonnet"
        assert p.tiers["standard"].thinking == "medium"
        assert p.tiers["cheap"].runner_type == "claude"
        assert p.tiers["cheap"].model == "haiku"
        assert p.tiers["cheap"].thinking == "disabled"

    def test_only_claude_available(self):
        probes = [
            ProbeResult(runner_type="claude", available=True),
            ProbeResult(runner_type="codex", available=False),
            ProbeResult(runner_type="gemini", available=False),
        ]
        p = compute_balanced_profile(probes)
        assert p.tiers["strong"].runner_type == "claude"
        assert p.tiers["strong"].model == "opus"
        assert p.tiers["standard"].runner_type == "claude"
        assert p.tiers["standard"].model == "sonnet"
        assert p.tiers["cheap"].runner_type == "claude"
        assert p.tiers["cheap"].model == "haiku"

    def test_only_gemini_available(self):
        probes = [
            ProbeResult(runner_type="claude", available=False),
            ProbeResult(runner_type="codex", available=False),
            ProbeResult(runner_type="gemini", available=True),
        ]
        p = compute_balanced_profile(probes)
        for tier in ("strong", "standard", "cheap"):
            assert p.tiers[tier].runner_type == "gemini"

    def test_no_runners_available(self):
        probes = [
            ProbeResult(runner_type="claude", available=False),
            ProbeResult(runner_type="codex", available=False),
            ProbeResult(runner_type="gemini", available=False),
        ]
        p = compute_balanced_profile(probes)
        assert p.name == "balanced"
        assert p.tiers == {}

    def test_codex_preferred_for_strong(self):
        probes = [
            ProbeResult(runner_type="claude", available=True),
            ProbeResult(runner_type="codex", available=True),
        ]
        p = compute_balanced_profile(probes)
        assert p.tiers["strong"].runner_type == "codex"

    def test_claude_preferred_for_standard(self):
        probes = [
            ProbeResult(runner_type="claude", available=True),
            ProbeResult(runner_type="codex", available=True),
        ]
        p = compute_balanced_profile(probes)
        assert p.tiers["standard"].runner_type == "claude"


# -- RunnerRegistry.get_installation ------------------------------------------

class TestGetInstallation:
    def _make_config(self, installations, active=None):
        return KoanConfig(
            agent_installations=installations,
            active_installations=active or {},
        )

    def test_active_installation_resolved(self):
        inst = AgentInstallation(alias="my-claude", runner_type="claude", binary="/usr/bin/claude")
        config = self._make_config([inst], active={"claude": "my-claude"})
        reg = RunnerRegistry()
        result = reg.get_installation("claude", config)
        assert result is inst

    def test_fallback_to_first_installation(self):
        inst = AgentInstallation(alias="default-codex", runner_type="codex", binary="/usr/bin/codex")
        config = self._make_config([inst])
        reg = RunnerRegistry()
        result = reg.get_installation("codex", config)
        assert result is inst

    def test_missing_installation_raises(self):
        config = self._make_config([])
        reg = RunnerRegistry()
        with pytest.raises(RunnerError) as exc_info:
            reg.get_installation("claude", config)
        assert exc_info.value.diagnostic.code == "no_installation"


# -- save_koan_config write lock -----------------------------------------------

class TestWriteLock:
    def test_sequential_writes(self, tmp_path, monkeypatch):
        config_path = tmp_path / "config.json"
        monkeypatch.setattr("koan.config.CONFIG_PATH", config_path)
        # Reset module-level lock so it gets created fresh
        monkeypatch.setattr("koan.config._config_write_lock", None)

        config1 = KoanConfig(scout_concurrency=4)
        config2 = KoanConfig(scout_concurrency=16)

        async def run():
            await asyncio.gather(
                save_koan_config(config1),
                save_koan_config(config2),
            )

        asyncio.run(run())

        result = json.loads(config_path.read_text("utf-8"))
        # Both writes completed; final value is one of {4, 16}
        assert result["scoutConcurrency"] in (4, 16)
        # File is valid JSON (not corrupted by concurrent writes)
        assert isinstance(result, dict)
