export function formatTokens(sent: number, recv: number): string {
  const fmt = (n: number) => {
    if (!n) return '--'
    if (n < 1000) return String(n)
    return Math.round(n / 1000) + 'k'
  }
  return `${fmt(sent)} / ${fmt(recv)}`
}

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function tierSummary(tiers: Record<string, { model?: string }>): string {
  const parts: string[] = []
  for (const t of ['strong', 'standard', 'cheap']) {
    if (tiers[t]?.model) parts.push(`${t}: ${tiers[t].model}`)
  }
  return parts.join(' | ') || '--'
}
