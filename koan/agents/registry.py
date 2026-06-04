# AgentRegistry -- maps agent types to Agent instances and resolves
# agent configuration (model spec) for a role.
# Replaces koan/runners/registry.py; the runner-level types (RunnerRegistry,
# compute_balanced_profile, compute_builtin_profiles) move here.

from __future__ import annotations

from typing import TYPE_CHECKING

from ..logger import get_logger
from ..probe import ProbeResult
from ..types import (
    BUILTIN_PROFILE_NAMES,
    ROLE_MODEL_TIER,
    CachingPolicy,
    ModelSpec,
    ModelTier,
    Profile,
    ProfileTier,
    ThinkingMode,
)
from .base import Agent, AgentDiagnostic, AgentError
from .command_line import CommandLineAgent

if TYPE_CHECKING:
    from ..config import KoanConfig
    from ..state import AppState
    from ..types import SubagentRole

log = get_logger("agent_registry")


# -- Built-in Gemini profile definitions (static; probe_results vestigial) ----
#
# Static per-tier Gemini specs: strong/standard/cheap -> model + thinking.
# These are the provider-based replacement for the old runner-priority table.
# Context windows are filled with known values; update when models change.

_GEMINI_TIER_SPECS: dict[ModelTier, tuple[str, ThinkingMode, int]] = {
    # (model_id, thinking, context_window). IDs must be valid google-GLA model
    # names: versioned names take no "-latest" suffix (gemini-2.5-pro, not
    # gemini-2.5-pro-latest -> 404); only unversioned names do (gemini-flash-lite-latest).
    "strong":   ("gemini-2.5-pro",            "high",     1_000_000),
    "standard": ("gemini-2.5-flash",          "medium",   1_000_000),
    "cheap":    ("gemini-flash-lite-latest",  "disabled", 1_000_000),
}

_TIER_DEFAULT_THINKING: dict[ModelTier, ThinkingMode] = {
    "strong": "high",
    "standard": "medium",
    "cheap": "disabled",
}

_THINKING_RANK: list[ThinkingMode] = ["disabled", "low", "medium", "high", "xhigh", "max"]


def _best_supported_thinking(
    supported: frozenset[ThinkingMode], desired: ThinkingMode
) -> ThinkingMode:
    """Return the highest supported thinking mode at or below *desired*."""
    desired_idx = _THINKING_RANK.index(desired) if desired in _THINKING_RANK else 0
    best: ThinkingMode = "disabled"
    for mode in _THINKING_RANK:
        if mode in supported and _THINKING_RANK.index(mode) <= desired_idx:
            best = mode
    return best


# -- AgentRegistry -------------------------------------------------------------

class AgentRegistry:
    """Resolves agent configuration and constructs Agent instances for a role.

    Replaces RunnerRegistry from koan/runners/registry.py. Post-M1 the primary
    resolution path is resolve_model_spec (provider-based). get_agent is
    orphaned pending the M2 rewire.
    """

    def get_agent(
        self,
        runner_type: str,
        subagent_dir: str,
        app_state: AppState | None = None,
    ) -> Agent:
        """Construct and return an Agent for the given runner_type.

        Orphaned after the M1 config reshape -- the legacy spawn path is rewired
        to PydanticAIAgent in M2 and this method is deleted at the M9 rip-out.
        Retained so tests that inject agent_impl directly still compile.

        Raises AgentError with code 'unknown_runner_type' for unrecognized types.
        Raises AgentError with code 'missing_app_state' when claude is requested
        without app_state.
        """
        # M2 seam: this branch constructs the legacy SDK/CLI agents. Once M2 is
        # complete PydanticAIAgent is used instead and this method is deleted.
        if runner_type == "claude":
            from .claude import ClaudeSDKAgent  # lazy -- avoids circular import
            if app_state is None:
                raise AgentError(AgentDiagnostic(
                    code="missing_app_state",
                    agent="claude",
                    stage="get_agent",
                    message="ClaudeSDKAgent requires app_state for the PostToolUse hook closure.",
                ))
            return ClaudeSDKAgent(subagent_dir=subagent_dir, app_state=app_state)
        elif runner_type == "codex":
            from ..runners.codex import CodexRunner  # lazy -- avoids circular import
            runner = CodexRunner()
        elif runner_type == "gemini":
            from ..runners.gemini import GeminiRunner  # lazy -- avoids circular import
            runner = GeminiRunner(subagent_dir=subagent_dir)
        else:
            raise AgentError(AgentDiagnostic(
                code="unknown_runner_type",
                agent=runner_type,
                stage="get_agent",
                message=f"Unknown runner type: {runner_type}",
            ))
        return CommandLineAgent(runner=runner, subagent_dir=subagent_dir)

    # get_installation removed -- binary detection retired; provider credentials
    # resolve in koan/agents/adapter.py.

    # resolve_installation removed -- binary detection retired; provider credentials
    # resolve in koan/agents/adapter.py.

    def resolve_model_spec(
        self,
        role: SubagentRole,
        config: KoanConfig,
        builtin_profiles: dict[str, Profile] | None = None,
    ) -> ModelSpec:
        """Resolve ModelSpec for a role via the active profile's tier mapping.

        Reads ROLE_MODEL_TIER[role] -> tier -> ProfileTier.model (ModelSpec).
        Raises AgentError with code 'no_profile' if the active profile or tier
        is missing from both config.profiles and builtin_profiles.
        """
        tier = ROLE_MODEL_TIER.get(role, "standard")

        profile: Profile | None = None
        for p in config.profiles:
            if p.name == config.active_profile:
                profile = p
                break

        if profile is None and builtin_profiles:
            profile = builtin_profiles.get(config.active_profile)

        if profile is None:
            raise AgentError(AgentDiagnostic(
                code="no_profile",
                agent="",
                stage="resolve_model_spec",
                message=f"Profile '{config.active_profile}' not found",
            ))

        profile_tier = profile.tiers.get(tier)
        if profile_tier is None:
            raise AgentError(AgentDiagnostic(
                code="no_profile",
                agent="",
                stage="resolve_model_spec",
                message=f"Profile '{profile.name}' has no tier '{tier}'",
            ))

        return profile_tier.model

    # _claude_clamp removed -- binary detection retired; provider adapter handles
    # per-provider thinking mapping in koan/agents/adapter.py.


# -- Built-in profile computation ----------------------------------------------

def _compute_balanced() -> Profile:
    """Build the balanced built-in profile with static Gemini ModelSpec tiers."""
    tiers: dict[str, ProfileTier] = {}
    for tier_name in ("strong", "standard", "cheap"):
        model_id, thinking, ctx_window = _GEMINI_TIER_SPECS[tier_name]
        tiers[tier_name] = ProfileTier(model=ModelSpec(
            provider="google",
            model=model_id,
            thinking=thinking,
            context_window=ctx_window,
        ))
    return Profile(name="balanced", tiers=tiers)


def _compute_fixed(name: str, specs: dict[ModelTier, tuple[str, ThinkingMode, int]]) -> Profile:
    """Build a named fixed built-in profile from a static (model, thinking, ctx_window) spec map."""
    tiers: dict[str, ProfileTier] = {}
    for tier_name, (model_id, thinking, ctx_window) in specs.items():
        tiers[tier_name] = ProfileTier(model=ModelSpec(
            provider="google",
            model=model_id,
            thinking=thinking,
            context_window=ctx_window,
        ))
    return Profile(name=name, tiers=tiers)


# Frontier uses larger/more-capable models than balanced across all tiers.
_GEMINI_FRONTIER_SPECS: dict[ModelTier, tuple[str, ThinkingMode, int]] = {
    "strong":   ("gemini-2.5-pro",    "high",     1_000_000),
    "standard": ("gemini-2.5-pro",    "medium",   1_000_000),
    "cheap":    ("gemini-2.5-flash",  "low",      1_000_000),
}


def compute_builtin_profiles(probe_results: list[ProbeResult]) -> dict[str, Profile]:
    """Compute all built-in profiles (balanced, frontier) as static Gemini ModelSpec profiles.

    probe_results vestigial -- runner probing is retired; provider profiles are
    static. Param kept until the M8 settings rework removes probe_results entirely.
    """
    # probe_results ignored: provider profiles are static Gemini specs now.
    profiles: dict[str, Profile] = {}
    profiles["balanced"] = _compute_balanced()
    profiles["frontier"] = _compute_fixed("frontier", _GEMINI_FRONTIER_SPECS)
    return profiles


def compute_balanced_profile(probe_results: list[ProbeResult]) -> Profile:
    """DEPRECATED: use compute_builtin_profiles instead."""
    return compute_builtin_profiles(probe_results)["balanced"]
