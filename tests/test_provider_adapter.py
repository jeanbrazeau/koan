# M7 provider fan-out: map_thinking / caching / build_model across all four
# providers. The pure mapping functions are tested directly; build_model is
# tested via a monkeypatched infer_model so no real provider credentials or
# network are needed (only the prefix-selection logic is under test here).

from __future__ import annotations

import pytest

from koan.agents import adapter
from koan.agents.base import AgentError
from koan.types import CachingPolicy, ModelSpec


def _spec(provider, model="m", thinking="disabled", caching=None, settings=None):
    return ModelSpec(
        provider=provider,
        model=model,
        thinking=thinking,
        settings=settings or {},
        caching=caching or CachingPolicy(),
    )


# -- map_thinking --------------------------------------------------------------


def test_map_thinking_google_disabled_suppresses_thoughts():
    assert adapter.map_thinking("google", "disabled") == {
        "google_thinking_config": {"include_thoughts": False}
    }


def test_map_thinking_google_budget():
    out = adapter.map_thinking("google", "high")
    assert out["google_thinking_config"]["thinking_budget"] == 8192
    assert out["google_thinking_config"]["include_thoughts"] is True


def test_map_thinking_anthropic():
    assert adapter.map_thinking("anthropic", "disabled") == {}
    assert adapter.map_thinking("anthropic", "medium") == {
        "anthropic_thinking": {"type": "enabled", "budget_tokens": 2048}
    }


def test_map_thinking_openai_effort():
    assert adapter.map_thinking("openai", "disabled") == {}
    assert adapter.map_thinking("openai", "low") == {"openai_reasoning_effort": "low"}
    # xhigh/max collapse to high (OpenAI has no finer knob).
    assert adapter.map_thinking("openai", "xhigh") == {"openai_reasoning_effort": "high"}


def test_map_thinking_bedrock_is_noop():
    assert adapter.map_thinking("bedrock", "high") == {}


def test_map_thinking_unknown_provider_raises():
    with pytest.raises(NotImplementedError):
        adapter.map_thinking("cohere", "high")


# -- caching -------------------------------------------------------------------


def test_caching_off_emits_nothing():
    s = adapter.build_model_settings(
        _spec("anthropic", caching=CachingPolicy(mode="off"))
    )
    assert not any(k.startswith("anthropic_cache") for k in s)


def test_caching_anthropic_auto_sets_ttl():
    s = adapter.build_model_settings(
        _spec("anthropic", caching=CachingPolicy(mode="auto", ttl="1h"))
    )
    assert s["anthropic_cache_instructions"] == "1h"
    assert s["anthropic_cache_tool_definitions"] == "1h"


def test_caching_google_openai_bedrock_noop():
    for provider in ("google", "openai", "bedrock"):
        s = adapter.build_model_settings(
            _spec(provider, caching=CachingPolicy(mode="auto"))
        )
        assert not any(k.startswith("anthropic_cache") for k in s)


def test_build_model_settings_merges_spec_settings_and_thinking():
    s = adapter.build_model_settings(
        _spec("openai", thinking="low", settings={"temperature": 0.2})
    )
    assert s["temperature"] == 0.2
    assert s["openai_reasoning_effort"] == "low"


# -- build_model ---------------------------------------------------------------


def test_build_model_unknown_provider_raises_agenterror():
    with pytest.raises(AgentError):
        adapter.build_model(_spec("cohere"))


@pytest.mark.parametrize(
    "provider,prefix",
    [("google", "google"), ("anthropic", "anthropic"), ("openai", "openai"), ("bedrock", "bedrock")],
)
def test_build_model_uses_provider_prefix(provider, prefix, monkeypatch):
    captured = {}

    def fake_infer(model_str):
        captured["model_str"] = model_str
        return object()

    monkeypatch.setattr("pydantic_ai.models.infer_model", fake_infer)
    adapter.build_model(_spec(provider, model="X"))
    assert captured["model_str"] == f"{prefix}:X"
