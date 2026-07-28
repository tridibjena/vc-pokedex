import { useEffect, useMemo, useState } from 'react'
import { Layers, ArrowLeft, TrendingUp, AlertTriangle, CheckCircle, XCircle, Star, RefreshCw, Newspaper, ExternalLink, Trash2 } from 'lucide-react'
import {
  ResponsiveContainer,
  RadarChart,
  Radar,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Tooltip,
} from 'recharts'
import { api } from '../api'
import { CHART, SERIES, STATUS, scoreColor, tooltipItemStyle, tooltipLabelStyle, tooltipStyle } from '../theme'
import { buildDex, dexNumber, shortSector, typeColor, verdictColor } from '../dex'
import type { DexEntry } from '../dex'
import DexGrid from './DexGrid'
import ScanBar from './ScanBar'
import { formatUsd } from './Ticker'
import MemoDocument from './MemoDocument'

const ALL_TYPES = 'All types'

export default function ScorecardPanel() {
  const [entries, setEntries] = useState<DexEntry[]>([])
  const [selected, setSelected] = useState<DexEntry | null>(null)
  const [dealDetail, setDealDetail] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [typeFilter, setTypeFilter] = useState(ALL_TYPES)
  const [removeError, setRemoveError] = useState<string | null>(null)

  const loadDex = async () => {
    setLoading(true)
    try {
      const [dealsRes, docsRes] = await Promise.all([
        api.get('/reports/deals?limit=100'),
        api.get('/research/documents').catch(() => ({ data: { documents: [] } })),
      ])
      setEntries(buildDex(dealsRes.data.deals || [], docsRes.data.documents || []))
    } catch (err) {
      console.error('Failed to load the dex:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadDex()
  }, [])

  const removeEntry = async (entry: DexEntry) => {
    // The API keys removal on file_id and cascades to chunks, deal and reports.
    const id = entry.fileId ?? entry.dealId
    if (!id) {
      setRemoveError(`Cannot remove ${entry.companyName}: no file reference.`)
      return
    }
    setRemoveError(null)
    // Drop it locally first so the grid responds immediately; a failure re-syncs.
    setEntries((prev) => prev.filter((e) => e.key !== entry.key))
    if (selected?.key === entry.key) setSelected(null)
    try {
      await api.delete(`/research/documents/${id}`)
    } catch (err: any) {
      setRemoveError(err.response?.data?.detail || `Failed to remove ${entry.companyName}.`)
      loadDex()
    }
  }

  useEffect(() => {
    if (!selected?.dealId) {
      setDealDetail(null)
      return
    }
    let cancelled = false
    setLoadingDetail(true)
    api
      .get(`/reports/deals/${selected.dealId}`)
      .then((res) => {
        if (!cancelled) setDealDetail(res.data)
      })
      .catch((err) => console.error('Failed to load deal detail:', err))
      .finally(() => {
        if (!cancelled) setLoadingDetail(false)
      })
    return () => {
      cancelled = true
    }
  }, [selected?.dealId])

  // Group by the normalised label, so "AI" and "Artificial Intelligence" are
  // one chip rather than two near-identical ones.
  const types = useMemo(() => {
    const set = new Set(entries.filter((e) => !e.pending).map((e) => shortSector(e.sector)))
    return [ALL_TYPES, ...Array.from(set).sort()]
  }, [entries])

  const visible = useMemo(
    () =>
      typeFilter === ALL_TYPES
        ? entries
        : entries.filter((e) => shortSector(e.sector) === typeFilter),
    [entries, typeFilter],
  )

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '40vh' }}>
        <div className="loading-spinner" />
      </div>
    )
  }

  if (entries.length === 0) {
    return (
      <div className="glass-card" style={{ padding: '48px', textAlign: 'center' }}>
        <Layers size={44} strokeWidth={1} color="var(--text-muted)" />
        <h3 style={{ marginTop: '16px', fontWeight: 600 }}>The Dex is empty</h3>
        <p style={{ color: 'var(--text-muted)', marginTop: '8px', fontSize: '0.9rem' }}>
          Scan a startup by name above to register your first entry.
        </p>
      </div>
    )
  }

  if (selected && !selected.pending) {
    return (
      <DealDetail
        entry={selected}
        detail={dealDetail}
        loading={loadingDetail}
        onBack={() => setSelected(null)}
        onRemove={removeEntry}
      />
    )
  }

  const analyzed = entries.filter((e) => !e.pending).length
  const pending = entries.length - analyzed

  return (
    <div className="dex-view">
      <ScanBar onScanned={() => setTimeout(loadDex, 1500)} />

      <div className="dex-toolbar">
        <div className="dex-count">
          <strong>{analyzed}</strong> registered
          {pending > 0 && <span className="dex-count-pending"> · {pending} scanning</span>}
        </div>
        <div className="dex-toolbar-right">
          {types.map((t) => (
            <button
              key={t}
              type="button"
              className={`dex-chip${typeFilter === t ? ' active' : ''}`}
              style={t === ALL_TYPES ? undefined : { color: typeFilter === t ? typeColor(t) : undefined }}
              onClick={() => setTypeFilter(t)}
            >
              {t === ALL_TYPES ? 'All' : t}
            </button>
          ))}
          <button className="btn-ghost" onClick={loadDex} title="Refresh">
            <RefreshCw size={14} />
          </button>
        </div>
      </div>

      {removeError && <div className="dex-error">{removeError}</div>}

      <DexGrid entries={visible} onSelect={setSelected} onRemove={removeEntry} />
    </div>
  )
}

function recStyle(rec: string | null | undefined) {
  const upper = (rec ?? '').toUpperCase()
  if (upper === 'INVEST') return { color: STATUS.good, icon: <CheckCircle size={16} /> }
  if (upper === 'CONSIDER') return { color: STATUS.warning, icon: <TrendingUp size={16} /> }
  if (upper === 'PASS') return { color: STATUS.critical, icon: <XCircle size={16} /> }
  return { color: CHART.axis, icon: <Star size={16} /> }
}

function DealDetail({
  entry,
  detail,
  loading,
  onBack,
  onRemove,
}: {
  entry: DexEntry
  detail: any
  loading: boolean
  onBack: () => void
  onRemove: (e: DexEntry) => Promise<void> | void
}) {
  const accent = typeColor(entry.sector)
  const [armed, setArmed] = useState(false)

  const radarData = detail?.scorecard
    ? [
        { metric: 'Market Size', value: detail.scorecard.market_size_score || 0 },
        { metric: 'Team', value: detail.scorecard.team_score || 0 },
        { metric: 'Traction', value: detail.scorecard.traction_score || 0 },
        { metric: 'Moat', value: detail.scorecard.competitive_moat_score || 0 },
        { metric: 'Financials', value: detail.scorecard.financial_health_score || 0 },
      ]
    : []

  return (
    <div className="dex-detail">
      <div className="dex-detail-bar">
        <button className="btn-ghost dex-back" onClick={onBack}>
          <ArrowLeft size={14} /> Back to the Dex
        </button>

        {armed ? (
          <span className="dex-remove-confirm dex-remove-inline">
            <button className="dex-remove-yes" onClick={() => onRemove(entry)}>
              <Trash2 size={11} /> remove {entry.companyName}
            </button>
            <button className="dex-remove-no" onClick={() => setArmed(false)}>cancel</button>
          </span>
        ) : (
          <button className="btn-ghost dex-remove-trigger" onClick={() => setArmed(true)}>
            <Trash2 size={13} /> Remove
          </button>
        )}
      </div>

      {loading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: '80px 0' }}>
          <div className="loading-spinner" />
        </div>
      ) : !detail ? (
        <div className="glass-card" style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
          Could not load this entry.
        </div>
      ) : (
        <>
          <div className="dex-detail-head glass-card">
            <span className="dex-num dex-num-lg">#{dexNumber(entry.dex)}</span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <h1 style={{ fontSize: '1.5rem', fontWeight: 700, letterSpacing: '-0.02em' }}>
                {detail.company_name}
              </h1>
              <div style={{ display: 'flex', gap: '8px', marginTop: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
                <span className="dex-type" style={{ color: accent, borderColor: `${accent}66` }} title={detail.sector}>
                  {shortSector(detail.sector)}
                </span>
                <span className="deal-badge">{detail.stage}</span>
                {detail.metadata?.hq_location && <span className="deal-badge">{detail.metadata.hq_location}</span>}
              </div>
            </div>
            {detail.scorecard?.recommendation && (
              <div className="dex-detail-rec" style={{ color: verdictColor(detail.scorecard.recommendation, detail.scorecard.overall_score) }}>
                {recStyle(detail.scorecard.recommendation).icon}
                <span>{detail.scorecard.recommendation}</span>
                <strong>{(detail.scorecard.overall_score || 0).toFixed(1)}</strong>
              </div>
            )}
          </div>

          <div className="pair-grid">
            <div className="glass-card">
              <h3 className="card-title">Scorecard Radar</h3>
              <ResponsiveContainer width="100%" height={250}>
                <RadarChart data={radarData}>
                  <PolarGrid stroke={CHART.grid} />
                  <PolarAngleAxis dataKey="metric" tick={{ fill: CHART.axis, fontSize: 11 }} />
                  <PolarRadiusAxis domain={[0, 10]} tick={false} axisLine={false} />
                  <Radar
                    name="Score"
                    dataKey="value"
                    stroke={SERIES[0]}
                    fill={SERIES[0]}
                    fillOpacity={0.22}
                    strokeWidth={2}
                    isAnimationActive={false}
                  />
                  <Tooltip contentStyle={tooltipStyle} itemStyle={tooltipItemStyle} labelStyle={tooltipLabelStyle} />
                </RadarChart>
              </ResponsiveContainer>
            </div>

            <div className="glass-card">
              <h3 className="card-title">Dimension Scores</h3>
              {detail.scorecard && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                  {[
                    { label: 'Market Size', key: 'market_size_score' },
                    { label: 'Team Quality', key: 'team_score' },
                    { label: 'Traction', key: 'traction_score' },
                    { label: 'Competitive Moat', key: 'competitive_moat_score' },
                    { label: 'Financial Health', key: 'financial_health_score' },
                  ].map(({ label, key }) => {
                    const val = detail.scorecard[key] || 0
                    return (
                      <div key={key} style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <span style={{ width: '118px', fontSize: '0.78rem', color: 'var(--text-secondary)' }}>{label}</span>
                        <div className="dex-stat-track" style={{ flexGrow: 1 }}>
                          <div className="dex-stat-fill" style={{ width: `${val * 10}%`, background: scoreColor(val) }} />
                        </div>
                        <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: '0.83rem', minWidth: '20px', textAlign: 'right' }}>
                          {val}
                        </span>
                      </div>
                    )
                  })}
                  <div className="dex-overall">
                    <span style={{ fontWeight: 600, fontSize: '0.85rem' }}>Overall</span>
                    <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: '1.4rem', color: scoreColor(detail.scorecard.overall_score) }}>
                      {(detail.scorecard.overall_score || 0).toFixed(1)} / 10
                    </span>
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className="pair-grid">
            <div className="glass-card">
              <h3 className="card-title" style={{ color: STATUS.good, display: 'flex', alignItems: 'center', gap: '6px' }}>
                <CheckCircle size={14} /> Key Strengths
              </h3>
              <ul className="dex-list">
                {(detail.scorecard?.key_strengths || []).map((s: string, i: number) => (
                  <li key={i}>
                    <span style={{ color: STATUS.good }}>✓</span>
                    {s}
                  </li>
                ))}
              </ul>
            </div>

            <div className="glass-card">
              <h3 className="card-title" style={{ color: STATUS.critical, display: 'flex', alignItems: 'center', gap: '6px' }}>
                <AlertTriangle size={14} /> Key Risks
              </h3>
              <ul className="dex-list">
                {(detail.scorecard?.key_risks || []).map((r: string, i: number) => (
                  <li key={i}>
                    <span style={{ color: STATUS.critical }}>⚠</span>
                    {r}
                  </li>
                ))}
              </ul>
            </div>
          </div>

          <FundingPanel meta={detail.metadata || {}} company={detail.company_name} />

          <NewsPanel dealId={entry.dealId} />

          <div className="pair-grid">
            <TeamPanel data={detail.founder_profiles} company={detail.company_name} />
            <CompetitorsPanel data={detail.competitors} />
          </div>

          {detail.scorecard?.analysis_summary && (
            <div className="glass-card" style={{ marginBottom: '20px' }}>
              <h3 className="card-title">Analysis</h3>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.88rem', lineHeight: 1.7 }}>
                {detail.scorecard.analysis_summary}
              </p>
            </div>
          )}

          <MemoSection dealId={entry.dealId} company={detail.company_name} />

          {detail.ratios && (
            <div className="glass-card">
              <h3 className="card-title">Financial Ratios</h3>
              <div className="ratio-grid">
                {[
                  { label: 'Burn Multiple', key: 'burn_multiple', suffix: 'x' },
                  { label: 'Runway', key: 'runway_months', suffix: ' mo' },
                  { label: 'YoY Growth', key: 'yoy_growth', suffix: '%' },
                  { label: 'Gross Margin', key: 'gross_margin', suffix: '%' },
                  { label: 'ARR / Head', key: 'arr_per_head', suffix: '' },
                ].map(({ label, key, suffix }) => {
                  const val = detail.ratios[key]
                  return (
                    <div className="ratio-tile" key={key}>
                      <span className="ratio-label">{label}</span>
                      <span className="ratio-value">
                        {val != null ? `${typeof val === 'number' ? val.toLocaleString() : val}${suffix}` : '—'}
                      </span>
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </>
      )}
    </div>
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
    <div className="glass-card" style={{ marginBottom: '20px' }}>
      <h3 className="card-title">Funding &amp; People</h3>

      {hasFunding && (
        <div className="funding-row">
          <Fact label="Latest round" value={meta.last_round || '—'} />
          <Fact label="Amount" value={amount || '—'} accent />
          <Fact label="Valuation" value={valuation || '—'} accent />
          <Fact label="Announced" value={meta.last_round_date || '—'} />
        </div>
      )}

      {investors.length > 0 && (
        <div className="chip-row">
          <span className="chip-row-label">Investors</span>
          {investors.map((inv) => (
            <span className="deal-badge" key={inv}>{inv}</span>
          ))}
        </div>
      )}

      {founders.length > 0 && (
        <div className="chip-row">
          <span className="chip-row-label">Founders</span>
          {founders.map((f) => (
            <a
              key={f}
              className="founder-link"
              href={googleUrl(f, company)}
              target="_blank"
              rel="noopener noreferrer"
              title={`Search Google for ${f}`}
            >
              {f}
            </a>
          ))}
        </div>
      )}
    </div>
  )
}

function Fact({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="fact">
      <span className="fact-label">{label}</span>
      <span className={accent ? 'fact-value fact-value-accent' : 'fact-value'}>{value}</span>
    </div>
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
      .catch(() => {
        if (!cancelled) setState('none')
      })
    return () => {
      cancelled = true
    }
  }, [dealId])

  if (state === 'none') return null

  return (
    <div className="glass-card" style={{ marginBottom: '20px' }}>
      {state === 'loading' ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: '24px' }}>
          <div className="loading-spinner" />
        </div>
      ) : (
        <MemoDocument content={memo || ''} companyName={company} createdAt={createdAt} />
      )}
    </div>
  )
}


const SIGNAL_COLOR: Record<string, string> = {
  strong: STATUS.good,
  moderate: STATUS.warning,
  unproven: CHART.axis,
}

function TeamPanel({ data, company }: { data: any; company: string }) {
  const profiles: any[] = data?.profiles || []
  if (profiles.length === 0) return null

  return (
    <div className="glass-card">
      <h3 className="card-title">
        Founding Team{data?.team_score != null ? ` · ${data.team_score}/10` : ''}
      </h3>
      <ul className="dex-list">
        {profiles.map((p, i) => (
          <li key={i} style={{ flexDirection: 'column', alignItems: 'flex-start', gap: '4px' }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
              <a
                className="founder-link"
                href={googleUrl(p.name, company)}
                target="_blank"
                rel="noopener noreferrer"
              >
                {p.name}
              </a>
              {p.role && <span className="deal-badge">{p.role}</span>}
              {p.signal && (
                <span
                  className="signal-pill"
                  style={{ color: SIGNAL_COLOR[p.signal] ?? CHART.axis,
                           borderColor: `${SIGNAL_COLOR[p.signal] ?? CHART.axis}55` }}
                >
                  {p.signal}
                </span>
              )}
            </span>
            <span style={{ color: 'var(--text-secondary)', fontSize: '0.82rem' }}>{p.background}</span>
          </li>
        ))}
      </ul>
      {data?.team_summary && (
        <p style={{ marginTop: '10px', fontSize: '0.82rem', color: 'var(--text-muted)', lineHeight: 1.6 }}>
          {data.team_summary}
        </p>
      )}
    </div>
  )
}

function CompetitorsPanel({ data }: { data: any }) {
  const rivals: any[] = data?.competitors || []
  if (rivals.length === 0 && !data?.differentiation) return null

  return (
    <div className="glass-card">
      <h3 className="card-title">
        Competitive Landscape{data?.moat_score != null ? ` · moat ${data.moat_score}/10` : ''}
      </h3>
      <ul className="dex-list">
        {rivals.map((r, i) => (
          <li key={i}>
            <span className="signal-pill" style={{ color: CHART.axis, borderColor: 'var(--border-color)' }}>
              {r.tier}
            </span>
            <span>
              <strong style={{ color: 'var(--text-primary)' }}>{r.name}</strong>
              {r.note ? ` — ${r.note}` : ''}
            </span>
          </li>
        ))}
      </ul>
      {data?.differentiation && (
        <p style={{ marginTop: '10px', fontSize: '0.82rem', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
          <strong style={{ color: 'var(--text-primary)' }}>Differentiation:</strong> {data.differentiation}
        </p>
      )}
      {data?.moat_assessment && (
        <p style={{ marginTop: '6px', fontSize: '0.82rem', color: 'var(--text-muted)', lineHeight: 1.6 }}>
          {data.moat_assessment}
        </p>
      )}
    </div>
  )
}


interface NewsItem {
  title: string
  url: string
  published?: string | null
  snippet?: string | null
}

/**
 * Recent coverage for the company.
 *
 * Served from the dossier captured at scan time — the research agent already
 * runs a recency-biased news pass, so surfacing it here costs no extra Tavily
 * calls.
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
      .catch(() => {
        if (!cancelled) setState('none')
      })
    return () => {
      cancelled = true
    }
  }, [dealId])

  if (state === 'none') return null

  return (
    <div className="glass-card" style={{ marginBottom: '20px' }}>
      <h3 className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <Newspaper size={13} /> Recent News
      </h3>

      {state === 'loading' ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: 20 }}>
          <div className="loading-spinner" />
        </div>
      ) : (
        <ul className="news-list">
          {news.map((n, i) => (
            <li key={`${n.url}-${i}`}>
              <a href={n.url} target="_blank" rel="noopener noreferrer" className="news-item">
                <span className="news-head">
                  <span className="news-title">{n.title}</span>
                  <ExternalLink size={11} className="news-link-icon" />
                </span>
                {n.snippet && <span className="news-snippet">{n.snippet}</span>}
                <span className="news-meta">
                  <span className="news-domain">{hostOf(n.url)}</span>
                  {n.published && <span className="news-date">{shortDate(n.published)}</span>}
                </span>
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url.slice(0, 40)
  }
}

function shortDate(value: string): string {
  const d = new Date(value)
  return isNaN(d.getTime()) ? value.slice(0, 10) : d.toLocaleDateString()
}
