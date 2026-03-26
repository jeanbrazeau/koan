# KoanConfig dataclass and config file loader/saver.
# Storage: ~/.koan/config.json -- mirrors src/planner/model-config.ts.

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from .types import ALL_MODEL_TIERS

log = logging.getLogger("koan.config")

CONFIG_PATH = Path.home() / ".koan" / "config.json"


@dataclass
class ModelTierConfig:
    strong: str = ""
    standard: str = ""
    cheap: str = ""


@dataclass
class KoanConfig:
    model_tiers: ModelTierConfig | None = None
    scout_concurrency: int = 8


# -- Loaders / savers --------------------------------------------------------

def _parse_model_tiers(raw: dict) -> ModelTierConfig | None:
    if not isinstance(raw, dict):
        return None
    mt = raw.get("modelTiers")
    if not isinstance(mt, dict):
        return None

    if len(mt) != len(ALL_MODEL_TIERS):
        log.warning(
            "config.json modelTiers has %d entries (expected %d); treating as absent.",
            len(mt),
            len(ALL_MODEL_TIERS),
        )
        return None

    values = {}
    for tier in ALL_MODEL_TIERS:
        if tier not in mt:
            log.warning('config.json modelTiers is missing key "%s"; treating as absent.', tier)
            return None
        v = mt[tier]
        if not isinstance(v, str) or len(v) == 0:
            log.warning('config.json modelTiers["%s"] is not a non-empty string; treating as absent.', tier)
            return None
        values[tier] = v

    for k in mt:
        if k not in ALL_MODEL_TIERS:
            log.warning('config.json modelTiers contains unknown key "%s"; treating as absent.', k)
            return None

    return ModelTierConfig(**values)


def _parse_scout_concurrency(raw: dict) -> int:
    if not isinstance(raw, dict):
        return 8
    sc = raw.get("scoutConcurrency")
    if isinstance(sc, bool):
        return 8
    if isinstance(sc, int) and sc > 0:
        return sc
    return 8


async def load_koan_config() -> KoanConfig:
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

    return KoanConfig(
        model_tiers=_parse_model_tiers(parsed),
        scout_concurrency=_parse_scout_concurrency(parsed),
    )


async def save_koan_config(config: KoanConfig) -> None:
    config_dir = CONFIG_PATH.parent
    config_dir.mkdir(parents=True, exist_ok=True)

    existing: dict = {}
    try:
        existing = json.loads(CONFIG_PATH.read_text("utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    if config.model_tiers is not None:
        existing["modelTiers"] = {
            "strong": config.model_tiers.strong,
            "standard": config.model_tiers.standard,
            "cheap": config.model_tiers.cheap,
        }

    existing["scoutConcurrency"] = config.scout_concurrency

    tmp_path = CONFIG_PATH.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(existing, indent=2) + "\n", "utf-8")
    tmp_path.rename(CONFIG_PATH)
