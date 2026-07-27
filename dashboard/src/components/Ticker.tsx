import { useEffect, useState } from 'react'
import { Radio } from 'lucide-react'
import { api } from '../api'
import { typeColor } from '../dex'

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

export function formatUsd(n: number | null | undefined): string | null {
  if (n == null || !isFinite(n)) return null
  if (n >= 1e9) return `$${(n / 1e9).toFixed(n >= 1e10 ? 0 : 1).replace(/\.0$/, '')}B`
  if (n >= 1e6) return `$${(n / 1e6).toFixed(n >= 1e8 ? 0 : 1).replace(/\.0$/, '')}M`
  if (n >= 1e3) return `$${Math.round(n / 1e3)}K`
  return `$${n}`
}

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

  if (loading) {
    return (
      <div className="ticker">
        <div className="ticker-label">
          <Radio size={11} /> WIRE
        </div>
        <div className="ticker-viewport">
          <span className="ticker-empty">Scanning global funding wire…</span>
        </div>
      </div>
    )
  }

  if (raises.length === 0) {
    return (
      <div className="ticker">
        <div className="ticker-label">
          <Radio size={11} /> WIRE
        </div>
        <div className="ticker-viewport">
          <span className="ticker-empty">No recent raises on the wire. Set TAVILY_API_KEY to enable.</span>
        </div>
      </div>
    )
  }

  // Rendered twice so the marquee wraps seamlessly.
  const lane = [...raises, ...raises]

  return (
    <div className="ticker">
      <div className="ticker-label">
        <Radio size={11} /> WIRE
      </div>
      <div className="ticker-viewport">
        <div className="ticker-lane" style={{ animationDuration: `${Math.max(30, raises.length * 7)}s` }}>
          {lane.map((r, i) => (
            <TickerItem key={`${r.company}-${i}`} raise={r} />
          ))}
        </div>
      </div>
    </div>
  )
}

function TickerItem({ raise: r }: { raise: Raise }) {
  const amount = formatUsd(r.amount_usd)
  const valuation = formatUsd(r.valuation_usd)
  const accent = typeColor(r.sector)

  const body = (
    <>
      <i className="ticker-dot" style={{ background: accent }} />
      <span className="ticker-company">{r.company}</span>
      {r.round && <span className="ticker-round">{r.round}</span>}
      {amount && <span className="ticker-amount">{amount}</span>}
      {valuation && <span className="ticker-val">@ {valuation}</span>}
      {r.country && <span className="ticker-country">{r.country}</span>}
    </>
  )

  return r.url ? (
    <a className="ticker-item" href={r.url} target="_blank" rel="noopener noreferrer" title={r.headline || r.company}>
      {body}
    </a>
  ) : (
    <span className="ticker-item">{body}</span>
  )
}
