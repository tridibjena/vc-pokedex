import { useEffect, useState } from 'react'
import { BarChart3, FileText, Landmark, Map as MapIcon, MessageSquare } from 'lucide-react'
import { api } from '../api'

export const TABS = [
  { id: 'dex', label: 'The Dex', icon: MapIcon },
  { id: 'dealflow', label: 'Deal Flow', icon: BarChart3 },
  { id: 'chat', label: 'RAG Chat', icon: MessageSquare },
  { id: 'firms', label: 'Firm Watch', icon: Landmark },
  { id: 'memos', label: 'Memos', icon: FileText },
] as const

export type TabId = (typeof TABS)[number]['id']

interface Health {
  gemini: boolean
  openrouter: boolean
  mongodb: boolean
  chromadb: boolean
  status: string
  primary_model?: string
}

// /health no longer calls the Gemini API, but there is still no reason to poll
// a status dot every 10s — that was 8,600 requests a day per open tab.
const HEALTH_POLL_MS = 60_000

interface Props {
  active: TabId
  onChange: (tab: TabId) => void
}

export default function Header({ active, onChange }: Props) {
  return (
    <header className="app-header">
      <a
        className="brand"
        href="#dex"
        onClick={(e) => {
          e.preventDefault()
          onChange('dex')
        }}
      >
        <img className="brand-mark" src="/logo-mark.png" alt="" width={44} height={44} />
        <span className="brand-text">
          <span className="brand-name">VC Pokedex!</span>
          <span className="brand-tag">Bloomberg for startup portfolios</span>
        </span>
      </a>

      <nav className="nav" aria-label="Sections">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            className="nav-btn"
            aria-current={active === id ? 'page' : undefined}
            onClick={() => onChange(id)}
          >
            <Icon size={15} strokeWidth={2.5} aria-hidden="true" />
            <span>{label}</span>
          </button>
        ))}
      </nav>

      <ServiceStatus />
    </header>
  )
}

function ServiceStatus() {
  const [health, setHealth] = useState<Health | null>(null)
  const [offline, setOffline] = useState(false)

  useEffect(() => {
    let cancelled = false
    const check = async () => {
      try {
        const res = await api.get('/health')
        if (!cancelled) {
          setHealth(res.data)
          setOffline(false)
        }
      } catch {
        if (!cancelled) setOffline(true)
      }
    }
    check()
    const timer = setInterval(check, HEALTH_POLL_MS)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [])

  const services: Array<[string, boolean]> = [
    ['Gemini (embeddings)', !offline && !!health?.gemini],
    ['OpenRouter', !offline && !!health?.openrouter],
    ['MongoDB', !offline && !!health?.mongodb],
    ['Chroma vectors', !offline && !!health?.chromadb],
  ]
  const up = services.filter(([, ok]) => ok).length
  const label = offline ? 'Offline' : !health ? 'Checking' : health.status === 'ok' ? 'All systems go' : 'Degraded'
  // Green only when everything is up; anything else is red.
  const tone = !health && !offline ? 'idle' : !offline && health?.status === 'ok' ? 'good' : 'bad'

  return (
    <details className="status">
      <summary
        className="btn btn-cyan status-btn"
        title={`${label} — ${up}/${services.length} services up`}
        aria-label={`Backing services: ${label}, ${up} of ${services.length} up`}
      >
        <span className={`status-dot status-${tone}`} aria-hidden="true" />
      </summary>
      <div className="status-pop">
        <p className="status-pop-title">{label} · {up}/{services.length} up</p>
        {health?.primary_model && (
          <p className="status-model" title={health.primary_model}>
            {health.primary_model.replace('openrouter:', '')}
          </p>
        )}
        <ul>
          {services.map(([name, ok]) => (
            <li key={name}>
              <span>{name}</span>
              <span className={`status-pill ${ok ? 'is-up' : 'is-down'}`}>{ok ? 'up' : 'down'}</span>
            </li>
          ))}
        </ul>
      </div>
    </details>
  )
}
