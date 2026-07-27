import { useEffect, useState } from 'react'
import { BarChart3, MessageSquare, Layers, FileText, Landmark, Activity } from 'lucide-react'
import { api } from '../api'

interface SidebarProps {
  activeTab: string
  setActiveTab: (tab: string) => void
}

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

export default function Sidebar({ activeTab, setActiveTab }: SidebarProps) {
  const [health, setHealth] = useState<Health>({
    gemini: false,
    openrouter: false,
    mongodb: false,
    chromadb: false,
    status: 'checking',
  })

  useEffect(() => {
    let cancelled = false

    const checkHealth = async () => {
      try {
        const res = await api.get('/health')
        if (!cancelled) setHealth(res.data)
      } catch {
        if (!cancelled) {
          setHealth({ gemini: false, openrouter: false, mongodb: false, chromadb: false, status: 'offline' })
        }
      }
    }

    checkHealth()
    const timer = setInterval(checkHealth, HEALTH_POLL_MS)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [])

  const navItems = [
    { id: 'dashboard', label: 'Dashboard', icon: BarChart3 },
    { id: 'chat', label: 'RAG Chat', icon: MessageSquare },
    { id: 'deals', label: 'The Dex', icon: Layers },
    { id: 'firms', label: 'Firm Watch', icon: Landmark },
    { id: 'memos', label: 'Investment Memos', icon: FileText },
  ]

  const services: Array<[string, boolean]> = [
    ['Gemini (embeddings)', health.gemini],
    ['OpenRouter', health.openrouter],
    ['MongoDB', health.mongodb],
    ['Chroma Vector', health.chromadb],
  ]

  return (
    <aside className="sidebar">
      <div className="logo-area">
        <img className="logo-icon" src="/logo-mark.png" alt="" width={30} height={30} />
        <span className="logo-text">VC Pokedex</span>
      </div>

      <nav className="nav-list">
        {navItems.map((item) => {
          const Icon = item.icon
          return (
            <div
              key={item.id}
              onClick={() => setActiveTab(item.id)}
              className={`nav-item ${activeTab === item.id ? 'active' : ''}`}
            >
              <Icon />
              <span>{item.label}</span>
            </div>
          )
        })}
      </nav>

      <div className="health-indicator">
        <div className="health-header">
          <Activity size={12} style={{ display: 'inline', marginRight: '4px', verticalAlign: 'text-bottom' }} />
          Backing Services
        </div>
        {health.primary_model && (
          <div className="health-model" title={health.primary_model}>
            {health.primary_model.replace('openrouter:', '')}
          </div>
        )}
        {services.map(([label, ok]) => (
          <div className="health-status-row" key={label}>
            <span>{label}</span>
            <div className={`status-dot ${ok ? 'online' : 'offline'}`} />
          </div>
        ))}
      </div>
    </aside>
  )
}
