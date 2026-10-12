import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { api } from '../api'
import { hasPin, shortSector, typeColor } from '../dex'
import type { DexEntry } from '../dex'
import { useDex } from '../useDex'
import DealDetail from './DealDetail'
import DexCard from './DexCard'
import DexMap from './DexMap'
import type { Inset } from './DexMap'
import ScanBar from './ScanBar'
import SpotlightCard from './SpotlightCard'

const ALL = 'All'

/** Matches the stacked (map over list) layout in style.css. */
const NARROW = '(max-width: 860px)'

/** An entry another page asked the Dex to open (Firm Watch's "In Dex"). */
export interface DexFocus {
  key: string
  fileId: string | null
}

interface Props {
  focus?: DexFocus | null
  onFocusHandled?: () => void
}

function useNarrow(): boolean {
  const [narrow, setNarrow] = useState(() => window.matchMedia(NARROW).matches)
  useEffect(() => {
    const mq = window.matchMedia(NARROW)
    const sync = () => setNarrow(mq.matches)
    mq.addEventListener('change', sync)
    return () => mq.removeEventListener('change', sync)
  }, [])
  return narrow
}

/**
 * The Dex as a map: every scanned startup pinned at its HQ, with the list in a
 * rail beside it.
 *
 * Picking a startup — its pin, its card, a search hit — flies the map in and,
 * on landing, puts it in the spotlight: the pin sized up, the rest faded, its
 * key facts on a large card. "Back to map" (or picking it again, or Esc)
 * returns to the default framing. The long-form dossier lives in the rail.
 */
export default function DexExplorer({ focus, onFocusHandled }: Props) {
  const { entries, setEntries, loading, reload: loadDex } = useDex()
  const [selectedKey, setSelectedKey] = useState<string | null>(null)
  const [hoveredKey, setHoveredKey] = useState<string | null>(null)
  const [showDetail, setShowDetail] = useState(false)
  // The entry whose spotlight card is up — set only once the flight lands.
  const [spotlitKey, setSpotlitKey] = useState<string | null>(null)
  const [typeFilter, setTypeFilter] = useState(ALL)
  const [query, setQuery] = useState('')
  const [focusNonce, setFocusNonce] = useState(0)
  const [homeNonce, setHomeNonce] = useState(0)
  // Whether the current flight is heading for a spotlight (room for the card).
  const [flyingToSpotlight, setFlyingToSpotlight] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // A scan the user just started: when it lands, spotlight it.
  const awaiting = useRef<string | null>(null)
  // The entry a flight in progress will spotlight when it lands.
  const pendingSpotlight = useRef<string | null>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const panelRef = useRef<HTMLElement>(null)
  const narrow = useNarrow()

  // Only where the rail scrolls on its own. On a phone the list flows below
  // the map, so this would scroll the whole page — map and spotlight with it —
  // out of view.
  const scrollCardIntoView = (key: string) =>
    !window.matchMedia(NARROW).matches &&
    requestAnimationFrame(() => {
      listRef.current?.querySelector(`[data-key="${CSS.escape(key)}"]`)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
    })

  // ── The three ways to look at an entry ─────────────────────────────────

  /** Back to the default view: nothing selected, the map framing everything. */
  const goHome = () => {
    pendingSpotlight.current = null
    setSpotlitKey(null)
    setSelectedKey(null)
    setShowDetail(false)
    setHomeNonce((n) => n + 1)
  }

  /** The long-form dossier in the rail. */
  const openDossier = (e: DexEntry) => {
    pendingSpotlight.current = null
    setSpotlitKey(null)
    setFlyingToSpotlight(false)
    setSelectedKey(e.key)
    setShowDetail(e.state === 'ready')
  }

  /** Fly in, then size it up. Picking the spotlit entry again backs out. */
  const spotlight = (e: DexEntry) => {
    if (!hasPin(e)) {
      // Nothing to fly to: a scored entry without a known HQ still has a
      // dossier; a scan in progress just gets its card selected.
      if (e.state === 'ready') openDossier(e)
      else setSelectedKey(e.key)
      return
    }
    if (spotlitKey === e.key) {
      goHome()
      return
    }
    pendingSpotlight.current = e.key
    setSpotlitKey(null) // the old card leaves before the flight, not after
    setShowDetail(false)
    setFlyingToSpotlight(true)
    setSelectedKey(e.key)
    setFocusNonce((n) => n + 1) // re-fly even if this pin was already selected
    scrollCardIntoView(e.key)
  }

  const arrived = (key: string) => {
    if (pendingSpotlight.current !== key) return
    pendingSpotlight.current = null
    setSpotlitKey(key)
  }

  // Esc leaves the spotlight.
  useEffect(() => {
    if (!spotlitKey) return
    const onKey = (ev: KeyboardEvent) => ev.key === 'Escape' && goHome()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [spotlitKey])

  // A scan we're waiting on has landed: spotlight it.
  useEffect(() => {
    const landed = awaiting.current && entries.find((e) => e.fileId === awaiting.current && e.state !== 'scanning')
    if (!landed) return
    awaiting.current = null
    if (landed.state === 'ready') spotlight(landed)
  }, [entries])

  // Another page asked for an entry: spotlight a scored one; select one still
  // scanning and spotlight it when it lands.
  useEffect(() => {
    if (!focus || loading) return
    const target =
      entries.find((e) => e.key === focus.key) ??
      (focus.fileId ? entries.find((e) => e.fileId === focus.fileId) : undefined)
    if (target) {
      setTypeFilter(ALL)
      setQuery('')
      if (target.state === 'ready') spotlight(target)
      else {
        setSelectedKey(target.key)
        if (target.state === 'scanning') awaiting.current = target.fileId
      }
    }
    onFocusHandled?.()
  }, [focus, loading, entries, onFocusHandled])

  // Chips: one per normalised sector, so "AI" and "Artificial Intelligence"
  // share a chip. The counts double as a legend for the badge colours.
  const types = useMemo(() => {
    const counts = new Map<string, number>()
    for (const e of entries) {
      if (e.state !== 'ready') continue
      const t = shortSector(e.sector)
      counts.set(t, (counts.get(t) ?? 0) + 1)
    }
    return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
  }, [entries])

  const q = query.trim().toLowerCase()
  const visible = useMemo(
    () =>
      entries.filter(
        (e) =>
          (typeFilter === ALL || shortSector(e.sector) === typeFilter) &&
          (!q || e.companyName.toLowerCase().includes(q)),
      ),
    [entries, typeFilter, q],
  )
  const exactMatch = useMemo(() => entries.find((e) => e.state === 'ready' && e.companyName.toLowerCase() === q) ?? null, [entries, q])

  // Newest first in the rail; numbering still follows scan order.
  const listed = useMemo(() => [...visible].sort((a, b) => b.dex - a.dex), [visible])
  const selected = entries.find((e) => e.key === selectedKey) ?? null
  const spotlit = entries.find((e) => e.key === spotlitKey && e.state === 'ready') ?? null
  const detailOpen = showDetail && selected?.state === 'ready'

  // The list and the dossier share one scroll container. Without this a
  // dossier opened from a card far down the list starts halfway through —
  // at the memo — instead of at its header; and going back lands nowhere
  // near the card you came from. Layout effect, so neither state flashes.
  useLayoutEffect(() => {
    const panel = panelRef.current
    if (!panel) return
    if (detailOpen) {
      panel.scrollTop = 0
    } else if (selectedKey && !narrow) {
      listRef.current?.querySelector(`[data-key="${CSS.escape(selectedKey)}"]`)?.scrollIntoView({ block: 'nearest' })
    }
    // Keyed on the view and the entry only — not on every poll's new entries.
  }, [detailOpen, selected?.key])

  // Re-frame the map when the filter changes, the pinned set grows or shrinks,
  // or the user goes back to the map — not on every poll.
  const pinnedCount = visible.filter(hasPin).length
  const fitKey = `${typeFilter}|${q}|${pinnedCount}|${loading}|${homeNonce}`

  // Filtering re-frames the map, which would leave a spotlight hanging over a
  // different view — so the user's own filter changes end it. (Not an effect
  // on the filter: opening a search hit clears the query itself, and that
  // must not cancel the spotlight it is starting.)
  const leaveSpotlight = () => {
    pendingSpotlight.current = null
    setSpotlitKey(null)
  }
  const filterBy = (t: string) => {
    leaveSpotlight()
    setTypeFilter(t)
  }
  const search = (text: string) => {
    leaveSpotlight()
    setQuery(text)
  }

  // Spotlight flights land the pin in the space the card leaves free: left of
  // it on a wide screen, above it on a phone.
  const flyPadding: Inset = !flyingToSpotlight
    ? { top: 150, bottom: 40, left: 40, right: 40 }
    : narrow
      ? { top: 80, bottom: Math.round(window.innerHeight * 0.36), left: 30, right: 30 }
      : { top: 110, bottom: 60, left: 60, right: 500 }

  const removeEntry = async (entry: DexEntry) => {
    // The API keys removal on file_id and cascades to chunks, deal and reports.
    const id = entry.fileId ?? entry.dealId
    if (!id) {
      setError(`Cannot remove ${entry.companyName}: no file reference.`)
      return
    }
    setError(null)
    setEntries((prev) => prev.filter((e) => e.key !== entry.key))
    if (selectedKey === entry.key) {
      pendingSpotlight.current = null
      setSpotlitKey(null)
      setSelectedKey(null)
      setShowDetail(false)
    }
    try {
      await api.delete(`/research/documents/${id}`)
    } catch (err: any) {
      setError(err.response?.data?.detail || `Failed to remove ${entry.companyName}.`)
      loadDex()
    }
  }

  const ready = entries.filter((e) => e.state === 'ready').length
  const inFlight = entries.filter((e) => e.state === 'scanning').length
  const onMap = entries.filter(hasPin).length

  return (
    <div className="explorer">
      <div className={`explorer-map${spotlit ? ' has-spotlight' : ''}`}>
        <DexMap
          entries={visible}
          selectedKey={selectedKey}
          hoveredKey={hoveredKey}
          spotlitKey={spotlit?.key ?? null}
          onSelect={(key) => {
            const e = entries.find((x) => x.key === key)
            if (e) spotlight(e)
          }}
          onHover={setHoveredKey}
          onArrive={arrived}
          fitKey={fitKey}
          focusNonce={focusNonce}
          flyPadding={flyPadding}
        />

        <div className="explorer-float" aria-hidden={spotlit ? true : undefined}>
          <ScanBar
            query={query}
            onQueryChange={search}
            existing={exactMatch}
            onOpenExisting={(e) => {
              setQuery('')
              spotlight(e)
            }}
            onScanned={(fileId) => {
              awaiting.current = fileId
              setTypeFilter(ALL)
              loadDex()
            }}
          />

          {types.length > 0 && (
            <div className="chip-rail" role="toolbar" aria-label="Filter by sector">
              <button
                type="button"
                className="chip chip-all"
                aria-pressed={typeFilter === ALL}
                onClick={() => filterBy(ALL)}
              >
                <span className="chip-label">All</span>
              </button>
              {types.map(([t, n]) => (
                <button
                  key={t}
                  type="button"
                  className="chip"
                  aria-pressed={typeFilter === t}
                  style={{ ['--chip-color' as string]: typeColor(t) }}
                  onClick={() => filterBy(typeFilter === t ? ALL : t)}
                >
                  <span className="chip-dot" aria-hidden="true" />
                  <span className="chip-label">{t}</span>
                  <span className="chip-count">{n}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        {spotlit && <SpotlightCard key={spotlit.key} entry={spotlit} onBack={goHome} />}
      </div>

      <aside className="explorer-panel" aria-label="The Dex" ref={panelRef}>
        {detailOpen && selected ? (
          <DealDetail
            key={selected.key}
            entry={selected}
            onBack={() => setShowDetail(false)}
            onLocate={spotlight}
            onRemove={removeEntry}
          />
        ) : (
          <div className="dex-list" ref={listRef}>
            <header className="panel-head">
              <div>
                <h2 className="panel-title">The Dex</h2>
                <p className="panel-sub">
                  <strong>{ready}</strong> registered · <strong>{onMap}</strong> on the map
                  {inFlight > 0 && (
                    <span className="panel-sub-live">
                      {' '}
                      · <span className="live-dot" /> {inFlight} scanning
                    </span>
                  )}
                </p>
              </div>
              <button type="button" className="btn btn-sm btn-icon" onClick={loadDex} title="Refresh" aria-label="Refresh the Dex">
                <RefreshCw size={14} />
              </button>
            </header>

            {error && <div className="alert alert-error">{error}</div>}

            {loading ? (
              <div className="panel-loading">
                <span className="spinner" />
              </div>
            ) : entries.length === 0 ? (
              <div className="empty-card">
                <p className="empty-title">The Dex is empty</p>
                <p>Type a startup's name in the search bar and hit <strong>Scan</strong>. About twenty seconds later it lands here — scored, written up and pinned on the map.</p>
              </div>
            ) : listed.length === 0 ? (
              <div className="empty-card">
                <p className="empty-title">No matches</p>
                <p>
                  Nothing in the Dex matches{q ? <> “{query.trim()}”</> : ' this filter'}.
                  {q && ' Hit Scan to research it.'}
                </p>
              </div>
            ) : (
              <div className="dex-cards">
                {listed.map((e) => (
                  <div key={e.key} data-key={e.key}>
                    <DexCard
                      entry={e}
                      selected={e.key === selectedKey}
                      hovered={e.key === hoveredKey}
                      onOpen={spotlight}
                      onDossier={openDossier}
                      onHover={setHoveredKey}
                      onRemove={removeEntry}
                    />
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </aside>
    </div>
  )
}
