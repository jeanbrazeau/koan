# Unit tests for koan.runners.registry -- AgentRegistry and compute_balanced_profile.
#
# NOTE: TestGetInstallation, TestResolveInstallation, TestResolveAgentConfigThinking,
# and TestComputeBalancedProfile are xfailed pending M2/M8:
#   - get_installation / resolve_installation / resolve_agent_config removed in M1
#     (binary detection retired; provider credentials resolve via adapter).
#   - ProfileTier reshaped from (runner_type, model, thinking) to (model: ModelSpec).
#   - compute_balanced_profile now returns static Gemini ModelSpec profiles; probe-based
#     assertions no longer hold.

import asyncio
import json

import pytest

from koan.agents.base import AgentError
from koan.agents.registry import AgentRegistry, compute_balanced_profile, _best_supported_thinking
from koan.config import KoanConfig, save_koan_config
from koan.probe import ProbeResult
from koan.types import AgentInstallation, ModelInfo, Profile, ProfileTier


# -- compute_balanced_profile --------------------------------------------------

# -- helpers for building probe results with models ---------------------------

def _codex_models() -> list[ModelInfo]:
    return [
        ModelInfo(alias="gpt-5", display_name="GPT-5", thinking_modes=frozenset({"disabled"}), tier_hint="strong"),
        ModelInfo(alias="gpt-5-mini", display_name="GPT-5 Mini", thinking_modes=frozenset({"disabled"}), tier_hint="cheap"),
    ]

def _claude_models() -> list[ModelInfo]:
    # Per-model thinking modes: Opus supports xhigh and max; Sonnet/Haiku do not.
    return [
        ModelInfo(
            alias="opus", display_name="Opus",
            thinking_modes=frozenset({"disabled", "low", "medium", "high", "xhigh", "max"}),
            tier_hint="strong",
        ),
        ModelInfo(
            alias="sonnet", display_name="Sonnet",
            thinking_modes=frozenset({"disabled", "low", "medium", "high"}),
            tier_hint="standard",
        ),
        ModelInfo(
            alias="haiku", display_name="Haiku",
            thinking_modes=frozenset({"disabled", "low"}),
            tier_hint="cheap",
        ),
    ]

def _gemini_models() -> list[ModelInfo]:
    return [
        ModelInfo(alias="gemini-pro", display_name="Gemini Pro", thinking_modes=frozenset({"disabled", "low", "medium", "high"}), tier_hint="strong"),
        ModelInfo(alias="gemini-flash", display_name="Gemini Flash", thinking_modes=frozenset({"disabled", "low"}), tier_hint="cheap"),
    ]


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


# -- compute_balanced_profile --------------------------------------------------

# M1: compute_balanced_profile returns static Gemini ModelSpec profiles; the
# probe-based runner_type/model/thinking assertions below no longer hold.
# Re-established with provider-based assertions in tests/test_provider_config.py.
@pytest.mark.xfail(
    reason="legacy SDK/CLI probe-based profile computation replaced by static "
           "Gemini ModelSpec profiles in M1; assertions expect runner_type/model "
           "from ProbeResult which is no longer consulted",
    strict=False,
)
class TestComputeBalancedProfile:
    def test_all_available_with_models(self):
        probes = [
            ProbeResult(runner_type="claude", available=True, models=_claude_models()),
            ProbeResult(runner_type="codex", available=True, models=_codex_models()),
            ProbeResult(runner_type="gemini", available=True, models=_gemini_models()),
        ]
        p = compute_balanced_profile(probes)
        assert p.name == "balanced"
        assert p.tiers["strong"].runner_type == "claude"
        assert p.tiers["strong"].model == "sonnet"
        assert p.tiers["strong"].thinking == "high"
        assert p.tiers["standard"].runner_type == "claude"
        assert p.tiers["standard"].model == "sonnet"
        assert p.tiers["standard"].thinking == "medium"
        assert p.tiers["cheap"].runner_type == "claude"
        assert p.tiers["cheap"].model == "haiku"
        assert p.tiers["cheap"].thinking == "disabled"

    def test_all_available_without_models_uses_defaults(self):
        """When probe results lack model info, default thinking is kept."""
        probes = [
            ProbeResult(runner_type="claude", available=True),
            ProbeResult(runner_type="codex", available=True),
            ProbeResult(runner_type="gemini", available=True),
        ]
        p = compute_balanced_profile(probes)
        assert p.tiers["strong"].runner_type == "claude"
        assert p.tiers["strong"].thinking == "high"  # no model info -> default

    def test_only_claude_available(self):
        probes = [
            ProbeResult(runner_type="claude", available=True, models=_claude_models()),
            ProbeResult(runner_type="codex", available=False),
            ProbeResult(runner_type="gemini", available=False),
        ]
        p = compute_balanced_profile(probes)
        assert p.tiers["strong"].runner_type == "claude"
        assert p.tiers["strong"].model == "sonnet"
        assert p.tiers["strong"].thinking == "high"  # claude/opus supports high
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

    def test_claude_preferred_for_strong(self):
        probes = [
            ProbeResult(runner_type="claude", available=True, models=_claude_models()),
            ProbeResult(runner_type="codex", available=True, models=_codex_models()),
        ]
        p = compute_balanced_profile(probes)
        assert p.tiers["strong"].runner_type == "claude"
        assert p.tiers["strong"].model == "sonnet"

    def test_claude_preferred_for_standard(self):
        probes = [
            ProbeResult(runner_type="claude", available=True, models=_claude_models()),
            ProbeResult(runner_type="codex", available=True, models=_codex_models()),
        ]
        p = compute_balanced_profile(probes)
        assert p.tiers["standard"].runner_type == "claude"


# -- AgentRegistry.get_installation ------------------------------------------

# M1: get_installation removed -- binary detection retired; provider credentials
# resolve in koan/agents/adapter.py. Rewired in M2; removed at M9 rip-out.
@pytest.mark.xfail(
    reason="legacy SDK/CLI spawn path: get_installation removed in M1 "
           "(binary detection retired); settings/probe reworked in M8",
    strict=False,
)
class TestGetInstallation:
    def _make_config(self, installations):
        return KoanConfig(agent_installations=installations)

    def test_run_installation_resolved(self):
        inst = AgentInstallation(alias="my-claude", runner_type="claude", binary="/fake/bin/claude")
        config = self._make_config([inst])
        reg = AgentRegistry()
        result = reg.get_installation("claude", config, run_installations={"claude": "my-claude"})
        assert result is inst

    def test_fallback_to_first_installation(self):
        inst = AgentInstallation(alias="default-codex", runner_type="codex", binary="/fake/bin/codex")
        config = self._make_config([inst])
        reg = AgentRegistry()
        result = reg.get_installation("codex", config)
        assert result is inst

    def test_missing_installation_raises(self):
        config = self._make_config([])
        reg = AgentRegistry()
        with pytest.raises(AgentError) as exc_info:
            reg.get_installation("claude", config)
        assert exc_info.value.diagnostic.code == "no_installation"

    def test_run_alias_configured_but_missing_raises(self):
        inst = AgentInstallation(alias="real-claude", runner_type="claude", binary="/fake/bin/claude")
        config = self._make_config([inst])
        reg = AgentRegistry()
        with pytest.raises(AgentError) as exc_info:
            reg.get_installation("claude", config, run_installations={"claude": "ghost-alias"})
        assert exc_info.value.diagnostic.code == "no_installation"
        assert "ghost-alias" in exc_info.value.diagnostic.message

    def test_fallback_only_when_no_active_alias(self):
        inst = AgentInstallation(alias="default-codex", runner_type="codex", binary="/fake/bin/codex")
        config = self._make_config([inst])
        reg = AgentRegistry()
        result = reg.get_installation("codex", config)
        assert result is inst


# -- AgentRegistry.resolve_installation ---------------------------------------

# M1: resolve_installation removed -- binary detection retired; provider credentials
# resolve in koan/agents/adapter.py. Rewired in M2; removed at M9 rip-out.
@pytest.mark.xfail(
    reason="legacy SDK/CLI spawn path: resolve_installation removed in M1 "
           "(binary detection retired); settings/probe reworked in M8",
    strict=False,
)
class TestResolveInstallation:
    def _make_config(self, installations):
        return KoanConfig(agent_installations=installations)

    def test_returns_installation_when_binary_exists(self, tmp_path):
        binary = tmp_path / "claude"
        binary.touch()
        inst = AgentInstallation(alias="my-claude", runner_type="claude", binary=str(binary))
        config = self._make_config([inst])
        reg = AgentRegistry()
        result = reg.resolve_installation("claude", config, run_installations={"claude": "my-claude"})
        assert result is inst

    def test_raises_when_binary_missing(self):
        inst = AgentInstallation(alias="bad", runner_type="claude", binary="/nonexistent/claude")
        config = self._make_config([inst])
        reg = AgentRegistry()
        with pytest.raises(AgentError) as exc_info:
            reg.resolve_installation("claude", config)
        assert exc_info.value.diagnostic.code == "binary_not_found"
        assert "bad" in exc_info.value.diagnostic.message
        assert "/nonexistent/claude" in exc_info.value.diagnostic.message

    def test_raises_when_no_installations(self):
        config = self._make_config([])
        reg = AgentRegistry()
        with pytest.raises(AgentError) as exc_info:
            reg.resolve_installation("claude", config)
        assert exc_info.value.diagnostic.code == "no_installation"


# -- resolve_agent_config: role-effort wiring and clamping --------------------

# M1: resolve_agent_config replaced by resolve_model_spec; ProfileTier reshaped
# from (runner_type, model, thinking) to (model: ModelSpec). These tests guard
# behavior re-established via resolve_model_spec + adapter in M2.
@pytest.mark.xfail(
    reason="legacy SDK/CLI spawn path: resolve_agent_config replaced by "
           "resolve_model_spec in M1; ProfileTier reshaped; settings/probe reworked in M8",
    strict=False,
)
class TestResolveAgentConfigThinking:
    """Pins the claude/gemini thinking mode resolution split introduced in M3."""

    def _make_config(self, inst, profile):
        return KoanConfig(
            agent_installations=[inst],
            profiles=[profile],
            active_profile=profile.name,
        )

    def test_resolve_agent_config_claude_uses_role_effort(self, tmp_path):
        """Claude ignores ProfileTier.thinking and derives effort from ROLE_EFFORT[role].

        Opus advertises max; orchestrator maps to max in ROLE_EFFORT, so no clamping
        occurs and the returned thinking mode is max regardless of the profile's thinking.
        """
        binary = tmp_path / "claude"
        binary.touch()
        inst = AgentInstallation(alias="claude", runner_type="claude", binary=str(binary))
        profile = Profile(name="test", tiers={
            "strong": ProfileTier(runner_type="claude", model="opus[1m]", thinking="low"),
        })
        config = self._make_config(inst, profile)
        reg = AgentRegistry()
        _, _, thinking = reg.resolve_agent_config(role="orchestrator", config=config)
        # ROLE_EFFORT["orchestrator"] == "max"; Opus advertises max; no clamp.
        assert thinking == "max"

    def test_resolve_agent_config_claude_clamps_on_sonnet(self, tmp_path):
        """Sonnet does not advertise max; orchestrator's max request is clamped to high.

        The clamp is deterministic and observable (log line emitted). ProfileTier.thinking
        is not consulted; clamping is driven solely by ROLE_EFFORT and per-model thinking_modes.
        """
        binary = tmp_path / "claude"
        binary.touch()
        inst = AgentInstallation(alias="claude", runner_type="claude", binary=str(binary))
        profile = Profile(name="test", tiers={
            "strong": ProfileTier(runner_type="claude", model="sonnet", thinking="low"),
        })
        config = self._make_config(inst, profile)
        reg = AgentRegistry()
        _, _, thinking = reg.resolve_agent_config(role="orchestrator", config=config)
        # ROLE_EFFORT["orchestrator"] == "max"; Sonnet max supported is "high"; clamped.
        assert thinking == "high"

    def test_resolve_agent_config_gemini_uses_profile_thinking(self, tmp_path):
        """Gemini reads ProfileTier.thinking unchanged; ROLE_EFFORT is not consulted.

        This confirms that the claude-side decoupling does not affect the gemini path.
        """
        binary = tmp_path / "gemini"
        binary.touch()
        inst = AgentInstallation(alias="gemini", runner_type="gemini", binary=str(binary))
        profile = Profile(name="test", tiers={
            "strong": ProfileTier(runner_type="gemini", model="gemini-pro", thinking="low"),
        })
        config = self._make_config(inst, profile)
        reg = AgentRegistry()
        _, _, thinking = reg.resolve_agent_config(role="orchestrator", config=config)
        # ProfileTier.thinking="low"; gemini does not consult ROLE_EFFORT.
        assert thinking == "low"


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
