import { useEffect, useState } from 'react'
import { Radio } from 'lucide-react'
import { api } from '../api'
import { shortSector } from '../dex'
import { formatUsd } from '../format'

interface Raise {
  company: string
  amount_usd: number | null
  round: string | null
  valuation_usd: number | null
  sector: string | null
  country: string | null
  url: string | null
  headline: string | null
}

const REFRESH_MS = 15 * 60 * 1000

/** The funding wire — a strip of tape across the top of every page. */
export default function Ticker() {
  const [raises, setRaises] = useState<Raise[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const res = await api.get('/research/ticker')
        if (!cancelled) setRaises(res.data.raises || [])
      } catch (err) {
        console.error('Ticker failed:', err)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    const t = setInterval(load, REFRESH_MS)
    return () => {
      cancelled = true
      clearInterval(t)
    }
  }, [])

  const label = (
    <div className="ticker-label">
      <Radio size={12} strokeWidth={2.5} /> Wire
    </div>
  )

  if (loading || raises.length === 0) {
    return (
      <div className="ticker">
        {label}
        <div className="ticker-viewport">
          <span className="ticker-empty">
            {loading ? 'Tuning in to the global funding wire…' : 'No recent raises on the wire. Set TAVILY_API_KEY to enable.'}
          </span>
        </div>
      </div>
    )
  }

  // Rendered twice so the marquee wraps seamlessly.
  const lane = [...raises, ...raises]

  return (
    <div className="ticker">
      {label}
      <div className="ticker-viewport">
        <div className="ticker-lane" style={{ animationDuration: `${Math.max(36, raises.length * 8)}s` }}>
          {lane.map((r, i) => (
            <TickerItem key={`${r.company}-${i}`} raise={r} hidden={i >= raises.length} />
          ))}
        </div>
      </div>
    </div>
  )
}

function TickerItem({ raise: r, hidden }: { raise: Raise; hidden: boolean }) {
  const amount = formatUsd(r.amount_usd)
  const valuation = formatUsd(r.valuation_usd)

  const body = (
    <>
      <span className="ticker-company">{r.company}</span>
      {r.round && <span className="ticker-round">{r.round}</span>}
      {amount && <span className="ticker-amount">{amount}</span>}
      {valuation && <span className="ticker-val">@ {valuation}</span>}
      {r.sector && <span className="ticker-sector">{shortSector(r.sector)}</span>}
      {r.country && <span className="ticker-country">{r.country}</span>}
      <span className="ticker-star" aria-hidden="true">✦</span>
    </>
  )

  // The second copy exists only for the seamless loop; keep it out of the
  // accessibility tree and the tab order.
  const a11y = hidden ? { 'aria-hidden': true, tabIndex: -1 } : {}

  return r.url ? (
    <a className="ticker-item" href={r.url} target="_blank" rel="noopener noreferrer" title={r.headline || r.company} {...a11y}>
      {body}
    </a>
  ) : (
    <span className="ticker-item" {...a11y}>{body}</span>
  )
}
