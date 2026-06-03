# Shared type literals and constants for the koan orchestrator.
# Python port of src/planner/types.ts -- kept in sync manually.

from dataclasses import dataclass, field
from typing import Literal

WorkflowPhase = Literal[
    # Legacy workflow phases (kept as dead code; no active workflow uses these)
    "intake",
    "brief-generation",
    "core-flows",
    "tech-plan",
    "ticket-breakdown",
    "cross-artifact-validation",
    "execution",
    "implementation-validation",
    "completed",
    # Plan workflow phases
    "plan-spec",
    "plan-review",
    "execute",
    # Curation (memory maintenance) -- reusable across workflows
    "curation",
]

SubagentRole = Literal[
    "intake",
    "scout",
    "orchestrator",
    "planner",
    "executor",
]

ModelTier = Literal["strong", "standard", "cheap"]

ALL_MODEL_TIERS: tuple[ModelTier, ...] = ("strong", "standard", "cheap")

StoryStatus = Literal[
    "pending",
    "selected",
    "planning",
    "executing",
    "verifying",
    "done",
    "retry",
    "skipped",
]

DEFAULT_MAX_RETRIES = 2

ThinkingMode = Literal["disabled", "low", "medium", "high", "xhigh", "max"]


@dataclass
class ModelInfo:
    alias: str
    display_name: str
    thinking_modes: frozenset[ThinkingMode]
    tier_hint: ModelTier | None


# -- Provider config types (M1: config schema reshape) ------------------------
# Defined before ProfileTier (book order: dependencies before use).


@dataclass
class CachingPolicy:
    """Per-provider caching directives resolved by the adapter into request settings."""

    mode: Literal["auto", "off"] = "auto"
    ttl: Literal["5m", "1h"] = "5m"


@dataclass
class ModelSpec:
    """Resolved provider+model+settings for one role's model selection."""

    provider: str
    model: str
    thinking: ThinkingMode
    settings: dict = field(default_factory=dict)
    caching: CachingPolicy = field(default_factory=CachingPolicy)
    context_window: int = 0


@dataclass
class ProviderAuth:
    """Provider credentials config; replaces AgentInstallation (CLI binary) at M9."""

    provider: str
    env_keys: list[str] = field(default_factory=list)
    region: str | None = None
    base_url: str | None = None


# -- Profile types ------------------------------------------------------------


@dataclass
class ProfileTier:
    """Model selection for one tier slot; reshaped from (runner_type, model, thinking) to ModelSpec."""

    model: ModelSpec


@dataclass
class Profile:
    name: str
    tiers: dict[ModelTier, ProfileTier] = field(default_factory=dict)


BUILTIN_PROFILE_NAMES: frozenset[str] = frozenset({"balanced", "frontier"})


# Vestigial -- consumed by the legacy ClaudeSDKAgent/CommandLineAgent path and probe.py;
# removed at the M9 rip-out. The new config path uses ProviderAuth.
@dataclass
class AgentInstallation:
    alias: str
    runner_type: str
    binary: str
    extra_args: list[str] = field(default_factory=list)


ROLE_MODEL_TIER: dict[SubagentRole, ModelTier] = {
    "intake": "strong",
    "scout": "cheap",
    "orchestrator": "strong",
    "planner": "strong",
    "executor": "standard",
}

# Superseded by the provider adapter's per-provider thinking mapping;
# retained until the legacy claude path is removed at M9.
ROLE_EFFORT: dict[SubagentRole, ThinkingMode] = {
    "intake": "max",
    "scout": "medium",
    "orchestrator": "max",
    "planner": "max",
    "executor": "medium",
}
