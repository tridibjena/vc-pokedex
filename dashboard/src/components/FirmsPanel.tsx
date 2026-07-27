import { useEffect, useState } from 'react'
import { RefreshCw, Landmark, ExternalLink } from 'lucide-react'
import { api } from '../api'
import { shortSector, typeColor } from '../dex'
import { formatUsd } from './Ticker'

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

export default function FirmsPanel() {
  const [firms, setFirms] = useState<Firm[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [meta, setMeta] = useState<{ cached: boolean; age_s: number } | null>(null)

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
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 14, paddingTop: '18vh' }}>
        <div className="loading-spinner" />
        <p style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
          Sweeping ten funds…
        </p>
      </div>
    )
  }

  const withDeals = firms.filter((f) => f.deals.length > 0)
  const total = firms.reduce((n, f) => n + f.deals.length, 0)

  return (
    <div>
      <div className="dex-toolbar">
        <div className="dex-count">
          <strong>{total}</strong> deals · <strong>{withDeals.length}</strong> of {firms.length} funds active
          {meta?.cached && <span style={{ marginLeft: 8, opacity: 0.7 }}>· cached {Math.round(meta.age_s / 60)}m</span>}
        </div>
        <button className="btn-ghost" onClick={() => load(true)} disabled={refreshing} title="Re-sweep (costs API budget)">
          <RefreshCw size={13} className={refreshing ? 'spin' : undefined} />
        </button>
      </div>

      {firms.length === 0 ? (
        <div className="glass-card" style={{ padding: 44, textAlign: 'center' }}>
          <Landmark size={40} strokeWidth={1} color="var(--text-muted)" />
          <h3 style={{ marginTop: 14, fontWeight: 600 }}>No firm activity</h3>
          <p style={{ color: 'var(--text-muted)', marginTop: 6, fontSize: '0.88rem' }}>
            Needs <code>TAVILY_API_KEY</code>. The sweep runs once and caches for six hours.
          </p>
        </div>
      ) : (
        <div className="firm-grid">
          {firms.map((f) => (
            <FirmCard key={f.firm} firm={f} />
          ))}
        </div>
      )}
    </div>
  )
}

function FirmCard({ firm }: { firm: Firm }) {
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
            <DealRow key={`${d.company}-${i}`} deal={d} />
          ))}
        </ul>
      )}
    </div>
  )
}

function DealRow({ deal: d }: { deal: Deal }) {
  const amount = formatUsd(d.amount_usd)
  const valuation = formatUsd(d.valuation_usd)
  const accent = typeColor(d.sector)

  const body = (
    <>
      <span className="firm-deal-main">
        <span className="firm-deal-company">{d.company}</span>
        {d.lead && <span className="firm-lead" title="Led the round">LED</span>}
        {d.url && <ExternalLink size={10} className="firm-deal-link" />}
      </span>
      <span className="firm-deal-meta">
        {d.sector && (
          <span className="firm-deal-sector" style={{ color: accent }}>
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
    </li>
  )
}
