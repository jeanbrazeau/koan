# resolve_runner -- maps a SubagentRole to the appropriate Runner instance.
# Provider is inferred from the model string prefix in config.model_tiers.

from __future__ import annotations

from ..config import KoanConfig
from ..types import ROLE_MODEL_TIER, SubagentRole
from .base import Runner
from .claude import ClaudeRunner
from .codex import CodexRunner
from .gemini import GeminiRunner


def resolve_runner(role: SubagentRole, config: KoanConfig, subagent_dir: str) -> Runner:
    tier = ROLE_MODEL_TIER[role]
    if config.model_tiers is None:
        raise ValueError("config.model_tiers is not configured")

    model = getattr(config.model_tiers, tier)
    if not model:
        raise ValueError(f"No model configured for tier '{tier}'")

    if model.startswith("claude"):
        return ClaudeRunner(subagent_dir=subagent_dir)
    if model.startswith("codex") or model.startswith("o"):
        return CodexRunner()
    if model.startswith("gemini"):
        return GeminiRunner(subagent_dir=subagent_dir)

    raise ValueError(f"Unknown provider for model '{model}' (role={role}, tier={tier})")
