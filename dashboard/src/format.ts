/** Display formatting shared across panels. */

export function formatUsd(n: number | null | undefined): string | null {
  if (n == null || !isFinite(n)) return null
  if (n >= 1e9) return `$${(n / 1e9).toFixed(n >= 1e10 ? 0 : 1).replace(/\.0$/, '')}B`
  if (n >= 1e6) return `$${(n / 1e6).toFixed(n >= 1e8 ? 0 : 1).replace(/\.0$/, '')}M`
  if (n >= 1e3) return `$${Math.round(n / 1e3)}K`
  return `$${n}`
}

export function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url.slice(0, 40)
  }
}

export function shortDate(value: string): string {
  const d = new Date(value)
  return isNaN(d.getTime()) ? value.slice(0, 10) : d.toLocaleDateString()
}
