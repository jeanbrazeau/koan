// Koan config persistence for per-phase model overrides.
// Storage location: ~/.koan/config.json under a `phaseModels` key.
// Enforces all-or-none semantics: a stored config must contain exactly all
// 20 PhaseModelKeys. Partial configs are treated as absent and logged.

import { promises as fs } from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

import {
  ALL_PHASE_MODEL_KEYS,
  isPhaseModelKey,
  type PhaseModelKey,
} from "./model-phase.js";

export const KOAN_CONFIG_PATH = path.join(os.homedir(), ".koan", "config.json");

interface KoanConfigFile {
  phaseModels?: Record<string, string>;
  [key: string]: unknown;
}

export async function loadPhaseModelConfig(): Promise<Record<PhaseModelKey, string> | null> {
  let raw: string;
  try {
    raw = await fs.readFile(KOAN_CONFIG_PATH, "utf8");
  } catch {
    return null;
  }

  let parsed: KoanConfigFile;
  try {
    parsed = JSON.parse(raw) as KoanConfigFile;
  } catch {
    console.warn("[koan] config.json is not valid JSON; treating phase model config as absent.");
    return null;
  }

  if (!parsed.phaseModels || typeof parsed.phaseModels !== "object") {
    return null;
  }

  const phaseModels = parsed.phaseModels;
  const keys = Object.keys(phaseModels);

  if (keys.length !== ALL_PHASE_MODEL_KEYS.length) {
    console.warn(
      `[koan] config.json phaseModels has ${keys.length} entries (expected ${ALL_PHASE_MODEL_KEYS.length}); treating as absent.`,
    );
    return null;
  }

  const result: Partial<Record<PhaseModelKey, string>> = {};
  for (const key of keys) {
    if (!isPhaseModelKey(key)) {
      console.warn(`[koan] config.json phaseModels contains unknown key "${key}"; treating as absent.`);
      return null;
    }
    const value = phaseModels[key];
    if (typeof value !== "string" || value.length === 0) {
      console.warn(
        `[koan] config.json phaseModels["${key}"] is not a non-empty string; treating as absent.`,
      );
      return null;
    }
    result[key] = value;
  }

  for (const expected of ALL_PHASE_MODEL_KEYS) {
    if (!(expected in result)) {
      console.warn(`[koan] config.json phaseModels is missing key "${expected}"; treating as absent.`);
      return null;
    }
  }

  return result as Record<PhaseModelKey, string>;
}

export async function savePhaseModelConfig(
  config: Record<PhaseModelKey, string> | null,
): Promise<void> {
  const configDir = path.dirname(KOAN_CONFIG_PATH);
  await fs.mkdir(configDir, { recursive: true });

  let existing: KoanConfigFile = {};
  try {
    const raw = await fs.readFile(KOAN_CONFIG_PATH, "utf8");
    existing = JSON.parse(raw) as KoanConfigFile;
  } catch {
    // Start fresh if file is missing or contains invalid JSON.
  }

  if (config === null) {
    delete existing.phaseModels;
  } else {
    existing.phaseModels = config as Record<string, string>;
  }

  const tmpPath = `${KOAN_CONFIG_PATH}.tmp`;
  await fs.writeFile(tmpPath, `${JSON.stringify(existing, null, 2)}\n`, "utf8");
  await fs.rename(tmpPath, KOAN_CONFIG_PATH);
}
