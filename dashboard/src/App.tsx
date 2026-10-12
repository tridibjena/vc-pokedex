import { useCallback, useEffect, useState } from 'react'
import Header, { TABS } from './components/Header'
import type { TabId } from './components/Header'
import DexExplorer from './components/DexExplorer'
import type { DexFocus } from './components/DexExplorer'
import type { DexEntry } from './dex'
import DashboardPanel from './components/DashboardPanel'
import ChatPanel from './components/ChatPanel'
import MemoPanel from './components/MemoPanel'
import FirmsPanel from './components/FirmsPanel'
import Ticker from './components/Ticker'

const TITLES: Record<TabId, string> = {
  dex: 'The Dex',
  dealflow: 'Deal Flow',
  chat: 'RAG Chat',
  firms: 'Firm Watch',
  memos: 'Investment Memos',
}

const SUBTITLES: Partial<Record<TabId, string>> = {
  dealflow: 'Everything that has come through the Dex, by sector, stage and month.',
  chat: 'Ask across every Dex dossier and the documents you upload.',
  firms: 'Recent rounds from ten of the most active venture funds.',
  memos: 'Every investment memo the agents have written.',
}

/** The tab lives in the URL hash, so a reload or a shared link lands in place. */
function tabFromHash(): TabId {
  const id = window.location.hash.replace('#', '')
  return (TABS.find((t) => t.id === id)?.id ?? 'dex') as TabId
}

export default function App() {
  const [tab, setTab] = useState<TabId>(tabFromHash)
  // An entry to open when the Dex next renders — set from Firm Watch.
  const [dexFocus, setDexFocus] = useState<DexFocus | null>(null)
  const clearFocus = useCallback(() => setDexFocus(null), [])

  useEffect(() => {
    const sync = () => setTab(tabFromHash())
    window.addEventListener('hashchange', sync)
    return () => window.removeEventListener('hashchange', sync)
  }, [])

  const go = (next: TabId) => {
    if (window.location.hash !== `#${next}`) window.history.pushState(null, '', `#${next}`)
    setTab(next)
  }

  useEffect(() => {
    document.title = `${TITLES[tab]} — VC Pokedex`
  }, [tab])

  return (
    <div className={`app app-${tab}`}>
      <Header active={tab} onChange={go} />
      <Ticker />
      {tab === 'dex' ? (
        <main className="app-main app-main-full">
          <h1 className="sr-only">The Dex — startup map</h1>
          <DexExplorer focus={dexFocus} onFocusHandled={clearFocus} />
        </main>
      ) : (
        <main className="app-main">
          <div className="page">
            <header className="page-head">
              <h1 className="page-title">{TITLES[tab]}</h1>
              {SUBTITLES[tab] && <p className="page-sub">{SUBTITLES[tab]}</p>}
            </header>
            {tab === 'dealflow' && <DashboardPanel onOpenDex={() => go('dex')} />}
            {tab === 'chat' && <ChatPanel />}
            {tab === 'firms' && (
              <FirmsPanel
                onOpenInDex={(entry: DexEntry) => {
                  setDexFocus({ key: entry.key, fileId: entry.fileId })
                  go('dex')
                }}
              />
            )}
            {tab === 'memos' && <MemoPanel />}
          </div>
        </main>
      )}
    </div>
  )
}
