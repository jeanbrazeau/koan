import { useState, useEffect } from 'react'

function formatElapsed(ms: number): string {
  const s = Math.floor(ms / 1000)
  const m = Math.floor(s / 60)
  return `${m}m ${String(s % 60).padStart(2, '0')}s`
}

// useElapsed computes a human-readable elapsed time string that updates every
// second. Replaces the DOM-scanning setInterval hack from koan.js that read
// data-started-at attributes.
export function useElapsed(startedAt: number): string {
  const [elapsed, setElapsed] = useState(() => formatElapsed(Date.now() - startedAt))

  useEffect(() => {
    const id = setInterval(() => {
      setElapsed(formatElapsed(Date.now() - startedAt))
    }, 1000)
    return () => clearInterval(id)
  }, [startedAt])

  return elapsed
}
