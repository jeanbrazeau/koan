# Provider adapter: the single per-provider dialect seam.
# Covers all four day-one providers (M7): google, anthropic, openai, bedrock.
# Built against the installed pydantic-ai 2.0.0b5 API.
#
# Responsibilities:
#   - resolve_credentials: validate env vars for a ProviderAuth
#   - map_thinking: translate koan ThinkingMode to provider-specific settings
#   - build_model_settings: merge spec settings with thinking + caching
#   - build_model: construct a pydantic-ai Model object from a ModelSpec

from __future__ import annotations

import os

from ..agents.base import AgentDiagnostic, AgentError
from ..types import ModelSpec, ProviderAuth, ThinkingMode

# Thinking token budget by ThinkingMode -- shared by the budget-based providers
# (google google_thinking_config, anthropic anthropic_thinking).
_THINKING_BUDGET: dict[ThinkingMode, int | None] = {
    "disabled": None,
    "low":      512,
    "medium":   2048,
    "high":     8192,
    "xhigh":    16384,
    "max":      32768,
}

# OpenAI exposes reasoning as a coarse effort knob, not a token budget.
_OPENAI_EFFORT: dict[ThinkingMode, str | None] = {
    "disabled": None,
    "low":      "low",
    "medium":   "medium",
    "high":     "high",
    "xhigh":    "high",
    "max":      "high",
}

# koan provider name -> pydantic-ai infer_model() prefix.
_PROVIDER_PREFIX: dict[str, str] = {
    "google":    "google",
    "anthropic": "anthropic",
    "openai":    "openai",
    "bedrock":   "bedrock",
}


def resolve_credentials(auth: ProviderAuth) -> dict[str, str]:
    """Resolve live credentials for a ProviderAuth, raising on missing env vars.

    Returns a dict with the first non-empty env var value found among auth.env_keys,
    plus region and base_url if set. Raises AgentError with code 'missing_credentials'
    when no env var is populated.
    """
    resolved: dict[str, str] = {}

    api_key: str | None = None
    for key in auth.env_keys:
        val = os.environ.get(key, "")
        if val:
            api_key = val
            break

    if api_key is None and auth.env_keys:
        raise AgentError(AgentDiagnostic(
            code="missing_credentials",
            agent=auth.provider,
            stage="resolve_credentials",
            message=(
                f"No credentials found for provider '{auth.provider}'. "
                f"Set one of: {', '.join(auth.env_keys)}"
            ),
        ))

    if api_key:
        resolved["api_key"] = api_key
    if auth.region:
        resolved["region"] = auth.region
    if auth.base_url:
        resolved["base_url"] = auth.base_url

    return resolved


def map_thinking(provider: str, mode: ThinkingMode) -> dict:
    """Map koan ThinkingMode to the provider's model_settings dict.

    - google:    google_thinking_config token budget (disabled suppresses thoughts).
    - anthropic: anthropic_thinking {type: enabled, budget_tokens: N} (disabled -> off).
    - openai:    openai_reasoning_effort low/medium/high (disabled -> off).
    - bedrock:   no-op -- thinking on Bedrock is profile-driven per underlying
                 model; left to pydantic-ai's BedrockModel + manual validation.

    Unknown providers raise NotImplementedError.
    """
    if provider == "google":
        if mode == "disabled":
            # Explicitly disable thinking to avoid unexpected token spend.
            return {"google_thinking_config": {"include_thoughts": False}}
        budget = _THINKING_BUDGET.get(mode, 2048)
        return {"google_thinking_config": {"thinking_budget": budget, "include_thoughts": True}}

    if provider == "anthropic":
        if mode == "disabled":
            return {}
        budget = _THINKING_BUDGET.get(mode) or 2048
        return {"anthropic_thinking": {"type": "enabled", "budget_tokens": budget}}

    if provider == "openai":
        effort = _OPENAI_EFFORT.get(mode)
        if effort is None:
            return {}
        return {"openai_reasoning_effort": effort}

    if provider == "bedrock":
        # Bedrock hosts Claude/OpenAI models; thinking is selected by the model
        # profile, not a portable koan-level knob. No-op (manual validation).
        return {}

    raise NotImplementedError(f"unknown provider '{provider}' has no thinking mapping")


def _caching_settings(spec: ModelSpec) -> dict:
    """Resolve the CachingPolicy into provider-specific cache settings.

    - anthropic: explicit cache_control on the instructions + tool definitions
      with the policy TTL (5m/1h).
    - google/openai: prompt caching is automatic server-side -> no settings.
    - bedrock: no portable cache knob exposed -> no-op (fallback per brief).
    Returns {} when caching is off or the provider needs nothing.
    """
    if spec.caching.mode == "off":
        return {}
    if spec.provider == "anthropic":
        ttl = spec.caching.ttl  # "5m" | "1h"
        return {
            "anthropic_cache_instructions": ttl,
            "anthropic_cache_tool_definitions": ttl,
        }
    return {}


def build_model_settings(spec: ModelSpec) -> dict:
    """Build the pydantic-ai model_settings dict from a ModelSpec.

    Merges spec.settings (temperature, max_tokens, etc.) with the per-provider
    thinking config (map_thinking) and caching settings (_caching_settings).
    Returns a flat dict suitable for pydantic-ai's model_settings parameter.
    """
    settings: dict = dict(spec.settings)
    settings.update(map_thinking(spec.provider, spec.thinking))
    settings.update(_caching_settings(spec))
    return settings


def build_model(spec: ModelSpec):
    """Construct a pydantic-ai Model object from a ModelSpec.

    Uses the stable '{prefix}:{model_id}' string form so the provider is
    resolved at call time via env credentials. The caller should have already
    called resolve_credentials to surface a clear error before this point.

    Raises AgentError(code='unknown_provider') for an unrecognised provider.
    """
    prefix = _PROVIDER_PREFIX.get(spec.provider)
    if prefix is None:
        raise AgentError(AgentDiagnostic(
            code="unknown_provider",
            agent=spec.provider,
            stage="build_model",
            message=(
                f"Unknown provider '{spec.provider}'. "
                f"Expected one of: {', '.join(sorted(_PROVIDER_PREFIX))}"
            ),
        ))
    from pydantic_ai.models import infer_model
    return infer_model(f"{prefix}:{spec.model}")
