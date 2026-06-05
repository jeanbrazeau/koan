# Shared type literals and constants for the koan orchestrator.
# Python port of src/planner/types.ts -- kept in sync manually.

from dataclasses import dataclass, field
from typing import Literal

WorkflowPhase = Literal[
    # Active workflow phases
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
    # M4: legacy phase literals kept to avoid breaking state.py WorkflowPhase
    # annotation until the phase taxonomy is revisited in M6/M7.
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


# ModelInfo removed in M4: the CLI binary probe that populated it is deleted.
# The all-providers model catalog uses ModelRegistryEntry (koan/types.py) and
# koan/agents/model_catalog.py instead.


# -- Provider availability and model registry (M2) ----------------------------
# Defined before ProfileTier (book order: dependencies before use).


@dataclass
class ProviderStatus:
    """Credential-based provider availability; replaces ProbeResult's availability role.

    Carries which env vars were checked (by name, never value) and whether all
    required keys were present. ProbeResult / probe.py stay defined-but-unused
    until Milestone 4.
    """

    provider: str
    available: bool
    env_keys: list[str] = field(default_factory=list)


@dataclass
class ModelRegistryEntry:
    """One entry in the all-providers model catalog, surfaced via Settings projection.

    Describes a curated (provider, model) pair with capability annotations.
    Sources: model lists and context_window from genai-prices bundled snapshot;
    thinking_modes and tier_hint from the koan capability table in model_catalog.py.
    """

    provider: str
    model: str
    display_name: str
    context_window: int
    thinking_modes: list[ThinkingMode] = field(default_factory=list)
    tier_hint: ModelTier | None = None


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


# AgentInstallation removed in M4: the legacy CLI/SDK agent path is deleted.
# Provider credentials use ProviderAuth.


ROLE_MODEL_TIER: dict[SubagentRole, ModelTier] = {
    "intake": "strong",
    "scout": "cheap",
    "orchestrator": "strong",
    "planner": "strong",
    "executor": "standard",
}

# ROLE_EFFORT removed in M4: superseded by the provider adapter's per-provider
# thinking mapping. Only ROLE_MODEL_TIER (above) remains for tier resolution.
