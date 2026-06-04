/**
 * UsageGauge -- compact token-usage readout for the HeaderBar right cluster.
 *
 * Shows the accumulated input/output token counts for the primary agent's
 * conversation (sourced from the projection's per-agent usage accumulation).
 * Presentational: all data arrives via props, no store access.
 *
 * Used in: HeaderBar (workflow mode), beside the orchestrator model + elapsed.
 */

import './UsageGauge.css'

interface UsageGaugeProps {
  inputTokens: number
  outputTokens: number
}

/** Compact a token count: 12345 -> "12.3k", 850 -> "850". */
function fmtTokens(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return String(n)
}

export function UsageGauge({ inputTokens, outputTokens }: UsageGaugeProps) {
  const title =
    `${inputTokens.toLocaleString()} input tokens / ` +
    `${outputTokens.toLocaleString()} output tokens`
  return (
    <span className="ug" title={title}>
      <span className="ug-label">tok</span>
      <span className="ug-val">{fmtTokens(inputTokens)} in</span>
      <span className="ug-sep">/</span>
      <span className="ug-val">{fmtTokens(outputTokens)} out</span>
    </span>
  )
}

export default UsageGauge
