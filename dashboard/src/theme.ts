/**
 * Chart + status tokens.
 *
 * The categorical order is not cosmetic — it is the CVD-safety mechanism.
 * Validated against the dark chart surface (#0e0e11) with the palette validator:
 *
 *   adjacent pairs : CVD ΔE 9.4 (deutan) / 8.7 (tritan), normal-vision ΔE 19.3
 *   all pairs      : passes for the FIRST FOUR slots only
 *
 * Slots 5+ fail all-pairs (yellow vs orange, normal-vision ΔE 10.6), so any
 * chart that shows every series at once — the sector donut — caps at four and
 * folds the rest into "Other". Do not extend or re-order without re-running:
 *
 *   node scripts/validate_palette.js "<hexes>" --mode dark --surface "#0e0e11"
 */
export const SERIES = [
  '#8315f9', // 1 violet  (brand)
  '#199e70', // 2 aqua
  '#d95926', // 3 orange
  '#3987e5', // 4 blue
  '#c98500', // 5 yellow  — adjacent-safe only
  '#d55181', // 6 magenta — adjacent-safe only
] as const

/** Max distinct hues in a chart where all series are visible simultaneously. */
export const ALL_PAIRS_CAP = 4

/** Neutral for the folded "Other" bucket — never one of the categorical hues. */
export const OTHER_COLOR = '#6b6b76'

/** Reserved status colors. Never reused as a series, always with icon + label. */
export const STATUS = {
  good: '#0ca30c',
  warning: '#fab219',
  serious: '#ec835a',
  critical: '#d03b3b',
} as const

/** Chart chrome. */
export const CHART = {
  surface: '#0e0e11',
  grid: 'rgba(255,255,255,0.07)',
  axis: '#6b6b76',
  textPrimary: '#fafafa',
  textSecondary: '#a1a1aa',
} as const

/** Shared Recharts tooltip styling so every chart reads as one system. */
export const tooltipStyle = {
  backgroundColor: '#141417',
  border: '1px solid rgba(255,255,255,0.13)',
  borderRadius: '7px',
  color: CHART.textPrimary,
  fontSize: '0.8rem',
  boxShadow: '0 8px 24px -8px rgba(0,0,0,0.8)',
} as const

export const tooltipItemStyle = { color: CHART.textSecondary } as const
export const tooltipLabelStyle = { color: CHART.textPrimary, fontWeight: 600 } as const

/**
 * Fold a categorical distribution down to the all-pairs-safe cap.
 * Keeps the largest buckets and sums the tail into a neutral "Other".
 */
export function foldToCap<T extends { name: string; value: number }>(
  rows: T[],
  cap: number = ALL_PAIRS_CAP,
): Array<{ name: string; value: number; color: string }> {
  const sorted = [...rows].sort((a, b) => b.value - a.value)
  const head = sorted.slice(0, cap).map((r, i) => ({ ...r, color: SERIES[i] }))
  const tail = sorted.slice(cap)
  if (tail.length === 0) return head

  return [
    ...head,
    {
      name: `Other (${tail.length})`,
      value: tail.reduce((sum, r) => sum + r.value, 0),
      color: OTHER_COLOR,
    },
  ]
}

/** Score colour thresholds, shared by the deal list, radar and score bars. */
export function scoreColor(score: number | null | undefined): string {
  if (score == null) return CHART.axis
  if (score >= 7) return STATUS.good
  if (score >= 5) return STATUS.warning
  return STATUS.critical
}

export function recommendationColor(rec: string | null | undefined): string {
  switch ((rec ?? '').toUpperCase()) {
    case 'INVEST':
      return STATUS.good
    case 'CONSIDER':
      return STATUS.warning
    case 'PASS':
      return STATUS.critical
    default:
      return CHART.axis
  }
}
