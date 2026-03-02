// Spawn-time model resolver for per-phase model overrides.
// Maps spawn contexts to PhaseModelKeys and looks up configured overrides.
// Returns undefined when no config exists so the caller omits --model entirely,
// preserving pi's current active model as the implicit fallback.

import { buildPhaseModelKey, type PhaseModelKey, type PhaseRow } from "./model-phase.js";
import { loadPhaseModelConfig } from "./model-config.js";

export type SpawnContext = "work-debut" | "fix" | "qr-decompose" | "qr-verify";

export function mapSpawnContextToPhaseModelKey(
  context: SpawnContext,
  phaseRow: PhaseRow,
  // Reserved for future fix-phase-specific routing. Current mapping is phase-row + context only.
  _fixPhase?: string,
): PhaseModelKey {
  switch (context) {
    case "work-debut":
      return buildPhaseModelKey(phaseRow, "exec-debut");
    case "fix":
      return buildPhaseModelKey(phaseRow, "exec-fix");
    case "qr-decompose":
      return buildPhaseModelKey(phaseRow, "qr-decompose");
    case "qr-verify":
      return buildPhaseModelKey(phaseRow, "qr-verify");
  }
}

export async function resolvePhaseModelOverride(key: PhaseModelKey): Promise<string | undefined> {
  const config = await loadPhaseModelConfig();
  if (config === null) return undefined;
  return config[key];
}
