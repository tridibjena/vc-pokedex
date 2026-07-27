import { useState } from 'react'
import Sidebar from './components/Sidebar'
import DashboardPanel from './components/DashboardPanel'
import ChatPanel from './components/ChatPanel'
import ScorecardPanel from './components/ScorecardPanel'
import MemoPanel from './components/MemoPanel'
import FirmsPanel from './components/FirmsPanel'
import Ticker from './components/Ticker'

const TITLES: Record<string, string> = {
  dashboard: 'Pipeline Overview',
  chat: 'RAG Chat',
  deals: 'The Dex',
  firms: 'Firm Watch',
  memos: 'Investment Memos',
}

export default function App() {
  const [activeTab, setActiveTab] = useState('dashboard')

  const renderPanel = () => {
    switch (activeTab) {
      case 'chat':
        return <ChatPanel />
      case 'deals':
        return <ScorecardPanel />
      case 'firms':
        return <FirmsPanel />
      case 'memos':
        return <MemoPanel />
      default:
        return <DashboardPanel />
    }
  }

  return (
    <div className="app-layout">
      <Sidebar activeTab={activeTab} setActiveTab={setActiveTab} />
      <main className="main-content">
        <Ticker />
        <header className="content-header">
          <h1 className="page-title">{TITLES[activeTab] ?? 'VC Pokedex'}</h1>
          <span className="header-meta">VC POKEDEX 1.83</span>
        </header>
        <div className="content-body">{renderPanel()}</div>
      </main>
    </div>
  )
}
