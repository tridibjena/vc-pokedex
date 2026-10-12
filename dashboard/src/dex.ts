/**
 * Dex domain helpers — numbering, sector "types", verdicts and stage evolution.
 *
 * Sector colour is a *type badge*: the label always sits on the swatch, so
 * identity never rides on hue alone. That is what lets the badge palette run
 * past the handful of hues a chart could carry. The map does not colour by
 * sector — pins carry the verdict instead (see theme.ts).
 */
import { UNSCORED, VERDICT, VERDICT_TEXT, scoreColor } from './theme'

export const STAGES = ['pre-seed', 'seed', 'series-a', 'series-b', 'growth'] as const
export type Stage = (typeof STAGES)[number]

const STAGE_SHORT: Record<string, string> = {
  'pre-seed': 'PRE',
  seed: 'SEED',
  'series-a': 'A',
  'series-b': 'B',
  growth: 'GROWTH',
}

/** Pastel badge fills, read with ink text. Keyed by name so a filter never repaints. */
const TYPE_COLORS: Record<string, string> = {
  ai: '#b995ff',
  devtools: '#91a8ff',
  saas: '#5dd9e7',
  technology: '#5dd9e7',
  fintech: '#7fd06d',
  insurtech: '#a8ddd0',
  biotech: '#ff9f57',
  healthtech: '#6fe0c0',
  consumer: '#ff8fb1',
  marketplace: '#ffb7cb',
  logistics: '#e8c07a',
  cleantech: '#a6d96a',
  agtech: '#c9e27a',
  security: '#ef6b5b',
  data: '#8fd3ff',
  hardware: '#cdb68c',
  robotics: '#f0a6e8',
  gaming: '#d6a6ff',
  edtech: '#ffd928',
  proptech: '#e2c290',
  industrials: '#c4b89f',
  telecom: '#9fc3ff',
  'business services': '#d9cdb4',
  other: '#dfd5bf',
}

const FALLBACK_TYPE_COLOR = '#dfd5bf'

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

export type Verdict = keyof typeof VERDICT

export function asVerdict(rec: string | null | undefined): Verdict | null {
  const v = (rec ?? '').trim().toUpperCase()
  return v === 'INVEST' || v === 'CONSIDER' || v === 'PASS' ? v : null
}

/**
 * Verdict colour.
 *
 * Keyed on the recommendation, NOT the score. Colouring by score produced cards
 * that argued with themselves — an 8.2 rendered as a buy while its label read
 * CONSIDER. The recommendation is the call; the score is its magnitude.
 */
export function verdictColor(recommendation: string | null | undefined, score?: number | null): string {
  const v = asVerdict(recommendation)
  if (v) return VERDICT[v]
  return score == null ? UNSCORED : scoreColor(score)
}

export function verdictTextColor(recommendation: string | null | undefined): string {
  const v = asVerdict(recommendation)
  return v ? VERDICT_TEXT[v] : '#161713'
}

export type EntryState = 'ready' | 'scanning' | 'failed'

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
  state: EntryState
  /** Why a scan failed, when it did. */
  error?: string | null
  createdAt?: string
  lastRound?: string | null
  roundAmount?: number | null
  valuation?: number | null
  location?: string | null
  lat?: number | null
  lng?: number | null
  /** "address" when the pin is the building; anything else is approximate. */
  geoPrecision?: string | null
  product?: string | null
  strengths: string[]
  risks: string[]
  /** Every name this entry answers to: the scanned company's resolved name
   *  plus the name it was scanned under, which can differ ("Zomato" →
   *  "Eternal Limited"). Used to recognise a company already in the Dex. */
  aliases: string[]
}

export const STAT_KEYS = [
  { key: 'market_size_score', label: 'MKT' },
  { key: 'team_score', label: 'TEA' },
  { key: 'traction_score', label: 'TRA' },
  { key: 'competitive_moat_score', label: 'MOA' },
  { key: 'financial_health_score', label: 'FIN' },
] as const

export interface RawDeal {
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
  hq_location?: string | null
  lat?: number | null
  lng?: number | null
  geo_precision?: string | null
  product?: string | null
  strengths?: string[]
  risks?: string[]
}

export interface RawDoc {
  file_id?: string
  company_name?: string
  filename?: string
  ingested_at?: string
  status?: string | null
  error?: string | null
}

export function hasPin(e: DexEntry): e is DexEntry & { lat: number; lng: number } {
  return e.lat != null && e.lng != null && isFinite(e.lat) && isFinite(e.lng)
}

/**
 * Merge analyzed deals with still-scanning documents into one dex.
 *
 * A document whose file_id has no deal yet is either a job still running —
 * drawn as a silhouette, so the async pipeline is visible instead of silent —
 * or one that failed, which says so and can be removed. Only the former is
 * worth polling for.
 */
export function buildDex(deals: RawDeal[], documents: RawDoc[]): DexEntry[] {
  // Dex numbers follow scan order, so a company's number never changes as new
  // deals arrive or the list is re-sorted.
  const ordered = [...deals].sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
  )

  // The name each scan was started with, keyed by its job.
  const scannedAs = new Map(
    documents.filter((doc) => doc.file_id && doc.company_name).map((doc) => [doc.file_id!, doc.company_name!]),
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
    state: 'ready',
    createdAt: d.created_at,
    lastRound: d.last_round,
    roundAmount: d.round_amount,
    valuation: d.valuation,
    location: d.hq_location,
    lat: d.lat,
    lng: d.lng,
    geoPrecision: d.geo_precision,
    product: d.product,
    strengths: d.strengths ?? [],
    risks: d.risks ?? [],
    aliases: [d.company_name, ...(d.file_id && scannedAs.has(d.file_id) ? [scannedAs.get(d.file_id)!] : [])],
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

    const scanning = doc.status === 'processing'
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
      state: scanning ? 'scanning' : 'failed',
      error: scanning ? null : doc.error || 'The scan finished without a scorecard.',
      createdAt: doc.ingested_at,
      strengths: [],
      risks: [],
      aliases: [name],
    })
  }

  return entries
}

// Legal-form suffixes that say nothing about which company it is.
const LEGAL_SUFFIX = /\b(inc|incorporated|ltd|limited|llc|llp|plc|corp|corporation|co|company|gmbh|ag|sa|pbc|pvt|private)\.?$/

/** A comparable form of a company name: "Ramp, Inc." and "ramp" are the same key. */
export function companyKey(name: string): string {
  let s = name.normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim()
  // Strip trailing legal forms repeatedly: "Acme Pvt. Ltd." has two.
  for (let prev = ''; prev !== s; ) {
    prev = s
    s = s.replace(/[\s,.]+$/, '').replace(LEGAL_SUFFIX, '').trim()
  }
  return s.replace(/[^a-z0-9]/g, '')
}

const STATE_RANK: Record<EntryState, number> = { ready: 0, scanning: 1, failed: 2 }

/**
 * The Dex entry for a company named elsewhere (a firm's deal, the ticker), if
 * there is one. A scored entry wins over a running scan, which wins over a
 * failed one, so a company re-scanned after a failure reads as in the Dex.
 */
export function findEntry(entries: DexEntry[], name: string): DexEntry | null {
  const key = companyKey(name)
  if (!key) return null
  const hits = entries.filter((e) => e.aliases.some((a) => companyKey(a) === key))
  hits.sort((a, b) => STATE_RANK[a.state] - STATE_RANK[b.state])
  return hits[0] ?? null
}
