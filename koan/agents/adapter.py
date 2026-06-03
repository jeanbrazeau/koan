# Provider adapter: the single per-provider dialect seam.
# Gemini-only until M7, when Anthropic/OpenAI/Bedrock adapters land.
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

# Gemini thinking budget by ThinkingMode.
# Mapped to google_thinking_config (ThinkingConfigDict) for the google provider.
# Values are token budgets; "disabled" uses include_thoughts=False to suppress.
_GEMINI_THINKING_BUDGET: dict[ThinkingMode, int | None] = {
    "disabled": None,
    "low":      512,
    "medium":   2048,
    "high":     8192,
    "xhigh":    16384,
    "max":      32768,
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
    """Map koan ThinkingMode to the provider's model settings dict.

    For 'google': returns google_thinking_config with a token budget.
    Disabled thinking suppresses thoughts via include_thoughts=False.
    Other providers raise NotImplementedError until M7.
    """
    if provider == "google":
        if mode == "disabled":
            # Explicitly disable thinking to avoid unexpected token spend.
            return {"google_thinking_config": {"include_thoughts": False}}
        budget = _GEMINI_THINKING_BUDGET.get(mode, 2048)
        return {"google_thinking_config": {"thinking_budget": budget, "include_thoughts": True}}
    raise NotImplementedError(
        f"thinking mapping for provider '{provider}' lands in M7"
    )


def build_model_settings(spec: ModelSpec) -> dict:
    """Build the pydantic-ai model_settings dict from a ModelSpec.

    Merges spec.settings (temperature, max_tokens, etc.) with the thinking
    config from map_thinking. Gemini caching is automatic (server-side no-op).
    Returns a flat dict suitable for pydantic-ai's model_settings parameter.
    """
    settings: dict = dict(spec.settings)
    # Merge provider-specific thinking config on top.
    # map_thinking raises NotImplementedError for non-Google providers;
    # callers should catch this until M7 adds the remaining adapters.
    thinking_settings = map_thinking(spec.provider, spec.thinking)
    settings.update(thinking_settings)
    return settings


def build_model(spec: ModelSpec):
    """Construct a pydantic-ai Model object from a ModelSpec.

    For 'google': uses the stable 'google:{model_id}' string form so the
    provider is resolved at call time via env credentials (GOOGLE_API_KEY /
    GEMINI_API_KEY). The caller should have already called resolve_credentials
    to surface a clear error before this point.

    Other providers raise NotImplementedError until M7.
    Returns the Model object to be passed to PydanticAIAgent in M2.
    """
    if spec.provider == "google":
        from pydantic_ai.models import infer_model
        return infer_model(f"google:{spec.model}")
    raise NotImplementedError(
        f"provider '{spec.provider}' lands in M7"
    )
