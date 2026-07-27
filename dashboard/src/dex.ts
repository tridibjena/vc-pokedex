/**
 * Dex domain helpers — numbering, sector "types", and stage evolution.
 *
 * Sector colour is a *type badge*: the label always sits next to the swatch, so
 * identity is never carried by hue alone. That is what lets this exceed the
 * 4-hue all-pairs cap that constrains the charts in theme.ts, where a slice or
 * a bar has no text on it.
 */
import { SERIES, STATUS } from './theme'

export const STAGES = ['pre-seed', 'seed', 'series-a', 'series-b', 'growth'] as const
export type Stage = (typeof STAGES)[number]

const STAGE_SHORT: Record<string, string> = {
  'pre-seed': 'PRE',
  seed: 'SEED',
  'series-a': 'A',
  'series-b': 'B',
  growth: 'GROWTH',
}

/** Stable palette for sector badges, keyed by name so a filter never repaints. */
const TYPE_COLORS: Record<string, string> = {
  saas: SERIES[0],
  devtools: '#c15df5',
  data: '#0891b2',
  security: '#e11d48',
  marketplace: SERIES[2],
  logistics: '#a16207',
  robotics: '#a16207',
  gaming: '#c15df5',
  edtech: '#14b8a6',
  proptech: '#65a30d',
  hardware: '#a16207',
  technology: SERIES[0],
  ai: '#c15df5',
  fintech: SERIES[3],
  insurtech: SERIES[3],
  biotech: SERIES[1],
  healthtech: '#14b8a6',
  consumer: SERIES[2],
  cleantech: '#65a30d',
  agtech: '#65a30d',
  industrials: '#a16207',
  telecom: '#0891b2',
  'business services': '#7c7c88',
}

const FALLBACK_TYPE_COLOR = '#6b6b76'

/**
 * Collapse a free-text sector onto the canonical vocabulary.
 *
 * The extractor is now constrained to a fixed list, but entries scanned before
 * that came back with prose like "Consumer Technology and Logistics" or
 * "Software Development / AI", which blew out the filter bar and truncated every
 * type stamp. Normalising on read keeps old records tidy without a migration.
 */
const SECTOR_ALIASES: Array<[RegExp, string]> = [
  [/\bdev(eloper)?\s*tools?\b|\bdeveloper\b/i, 'DevTools'],
  [/\bfin\s*tech|financial services|banking|payments?\b/i, 'FinTech'],
  [/\binsur/i, 'InsurTech'],
  [/\bbio|pharma|therapeutic|genomic/i, 'Biotech'],
  [/\bhealth|medical|clinic/i, 'HealthTech'],
  [/\blogistic|supply chain|freight|shipping/i, 'Logistics'],
  [/\bmarketplace|e-?commerce|retail/i, 'Marketplace'],
  [/\bclean\s*tech|climate|energy|sustainab/i, 'CleanTech'],
  [/\bagri|agtech|farm/i, 'AgTech'],
  [/\bsecurity|cyber/i, 'Security'],
  [/\brobotic|drone/i, 'Robotics'],
  [/\bgaming|games?\b/i, 'Gaming'],
  [/\bed\s*tech|education|learning/i, 'EdTech'],
  [/\bprop\s*tech|real estate/i, 'PropTech'],
  [/\btelecom|network/i, 'Telecom'],
  [/\bhardware|semiconductor|chip/i, 'Hardware'],
  [/\bdata\b|analytics|database/i, 'Data'],
  [/\bconsumer\b/i, 'Consumer'],
  [/\benterprise\b|\bb2b\b/i, 'SaaS'],
  [/\bsaas\b|software|platform/i, 'SaaS'],
  [/\bai\b|artificial intelligence|machine learning|\bllm\b/i, 'AI'],
  [/\bindustrial|manufactur/i, 'Industrials'],
]

/** The canonical labels, indexed lowercase for case-insensitive matching. */
const CANONICAL = [
  'AI', 'DevTools', 'SaaS', 'FinTech', 'InsurTech', 'Biotech', 'HealthTech',
  'Consumer', 'Marketplace', 'Logistics', 'CleanTech', 'AgTech', 'Security',
  'Data', 'Hardware', 'Robotics', 'Gaming', 'EdTech', 'PropTech', 'Industrials',
  'Telecom', 'Other',
]
const CANONICAL_BY_KEY = new Map(CANONICAL.map((c) => [c.toLowerCase(), c]))

export function shortSector(sector: string | null | undefined): string {
  const raw = (sector ?? '').trim()
  if (!raw || raw === '???') return raw || 'Unknown'

  // Canonicalize casing first: "Fintech", "FinTech" and "fintech" must collapse
  // to one label, or the filter renders a chip per spelling.
  const exact = CANONICAL_BY_KEY.get(raw.toLowerCase())
  if (exact) return exact

  for (const [re, label] of SECTOR_ALIASES) {
    if (re.test(raw)) return label
  }
  if (raw.length <= 12 && !/\s/.test(raw)) return raw
  return raw.length > 14 ? raw.slice(0, 13).trimEnd() + '…' : raw
}

export function typeColor(sector: string | null | undefined): string {
  const key = shortSector(sector).trim().toLowerCase()
  return TYPE_COLORS[key] ?? TYPE_COLORS[(sector ?? '').trim().toLowerCase()] ?? FALLBACK_TYPE_COLOR
}

export function stageShort(stage: string | null | undefined): string {
  return STAGE_SHORT[(stage ?? '').trim().toLowerCase()] ?? '?'
}

/** Index of a stage in the evolution chain, or -1 when unrecognized. */
export function stageIndex(stage: string | null | undefined): number {
  return STAGES.indexOf((stage ?? '').trim().toLowerCase() as Stage)
}

/** Zero-padded dex number, e.g. 1 -> "001". */
export function dexNumber(n: number): string {
  return String(n).padStart(3, '0')
}

export interface DexEntry {
  key: string
  dex: number
  dealId: string | null
  /** Needed to delete the entry — the API keys removal on file_id. */
  fileId: string | null
  companyName: string
  sector: string
  stage: string
  overallScore: number | null
  recommendation: string | null
  stats: Array<{ key: string; label: string; value: number }>
  pending: boolean
  createdAt?: string
  lastRound?: string | null
  roundAmount?: number | null
  valuation?: number | null
}

export const STAT_KEYS = [
  { key: 'market_size_score', label: 'MKT' },
  { key: 'team_score', label: 'TEA' },
  { key: 'traction_score', label: 'TRA' },
  { key: 'competitive_moat_score', label: 'MOA' },
  { key: 'financial_health_score', label: 'FIN' },
] as const

interface RawDeal {
  deal_id: string
  company_name: string
  sector: string
  stage: string
  overall_score: number | null
  recommendation: string | null
  created_at: string
  file_id?: string | null
  scores?: Record<string, number> | null
  last_round?: string | null
  round_amount?: number | null
  valuation?: number | null
}

interface RawDoc {
  file_id?: string
  company_name?: string
  filename?: string
  ingested_at?: string
}

/**
 * Merge analyzed deals with still-ingesting documents into one dex.
 *
 * A document whose file_id has no deal yet is a job the background analyzer
 * hasn't finished — rendered as an unidentified silhouette rather than hidden,
 * so the async pipeline is visible instead of silent.
 */
export function buildDex(deals: RawDeal[], documents: RawDoc[]): DexEntry[] {
  // Dex numbers follow ingestion order, so a company's number never changes as
  // new deals arrive or the list is re-sorted.
  const ordered = [...deals].sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
  )

  const entries: DexEntry[] = ordered.map((d, i) => ({
    key: d.deal_id,
    dex: i + 1,
    dealId: d.deal_id,
    fileId: d.file_id ?? null,
    companyName: d.company_name,
    sector: d.sector,
    stage: d.stage,
    overallScore: d.overall_score,
    recommendation: d.recommendation,
    stats: STAT_KEYS.filter((s) => d.scores?.[s.key] != null).map((s) => ({
      key: s.key,
      label: s.label,
      value: Number(d.scores![s.key]),
    })),
    pending: false,
    createdAt: d.created_at,
    lastRound: d.last_round,
    roundAmount: d.round_amount,
    valuation: d.valuation,
  }))

  const analyzedFileIds = new Set(
    deals.map((d) => d.file_id).filter((v): v is string => Boolean(v)),
  )
  const analyzedNames = new Set(ordered.map((d) => d.company_name.toLowerCase()))

  let next = entries.length + 1
  for (const doc of documents) {
    const fid = doc.file_id
    const name = (doc.company_name || doc.filename || 'Unknown').trim()
    const alreadyAnalyzed =
      (fid && analyzedFileIds.has(fid)) || analyzedNames.has(name.toLowerCase())
    if (alreadyAnalyzed) continue

    entries.push({
      key: fid || `pending-${name}`,
      dex: next++,
      dealId: null,
      fileId: fid ?? null,
      companyName: name,
      sector: '???',
      stage: '???',
      overallScore: null,
      recommendation: null,
      stats: [],
      pending: true,
      createdAt: doc.ingested_at,
    })
  }

  return entries
}

/**
 * Verdict colour.
 *
 * Keyed on the recommendation, NOT the score. Colouring by score produced cards
 * that argued with themselves — an 8.2 rendered green while its label read
 * CONSIDER. The recommendation is the actual call; the score is its magnitude.
 */
export function verdictColor(recommendation: string | null | undefined, score?: number | null): string {
  switch ((recommendation ?? '').trim().toUpperCase()) {
    case 'INVEST':
      return STATUS.good
    case 'CONSIDER':
      return STATUS.warning
    case 'PASS':
      return STATUS.critical
    default:
      break
  }
  if (score == null) return '#6b6b76'
  return score >= 7 ? STATUS.good : score >= 5 ? STATUS.warning : STATUS.critical
}

/** @deprecated kept for callers that only have a score. */
export function scoreTierColor(score: number | null): string {
  return verdictColor(null, score)
}
