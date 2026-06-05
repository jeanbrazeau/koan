# Unit tests for koan.agents.registry -- AgentRegistry and compute_balanced_profile.
#
# NOTE: TestGetInstallation, TestResolveInstallation, TestResolveAgentConfigThinking,
# and TestComputeBalancedProfile removed in M4 -- their subjects (ProbeResult,
# AgentInstallation, ModelInfo, get_installation, resolve_installation,
# resolve_agent_config, compute_balanced_profile probe path) are all deleted.
# Replacement coverage lives in tests/test_provider_config.py.

import asyncio
import json

import pytest

from koan.agents.base import AgentError
from koan.agents.registry import AgentRegistry, _best_supported_thinking
from koan.config import KoanConfig, save_koan_config


# -- _best_supported_thinking --------------------------------------------------

class TestBestSupportedThinking:
    def test_desired_is_supported(self):
        assert _best_supported_thinking(frozenset({"disabled", "high"}), "high") == "high"

    def test_clamp_to_highest_below(self):
        assert _best_supported_thinking(frozenset({"disabled", "low"}), "high") == "low"

    def test_disabled_only(self):
        assert _best_supported_thinking(frozenset({"disabled"}), "high") == "disabled"

    def test_exact_medium(self):
        assert _best_supported_thinking(frozenset({"disabled", "low", "medium"}), "medium") == "medium"




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
