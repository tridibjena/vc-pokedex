import { useEffect, useState } from 'react'
import { ArrowRight, Check, ExternalLink, Landmark, Loader2, Plus, RefreshCw, RotateCcw } from 'lucide-react'
import { api } from '../api'
import { companyKey, findEntry, shortSector, typeColor } from '../dex'
import type { DexEntry } from '../dex'
import { formatUsd } from '../format'
import { useDex } from '../useDex'

interface Deal {
  company: string
  round: string | null
  amount_usd: number | null
  valuation_usd: number | null
  sector: string | null
  lead: boolean | null
  date: string | null
  url: string | null
}

interface Firm {
  firm: string
  deals: Deal[]
  sources: number
}

/** Per-company state of an "Add to Dex" request, keyed by companyKey(). */
type AddState = { status: 'posting' } | { status: 'error'; message: string }

export default function FirmsPanel({ onOpenInDex }: { onOpenInDex: (entry: DexEntry) => void }) {
  const [firms, setFirms] = useState<Firm[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [meta, setMeta] = useState<{ cached: boolean; age_s: number } | null>(null)
  const dex = useDex()
  const [adding, setAdding] = useState<Record<string, AddState>>({})

  // POST /research returns 202 once the dossier is saved, so the reload that
  // follows already sees the entry as scanning; the hook polls from there.
  const addToDex = async (company: string) => {
    const key = companyKey(company)
    setAdding((prev) => ({ ...prev, [key]: { status: 'posting' } }))
    try {
      await api.post('/research', { company_name: company })
      await dex.reload()
      setAdding(({ [key]: _done, ...rest }) => rest)
    } catch (err: any) {
      const message = err.response?.data?.detail || 'Could not start the scan.'
      setAdding((prev) => ({ ...prev, [key]: { status: 'error', message } }))
    }
  }

  const load = async (force = false) => {
    force ? setRefreshing(true) : setLoading(true)
    try {
      const res = await api.get(`/research/firms${force ? '?force=true' : ''}`)
      setFirms(res.data.firms || [])
      setMeta({ cached: res.data.cached, age_s: res.data.age_s })
    } catch (err) {
      console.error('Firm watch failed:', err)
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  if (loading) {
    return (
      <div className="panel-loading panel-loading-tall">
        <span className="spinner" />
        <p className="loading-note">Sweeping ten funds…</p>
      </div>
    )
  }

  const withDeals = firms.filter((f) => f.deals.length > 0)
  const total = firms.reduce((n, f) => n + f.deals.length, 0)

  return (
    <div>
      <div className="toolbar">
        <p className="toolbar-count">
          <strong>{total}</strong> deals · <strong>{withDeals.length}</strong> of {firms.length} funds active
          {meta?.cached && <span className="toolbar-muted"> · cached {Math.round(meta.age_s / 60)}m ago</span>}
        </p>
        <button className="btn btn-sm" onClick={() => load(true)} disabled={refreshing} title="Re-sweep (costs API budget)">
          <RefreshCw size={13} className={refreshing ? 'spin' : undefined} /> Re-sweep
        </button>
      </div>

      {firms.length === 0 ? (
        <div className="empty-card">
          <Landmark size={36} strokeWidth={2} aria-hidden="true" />
          <p className="empty-title">No firm activity</p>
          <p>
            Needs <code>TAVILY_API_KEY</code>. The sweep runs once and caches for six hours.
          </p>
        </div>
      ) : (
        <div className="firm-grid">
          {firms.map((f) => (
            <FirmCard
              key={f.firm}
              firm={f}
              dexEntries={dex.entries}
              adding={adding}
              onAdd={addToDex}
              onOpenInDex={onOpenInDex}
            />
          ))}
        </div>
      )}
    </div>
  )
}

interface RowActions {
  dexEntries: DexEntry[]
  adding: Record<string, AddState>
  onAdd: (company: string) => void
  onOpenInDex: (entry: DexEntry) => void
}

function FirmCard({ firm, ...actions }: { firm: Firm } & RowActions) {
  return (
    <div className="firm-card">
      <header className="firm-head">
        <h3 className="firm-name">{firm.firm}</h3>
        <span className="firm-count">{firm.deals.length || '—'}</span>
      </header>

      {firm.deals.length === 0 ? (
        <p className="firm-quiet">no recent deals found</p>
      ) : (
        <ul className="firm-deals">
          {firm.deals.map((d, i) => (
            <DealRow key={`${d.company}-${i}`} deal={d} {...actions} />
          ))}
        </ul>
      )}
    </div>
  )
}

function DealRow({ deal: d, dexEntries, adding, onAdd, onOpenInDex }: { deal: Deal } & RowActions) {
  const entry = findEntry(dexEntries, d.company)
  const pending = adding[companyKey(d.company)]

  const amount = formatUsd(d.amount_usd)
  const valuation = formatUsd(d.valuation_usd)
  const accent = typeColor(d.sector)

  const body = (
    <>
      <span className="firm-deal-main">
        <span className="firm-deal-company">{d.company}</span>
        {d.lead && <span className="firm-lead" title="Led the round">LED</span>}
        {d.url && <ExternalLink size={11} className="firm-deal-link" />}
      </span>
      <span className="firm-deal-meta">
        {d.sector && (
          <span className="tag tag-xs" style={{ ['--tag-color' as string]: accent }}>
            {shortSector(d.sector)}
          </span>
        )}
        {d.round && <span className="firm-deal-round">{d.round}</span>}
        {amount && <span className="firm-deal-amount">{amount}</span>}
        {valuation && <span className="firm-deal-val">@ {valuation}</span>}
        {d.date && <span className="firm-deal-date">{d.date}</span>}
      </span>
    </>
  )

  return (
    <li className="firm-deal">
      {d.url ? (
        <a href={d.url} target="_blank" rel="noopener noreferrer" className="firm-deal-a">
          {body}
        </a>
      ) : (
        <span className="firm-deal-a">{body}</span>
      )}
      <DexAction company={d.company} entry={entry} pending={pending} onAdd={onAdd} onOpenInDex={onOpenInDex} />
      {pending?.status === 'error' && (
        <p className="firm-deal-error" role="alert">
          {pending.message}
        </p>
      )}
    </li>
  )
}

/**
 * What the row can do with the Dex, read off the Dex itself: add a company
 * that isn't there, show one that's scanning, open one that's scored.
 * Re-adding a scored company would only register a duplicate entry.
 */
function DexAction({
  company,
  entry,
  pending,
  onAdd,
  onOpenInDex,
}: {
  company: string
  entry: DexEntry | null
  pending: AddState | undefined
  onAdd: (company: string) => void
  onOpenInDex: (entry: DexEntry) => void
}) {
  if (pending?.status === 'posting') {
    return (
      <button type="button" className="btn btn-sm firm-dex-btn" disabled>
        <Loader2 size={13} className="spin" /> Adding
      </button>
    )
  }

  if (entry?.state === 'ready') {
    return (
      <button
        type="button"
        className="btn btn-sm btn-cyan firm-dex-btn"
        onClick={() => onOpenInDex(entry)}
        title={`Open ${entry.companyName} in the Dex`}
        aria-label={`${company} is in the Dex — open it`}
      >
        <Check size={13} /> In Dex <ArrowRight size={12} />
      </button>
    )
  }

  if (entry?.state === 'scanning') {
    return (
      <button
        type="button"
        className="btn btn-sm firm-dex-btn firm-dex-scanning"
        onClick={() => onOpenInDex(entry)}
        title="Being scanned — opens in the Dex when it lands"
        aria-label={`${company} is being scanned — open it in the Dex`}
      >
        <span className="live-dot" aria-hidden="true" /> Scanning
      </button>
    )
  }

  const retry = entry?.state === 'failed'
  return (
    <button
      type="button"
      className="btn btn-sm btn-soft firm-dex-btn"
      onClick={() => onAdd(company)}
      title={retry ? `Last scan failed: ${entry.error ?? 'unknown error'}` : `Research and score ${company}`}
      aria-label={`${retry ? 'Retry scanning' : 'Add'} ${company} ${retry ? '' : 'to the Dex'}`.trim()}
    >
      {retry ? <RotateCcw size={13} /> : <Plus size={13} />} {retry ? 'Retry' : 'Add to Dex'}
    </button>
  )
}
