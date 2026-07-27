import { useState } from 'react'
import { Search, Loader2 } from 'lucide-react'
import { api } from '../api'

interface Props {
  onScanned: (fileId: string, companyName: string) => void
}

/**
 * Name → dex entry. Posts to /research, which returns 202 immediately and
 * scores the company in the background; the Dex polls for completion.
 */
export default function ScanBar({ onScanned }: Props) {
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)

  const scan = async (e: React.FormEvent) => {
    e.preventDefault()
    const q = name.trim()
    if (!q || busy) return

    setBusy(true)
    setError(null)
    setNote(null)
    try {
      const res = await api.post('/research', { company_name: q })
      setNote(`Registering ${res.data.company_name} — ${res.data.sources?.length ?? 0} sources found.`)
      setName('')
      onScanned(res.data.file_id, res.data.company_name)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Scan failed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="scan-bar" onSubmit={scan}>
      <div className="scan-input-wrap">
        <Search size={15} className="scan-icon" />
        <input
          className="scan-input"
          placeholder="Enter a startup name to scan…"
          value={name}
          onChange={(e) => setName(e.target.value)}
          disabled={busy}
        />
      </div>
      <button className="scan-btn" type="submit" disabled={busy || !name.trim()}>
        {busy ? <Loader2 size={14} className="spin" /> : null}
        {busy ? 'Scanning' : 'Scan'}
      </button>
      {error && <span className="scan-msg scan-msg-error">{error}</span>}
      {note && !error && <span className="scan-msg scan-msg-ok">{note}</span>}
    </form>
  )
}
