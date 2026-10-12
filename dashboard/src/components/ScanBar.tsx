import { useState } from 'react'
import { Loader2, Search, Sparkles } from 'lucide-react'
import { api } from '../api'
import type { DexEntry } from '../dex'

interface Props {
  query: string
  onQueryChange: (q: string) => void
  /** An entry already in the Dex whose name matches the query exactly. */
  existing: DexEntry | null
  onOpenExisting: (entry: DexEntry) => void
  onScanned: (fileId: string, companyName: string) => void
}

/**
 * Search the Dex, or scan something new.
 *
 * Typing filters the list and the map as you go. Submitting opens the entry if
 * it is already in the Dex — re-scanning would register a duplicate — and
 * otherwise posts to /research, which returns 202 and scores in the background.
 */
export default function ScanBar({ query, onQueryChange, existing, onOpenExisting, onScanned }: Props) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    const name = query.trim()
    if (!name || busy) return

    if (existing) {
      onOpenExisting(existing)
      return
    }

    setBusy(true)
    setError(null)
    setNote(null)
    try {
      const res = await api.post('/research', { company_name: name })
      setNote(`${res.data.company_name}: ${res.data.sources?.length ?? 0} sources found, scoring now.`)
      onQueryChange('')
      onScanned(res.data.file_id, res.data.company_name)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Scan failed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="scan-bar" onSubmit={submit} role="search">
      <div className="scan-field">
        <Search size={16} strokeWidth={2.5} className="scan-icon" aria-hidden="true" />
        <input
          className="input scan-input"
          placeholder="Search the Dex or scan a startup…"
          aria-label="Search the Dex, or name a startup to scan"
          value={query}
          onChange={(e) => {
            onQueryChange(e.target.value)
            setError(null)
          }}
          disabled={busy}
        />
      </div>
      {/* Labelled explicitly: on phones the text is hidden and only the icon shows. */}
      <button
        className="btn btn-pink scan-btn"
        type="submit"
        disabled={busy || !query.trim()}
        aria-label={busy ? 'Scanning' : existing ? `Open ${existing.companyName}` : 'Scan this startup'}
      >
        {busy ? <Loader2 size={15} className="spin" /> : <Sparkles size={15} />}
        <span>{busy ? 'Scanning' : existing ? 'Open' : 'Scan'}</span>
      </button>
      {(error || note) && (
        <p className={`scan-msg ${error ? 'scan-msg-error' : 'scan-msg-ok'}`} role="status">
          {error || note}
        </p>
      )}
    </form>
  )
}
