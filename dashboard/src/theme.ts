/**
 * Comic design tokens for charts, pins and verdicts.
 *
 * The page palette — cream canvas, ink lines, hard offset shadows — lives in
 * style.css as CSS variables. These are the same values for the places CSS
 * can't reach: Recharts props and MapLibre paint properties.
 */
export const INK = '#161713'
export const PAPER = '#fffaf0'
export const CANVAS = '#f3ead5'
export const POP = '#ffd928'
export const PINK = '#ff5f91'
export const CYAN = '#5dd9e7'
export const MUTED = '#dfd5bf'
export const MUTED_INK = '#5e5b52'

/**
 * Verdict colours — the one categorical encoding on the map (pin fill).
 *
 * Blue for INVEST rather than the conventional green: green and red collapse
 * under deuteranopia (ΔE 3.0), which is exactly the pair a reader most needs to
 * tell apart. Validated with the dataviz palette validator against the canvas:
 *
 *   node validate_palette.js "#2378c9,#e0a100,#d8345f" --mode light \
 *     --surface "#f3ead5" --pairs all
 *   → CVD worst ΔE 16.9 (protan), normal-vision worst ΔE 26.1
 *
 * Amber is below 3:1 against the canvas, so a verdict colour never stands
 * alone: every pin has an ink outline and its score printed inside, every badge
 * carries the verdict word, and the map has a legend.
 */
export const VERDICT = {
  INVEST: '#2378c9',
  CONSIDER: '#e0a100',
  PASS: '#d8345f',
} as const

/** Text that sits on a verdict fill — chosen per fill for contrast. */
export const VERDICT_TEXT: Record<keyof typeof VERDICT, string> = {
  INVEST: PAPER,
  CONSIDER: INK,
  PASS: PAPER,
}

export const UNSCORED = '#a39a85'

/** Chart chrome. Marks are ink-outlined, so their fill is decoration, not contrast. */
export const CHART = {
  surface: PAPER,
  grid: 'rgba(22, 23, 19, 0.14)',
  axis: MUTED_INK,
  textPrimary: INK,
  textSecondary: MUTED_INK,
  /** The single-series fill. One colour: the axis already carries identity. */
  series: CYAN,
  seriesStroke: INK,
} as const

/** Shared Recharts tooltip — a paper card with an ink border and offset shadow. */
export const tooltipStyle = {
  backgroundColor: PAPER,
  border: `2px solid ${INK}`,
  borderRadius: 0,
  color: INK,
  fontSize: '0.8rem',
  fontFamily: 'var(--mono-face)',
  boxShadow: `3px 3px 0 ${INK}`,
} as const

export const tooltipItemStyle = { color: INK, fontWeight: 700 } as const
export const tooltipLabelStyle = { color: INK, fontWeight: 900, textTransform: 'uppercase' } as const

/** Dimension-score colour, on the same three steps as the verdicts. */
export function scoreColor(score: number | null | undefined): string {
  if (score == null) return UNSCORED
  if (score >= 7) return VERDICT.INVEST
  if (score >= 5) return VERDICT.CONSIDER
  return VERDICT.PASS
}
