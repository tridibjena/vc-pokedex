import { useEffect, useState } from 'react'
import { ArrowLeft, ExternalLink, MapPin, Newspaper, X } from 'lucide-react'
import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
} from 'recharts'
import { api } from '../api'
import { dexNumber, hasPin, shortSector, typeColor } from '../dex'
import type { DexEntry } from '../dex'
import { formatUsd, hostOf, shortDate } from '../format'
import { CHART, INK, POP, scoreColor, tooltipItemStyle, tooltipLabelStyle, tooltipStyle } from '../theme'
import { EvolutionChain, RemoveButton, StageTag, VerdictBadge } from './DexCard'
import MemoDocument from './MemoDocument'

const DIMENSIONS = [
  { label: 'Market size', short: 'Market', key: 'market_size_score' },
  { label: 'Team', short: 'Team', key: 'team_score' },
  { label: 'Traction', short: 'Traction', key: 'traction_score' },
  { label: 'Moat', short: 'Moat', key: 'competitive_moat_score' },
  { label: 'Financials', short: 'Financials', key: 'financial_health_score' },
] as const

interface Props {
  entry: DexEntry
  onBack: () => void
  onLocate: (entry: DexEntry) => void
  onRemove: (entry: DexEntry) => Promise<void> | void
}

/** The full dossier for one entry, rendered in the side panel. */
export default function DealDetail({ entry, onBack, onLocate, onRemove }: Props) {
  return (
    <div className="dossier">
      <div className="dossier-bar">
        <button type="button" className="btn btn-sm" onClick={onBack}>
          <ArrowLeft size={14} /> The Dex
        </button>
        <div className="dossier-bar-right">
          {hasPin(entry) && (
            <button type="button" className="btn btn-sm" onClick={() => onLocate(entry)}>
              <MapPin size={13} /> Map
            </button>
          )}
          <RemoveButton entry={entry} onRemove={onRemove} />
          <button type="button" className="btn btn-sm btn-icon" onClick={onBack} aria-label={`Close details for ${entry.companyName}`}>
            <X size={14} />
          </button>
        </div>
      </div>

      <header className="dossier-head">
        <span className="dex-num">No.{dexNumber(entry.dex)}</span>
        <h2 className="dossier-name">{entry.companyName}</h2>
        <div className="dossier-tags">
          <span className="tag" style={{ ['--tag-color' as string]: typeColor(entry.sector) }} title={entry.sector}>
            {shortSector(entry.sector)}
          </span>
          <StageTag stage={entry.stage} />
          {entry.location && (
            <span className="tag tag-plain">
              <MapPin size={11} strokeWidth={2.5} /> {entry.location}
            </span>
          )}
        </div>
        {entry.product && <p className="dossier-tagline">{entry.product}</p>}
        <div className="dossier-verdict">
          <VerdictBadge recommendation={entry.recommendation} score={entry.overallScore} large />
          <EvolutionChain stage={entry.stage} />
        </div>
      </header>

      <DossierBody entry={entry} />
    </div>
  )
}

/**
 * The long-form dossier sections, loaded for one entry. Shared by the rail
 * and by the spotlight card, which already shows the scores and the bull and
 * bear case up top and so asks for `withSummary={false}`.
 */
export function DossierBody({ entry, withSummary = true }: { entry: DexEntry; withSummary?: boolean }) {
  const [detail, setDetail] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!entry.dealId) return
    let cancelled = false
    setLoading(true)
    api
      .get(`/reports/deals/${entry.dealId}`)
      .then((res) => !cancelled && setDetail(res.data))
      .catch((err) => console.error('Failed to load deal detail:', err))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [entry.dealId])

  if (loading) {
    return (
      <div className="panel-loading">
        <span className="spinner" />
      </div>
    )
  }
  if (!detail) return <div className="section-card">Could not load this entry.</div>

  const sc = detail.scorecard
  const meta = detail.metadata || {}

  return (
    <>
      {withSummary && sc && (
        <section className="section-card">
          <h3 className="section-title">Scorecard</h3>
          <div className="score-radar">
            <ResponsiveContainer width="100%" height={220}>
              <RadarChart data={DIMENSIONS.map((d) => ({ metric: d.short, value: sc[d.key] || 0 }))} outerRadius="72%">
                <PolarGrid stroke={CHART.grid} />
                <PolarAngleAxis dataKey="metric" tick={{ fill: INK, fontSize: 11, fontWeight: 700 }} />
                <PolarRadiusAxis domain={[0, 10]} tick={false} axisLine={false} />
                <Radar
                  name="Score"
                  dataKey="value"
                  stroke={INK}
                  fill={POP}
                  fillOpacity={0.75}
                  strokeWidth={2}
                  dot={{ r: 4, fill: INK, strokeWidth: 0 }}
                  isAnimationActive={false}
                />
                <Tooltip contentStyle={tooltipStyle} itemStyle={tooltipItemStyle} labelStyle={tooltipLabelStyle} />
              </RadarChart>
            </ResponsiveContainer>
          </div>
          <ul className="score-bars">
            {DIMENSIONS.map(({ label, key }) => {
              const val = sc[key] || 0
              return (
                <li key={key}>
                  <span className="score-bar-label">{label}</span>
                  <span className="score-bar-track">
                    <span className="score-bar-fill" style={{ width: `${val * 10}%`, background: scoreColor(val) }} />
                  </span>
                  <span className="score-bar-value">{val}</span>
                </li>
              )
            })}
          </ul>
        </section>
      )}

      {withSummary && sc && (sc.key_strengths?.length > 0 || sc.key_risks?.length > 0) && (
        <section className="section-card case-grid">
          <div>
            <h3 className="section-title"><span className="dex-case-label dex-case-bull">Bull case</span></h3>
            <ul className="bullet-list">
              {(sc.key_strengths || []).map((s: string, i: number) => <li key={i}>{s}</li>)}
            </ul>
          </div>
          <div>
            <h3 className="section-title"><span className="dex-case-label dex-case-bear">Pass if</span></h3>
            <ul className="bullet-list">
              {(sc.key_risks || []).map((r: string, i: number) => <li key={i}>{r}</li>)}
            </ul>
          </div>
        </section>
      )}

      {sc?.analysis_summary && (
        <section className="section-card">
          <h3 className="section-title">The take</h3>
          <p className="prose">{sc.analysis_summary}</p>
        </section>
      )}

      <FundingPanel meta={meta} company={detail.company_name} />
      <NewsPanel dealId={entry.dealId} />
      <TeamPanel data={detail.founder_profiles} company={detail.company_name} />
      <CompetitorsPanel data={detail.competitors} />
      <RatiosPanel ratios={detail.ratios} />
      <MemoSection dealId={entry.dealId} company={detail.company_name} />
    </>
  )
}

function googleUrl(person: string, company: string) {
  return `https://www.google.com/search?q=${encodeURIComponent(`${person} ${company}`)}`
}

function FundingPanel({ meta, company }: { meta: any; company: string }) {
  const founders: string[] = Array.isArray(meta.founders) ? meta.founders : []
  const leads: string[] = Array.isArray(meta.lead_investors) ? meta.lead_investors : []
  const notable: string[] = Array.isArray(meta.notable_investors) ? meta.notable_investors : []
  const investors = Array.from(new Set([...leads, ...notable]))

  const amount = formatUsd(meta.last_round_amount)
  const valuation = formatUsd(meta.valuation)
  const hasFunding = Boolean(meta.last_round || amount || valuation || investors.length)

  if (!hasFunding && founders.length === 0) return null

  return (
    <section className="section-card">
      <h3 className="section-title">Funding &amp; people</h3>

      {hasFunding && (
        <div className="fact-grid">
          <Fact label="Latest round" value={meta.last_round || '—'} />
          <Fact label="Amount" value={amount || '—'} />
          <Fact label="Valuation" value={valuation || '—'} />
          <Fact label="Announced" value={meta.last_round_date || '—'} />
        </div>
      )}

      {investors.length > 0 && (
        <div className="chip-row">
          <span className="chip-row-label">Investors</span>
          {investors.map((inv) => (
            <span className="tag tag-plain" key={inv}>{inv}</span>
          ))}
        </div>
      )}

      {founders.length > 0 && (
        <div className="chip-row">
          <span className="chip-row-label">Founders</span>
          {founders.map((f) => (
            <a key={f} className="ink-link" href={googleUrl(f, company)} target="_blank" rel="noopener noreferrer" title={`Search Google for ${f}`}>
              {f}
            </a>
          ))}
        </div>
      )}
    </section>
  )
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="fact">
      <span className="fact-label">{label}</span>
      <span className="fact-value">{value}</span>
    </div>
  )
}

function RatiosPanel({ ratios }: { ratios: any }) {
  if (!ratios) return null
  const tiles = [
    { label: 'Burn multiple', key: 'burn_multiple', suffix: 'x' },
    { label: 'Runway', key: 'runway_months', suffix: ' mo' },
    { label: 'YoY growth', key: 'yoy_growth', suffix: '%' },
    { label: 'Gross margin', key: 'gross_margin', suffix: '%' },
    { label: 'ARR / head', key: 'arr_per_head', suffix: '' },
  ]
  return (
    <section className="section-card">
      <h3 className="section-title">Financial ratios</h3>
      <div className="fact-grid">
        {tiles.map(({ label, key, suffix }) => {
          const val = ratios[key]
          return (
            <Fact
              key={key}
              label={label}
              value={val != null ? `${typeof val === 'number' ? val.toLocaleString() : val}${suffix}` : '—'}
            />
          )
        })}
      </div>
      {ratios.commentary && <p className="prose prose-muted">{ratios.commentary}</p>}
    </section>
  )
}

function MemoSection({ dealId, company }: { dealId: string | null; company?: string }) {
  const [memo, setMemo] = useState<string | null>(null)
  const [createdAt, setCreatedAt] = useState<string | undefined>()
  const [state, setState] = useState<'loading' | 'ready' | 'none'>('loading')

  useEffect(() => {
    if (!dealId) {
      setState('none')
      return
    }
    let cancelled = false
    setState('loading')
    api
      .get(`/reports/deals/${dealId}/memo`)
      .then((res) => {
        if (cancelled) return
        setMemo(res.data.content || '')
        setCreatedAt(res.data.created_at)
        setState(res.data.content ? 'ready' : 'none')
      })
      .catch(() => !cancelled && setState('none'))
    return () => {
      cancelled = true
    }
  }, [dealId])

  if (state === 'none') return null

  return (
    <section className="section-card section-card-memo">
      {state === 'loading' ? (
        <div className="panel-loading">
          <span className="spinner" />
        </div>
      ) : (
        <MemoDocument content={memo || ''} companyName={company} createdAt={createdAt} />
      )}
    </section>
  )
}

const SIGNAL_CLASS: Record<string, string> = {
  strong: 'signal-strong',
  moderate: 'signal-moderate',
  unproven: 'signal-unproven',
}

function TeamPanel({ data, company }: { data: any; company: string }) {
  const profiles: any[] = data?.profiles || []
  if (profiles.length === 0) return null

  return (
    <section className="section-card">
      <h3 className="section-title">
        Founding team{data?.team_score != null ? <span className="section-score">{data.team_score}/10</span> : null}
      </h3>
      <ul className="people-list">
        {profiles.map((p, i) => (
          <li key={i}>
            <span className="people-head">
              <a className="ink-link" href={googleUrl(p.name, company)} target="_blank" rel="noopener noreferrer">
                {p.name}
              </a>
              {p.role && <span className="tag tag-plain">{p.role}</span>}
              {p.signal && <span className={`signal ${SIGNAL_CLASS[p.signal] ?? ''}`}>{p.signal}</span>}
            </span>
            <span className="people-note">{p.background}</span>
          </li>
        ))}
      </ul>
      {data?.team_summary && <p className="prose prose-muted">{data.team_summary}</p>}
    </section>
  )
}

function CompetitorsPanel({ data }: { data: any }) {
  const rivals: any[] = data?.competitors || []
  if (rivals.length === 0 && !data?.differentiation) return null

  return (
    <section className="section-card">
      <h3 className="section-title">
        Competition{data?.moat_score != null ? <span className="section-score">moat {data.moat_score}/10</span> : null}
      </h3>
      <ul className="people-list">
        {rivals.map((r, i) => (
          <li key={i}>
            <span className="people-head">
              <strong>{r.name}</strong>
              {r.tier && <span className="tag tag-plain">{r.tier}</span>}
            </span>
            {r.note && <span className="people-note">{r.note}</span>}
          </li>
        ))}
      </ul>
      {data?.differentiation && (
        <p className="prose">
          <strong>Edge:</strong> {data.differentiation}
        </p>
      )}
      {data?.moat_assessment && <p className="prose prose-muted">{data.moat_assessment}</p>}
    </section>
  )
}

interface NewsItem {
  title: string
  url: string
  published?: string | null
  snippet?: string | null
}

/**
 * Recent coverage, served from the dossier captured at scan time — the
 * research agent already ran a recency-biased news pass, so this costs no
 * extra Tavily calls.
 */
function NewsPanel({ dealId }: { dealId: string | null }) {
  const [news, setNews] = useState<NewsItem[]>([])
  const [state, setState] = useState<'loading' | 'ready' | 'none'>('loading')

  useEffect(() => {
    if (!dealId) {
      setState('none')
      return
    }
    let cancelled = false
    setState('loading')
    api
      .get(`/reports/deals/${dealId}/news`)
      .then((res) => {
        if (cancelled) return
        const items: NewsItem[] = res.data.news || []
        setNews(items)
        setState(items.length ? 'ready' : 'none')
      })
      .catch(() => !cancelled && setState('none'))
    return () => {
      cancelled = true
    }
  }, [dealId])

  if (state === 'none') return null

  return (
    <section className="section-card">
      <h3 className="section-title">
        <Newspaper size={14} /> In the news
      </h3>
      {state === 'loading' ? (
        <div className="panel-loading">
          <span className="spinner" />
        </div>
      ) : (
        <ul className="news-list">
          {news.map((n, i) => (
            <li key={`${n.url}-${i}`}>
              <a href={n.url} target="_blank" rel="noopener noreferrer" className="news-item">
                <span className="news-title">
                  {n.title} <ExternalLink size={11} className="news-link-icon" />
                </span>
                {n.snippet && <span className="news-snippet">{n.snippet}</span>}
                <span className="news-meta">
                  <span>{hostOf(n.url)}</span>
                  {n.published && <span>{shortDate(n.published)}</span>}
                </span>
              </a>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
