// Canonical phase-model key definitions for koan per-phase model selection.
// Defines the 5×4 matrix of (phase row × sub-phase column) keys used across
// configuration, UI, and spawn-time resolution.

export type PhaseRow = "plan-design" | "plan-code" | "plan-docs" | "exec-code" | "exec-docs";
export type SubPhase = "exec-debut" | "exec-fix" | "qr-decompose" | "qr-verify";
export type PhaseModelKey = `${PhaseRow}-${SubPhase}`;

export const PHASE_ROWS: readonly PhaseRow[] = [
  "plan-design",
  "plan-code",
  "plan-docs",
  "exec-code",
  "exec-docs",
];

export const SUB_PHASES: readonly SubPhase[] = [
  "exec-debut",
  "exec-fix",
  "qr-decompose",
  "qr-verify",
];

function computeAllKeys(): PhaseModelKey[] {
  const keys: PhaseModelKey[] = [];
  for (const row of PHASE_ROWS) {
    for (const col of SUB_PHASES) {
      keys.push(`${row}-${col}`);
    }
  }
  return keys;
}

export const ALL_PHASE_MODEL_KEYS: readonly PhaseModelKey[] = computeAllKeys();

const STRONG_KEY_SET: Set<PhaseModelKey> = new Set([
  // All qr-decompose keys (bias reasoning budget to verification)
  "plan-design-qr-decompose",
  "plan-code-qr-decompose",
  "plan-docs-qr-decompose",
  "exec-code-qr-decompose",
  "exec-docs-qr-decompose",
  // plan-design exec keys (ripple effects across later work)
  "plan-design-exec-debut",
  "plan-design-exec-fix",
  // exec-docs exec keys (no mechanical correctness backstop)
  "exec-docs-exec-debut",
  "exec-docs-exec-fix",
]);

export const STRONG_PHASE_MODEL_KEYS: ReadonlySet<PhaseModelKey> = STRONG_KEY_SET;

export const GENERAL_PURPOSE_PHASE_MODEL_KEYS: readonly PhaseModelKey[] =
  ALL_PHASE_MODEL_KEYS.filter((k) => !STRONG_KEY_SET.has(k));

export function isPhaseModelKey(value: unknown): value is PhaseModelKey {
  if (typeof value !== "string") return false;
  return (ALL_PHASE_MODEL_KEYS as readonly string[]).includes(value);
}

export function buildPhaseModelKey(phaseRow: PhaseRow, subPhase: SubPhase): PhaseModelKey {
  return `${phaseRow}-${subPhase}`;
}
