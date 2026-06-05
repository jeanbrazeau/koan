# KoanConfig dataclass and config file loader/saver.
# Storage: ~/.koan/config.json -- mirrors src/planner/model-config.ts.

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from .types import (
    BUILTIN_PROFILE_NAMES,
    CachingPolicy,
    ModelSpec,
    Profile,
    ProfileTier,
    ProviderAuth,
    ThinkingMode,
)

log = logging.getLogger("koan.config")

CONFIG_PATH = Path.home() / ".koan" / "config.json"


@dataclass
class KoanConfig:
    """Driver-internal config root; provider-based shape replaces the CLI-binary model."""

    provider_auth: list[ProviderAuth] = field(default_factory=list)
    profiles: list[Profile] = field(default_factory=list)
    active_profile: str = "balanced"
    scout_concurrency: int = 8

    # agent_installations compat-shim removed in M4: all callers migrated to
    # provider_auth in M1/M3; api_agents_list deleted in M4.


# -- Write lock (lazily initialized) ------------------------------------------

_config_write_lock: asyncio.Lock | None = None


def _get_write_lock() -> asyncio.Lock:
    global _config_write_lock
    if _config_write_lock is None:
        _config_write_lock = asyncio.Lock()
    return _config_write_lock


# -- Parsers -------------------------------------------------------------------

def _parse_model_spec(raw: dict) -> ModelSpec:
    """Parse a ModelSpec from a camelCase config dict.

    Expects keys: provider, model, thinking, settings (optional dict),
    caching (optional sub-object with mode/ttl), contextWindow (optional int).
    Falls back gracefully for any missing key.
    """
    caching_raw = raw.get("caching") or {}
    caching = CachingPolicy(
        mode=caching_raw.get("mode", "auto"),
        ttl=caching_raw.get("ttl", "5m"),
    )
    return ModelSpec(
        provider=raw.get("provider", ""),
        model=raw.get("model", ""),
        thinking=raw.get("thinking", "disabled"),
        settings=raw.get("settings") or {},
        caching=caching,
        context_window=int(raw.get("contextWindow") or 0),
    )


def _parse_provider_auth(raw: list) -> list[ProviderAuth]:
    """Parse a list of ProviderAuth from camelCase config dicts.

    Expects each entry to have: provider, envKeys (list), region (opt), baseUrl (opt).
    """
    results: list[ProviderAuth] = []
    if not isinstance(raw, list):
        return results
    for entry in raw:
        if not isinstance(entry, dict):
            log.warning("providerAuth entry is not an object; skipping.")
            continue
        provider = entry.get("provider", "")
        if not provider:
            log.warning("providerAuth entry missing provider; skipping.")
            continue
        env_keys = entry.get("envKeys", [])
        if not isinstance(env_keys, list):
            env_keys = []
        results.append(ProviderAuth(
            provider=provider,
            env_keys=[str(k) for k in env_keys],
            region=entry.get("region") or None,
            base_url=entry.get("baseUrl") or None,
        ))
    return results


def _parse_profiles(raw: list) -> list[Profile]:
    """Parse a list of Profile from config dicts.

    Each profile tier value is a ModelSpec dict (provider/model/thinking/settings/caching/contextWindow).
    """
    results: list[Profile] = []
    if not isinstance(raw, list):
        return results
    for entry in raw:
        if not isinstance(entry, dict):
            log.warning("profiles entry is not an object; skipping.")
            continue
        name = entry.get("name", "")
        if not name:
            log.warning("profiles entry missing name; skipping.")
            continue
        tiers_raw = entry.get("tiers", {})
        if not isinstance(tiers_raw, dict):
            log.warning("profiles[%s].tiers is not an object; skipping.", name)
            continue
        tiers: dict[str, ProfileTier] = {}
        for tier_name, tier_val in tiers_raw.items():
            if not isinstance(tier_val, dict):
                log.warning("profiles[%s].tiers[%s] is not an object; skipping tier.", name, tier_name)
                continue
            provider = tier_val.get("provider", "")
            model = tier_val.get("model", "")
            if not provider or not model:
                log.warning("profiles[%s].tiers[%s] missing provider/model; skipping tier.", name, tier_name)
                continue
            tiers[tier_name] = ProfileTier(model=_parse_model_spec(tier_val))
        results.append(Profile(name=name, tiers=tiers))
    return results


def _parse_scout_concurrency(raw: dict) -> int:
    if not isinstance(raw, dict):
        return 8
    sc = raw.get("scoutConcurrency")
    if isinstance(sc, bool):
        return 8
    if isinstance(sc, int) and sc > 0:
        return sc
    return 8


# -- Loaders / savers ---------------------------------------------------------

async def load_koan_config() -> KoanConfig:
    """Load KoanConfig from ~/.koan/config.json.

    Reads providerAuth and profiles from camelCase JSON; returns defaults on
    missing or invalid file. Built-in profiles (balanced, frontier) are excluded
    from the persisted profiles -- they are recomputed at startup.
    """
    defaults = KoanConfig()

    try:
        text = CONFIG_PATH.read_text("utf-8")
    except FileNotFoundError:
        return defaults

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        log.warning("config.json is not valid JSON; treating config as absent.")
        return defaults

    if not isinstance(parsed, dict):
        log.warning("config.json top-level value is not an object; treating config as absent.")
        return defaults

    active_profile = parsed.get("activeProfile", "balanced")
    if not isinstance(active_profile, str) or not active_profile:
        active_profile = "balanced"

    # Exclude built-in profiles from persisted profiles -- they are recomputed at startup
    profiles = [p for p in _parse_profiles(parsed.get("profiles", [])) if p.name not in BUILTIN_PROFILE_NAMES]

    return KoanConfig(
        provider_auth=_parse_provider_auth(parsed.get("providerAuth", [])),
        profiles=profiles,
        active_profile=active_profile,
        scout_concurrency=_parse_scout_concurrency(parsed),
    )


async def save_koan_config(config: KoanConfig) -> None:
    """Write KoanConfig to ~/.koan/config.json atomically via a tmp-file rename.

    Serializes providerAuth (camelCase) and profiles with ModelSpec tiers.
    Strips the legacy agentInstallations key from existing files on write.
    """
    async with _get_write_lock():
        config_dir = CONFIG_PATH.parent
        config_dir.mkdir(parents=True, exist_ok=True)

        existing: dict = {}
        try:
            existing = json.loads(CONFIG_PATH.read_text("utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            pass

        # Remove legacy keys (agentInstallations replaced by providerAuth)
        existing.pop("modelTiers", None)
        existing.pop("activeInstallations", None)
        existing.pop("agentInstallations", None)

        # Serialize provider_auth
        existing["providerAuth"] = [
            {
                "provider": pa.provider,
                "envKeys": pa.env_keys,
                **({"region": pa.region} if pa.region else {}),
                **({"baseUrl": pa.base_url} if pa.base_url else {}),
            }
            for pa in config.provider_auth
        ]

        # Serialize active_profile (omit if default)
        if config.active_profile != "balanced":
            existing["activeProfile"] = config.active_profile
        else:
            existing.pop("activeProfile", None)

        # Serialize profiles (user-defined only; built-in profiles never persisted)
        existing["profiles"] = [
            {
                "name": p.name,
                "tiers": {
                    tier_name: {
                        "provider": pt.model.provider,
                        "model": pt.model.model,
                        "thinking": pt.model.thinking,
                        "settings": pt.model.settings,
                        "caching": {
                            "mode": pt.model.caching.mode,
                            "ttl": pt.model.caching.ttl,
                        },
                        "contextWindow": pt.model.context_window,
                    }
                    for tier_name, pt in p.tiers.items()
                },
            }
            for p in config.profiles
            if p.name not in BUILTIN_PROFILE_NAMES
        ]

        existing["scoutConcurrency"] = config.scout_concurrency

        tmp_path = CONFIG_PATH.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(existing, indent=2) + "\n", "utf-8")
        tmp_path.rename(CONFIG_PATH)
