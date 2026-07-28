import { useCallback, useEffect, useRef, useState } from 'react'
import { Upload, FileText, Trash2, Layers, AlertCircle, Check } from 'lucide-react'
import { api } from '../api'

export interface Scope {
  fileId: string | null
  label: string
}

export const ALL_SOURCES: Scope = { fileId: null, label: 'All sources' }

interface LibraryDoc {
  file_id: string
  filename: string
  status: string
  chunks?: number
  chars?: number
  error?: string | null
}

interface DexDoc {
  file_id?: string
  company_name?: string
  filename?: string
}

interface Props {
  scope: Scope
  setScope: (scope: Scope) => void
}

/** Poll while anything is still indexing; stop once everything settles. */
const POLL_MS = 3000

export default function SourcesPanel({ scope, setScope }: Props) {
  const [docs, setDocs] = useState<LibraryDoc[]>([])
  const [dex, setDex] = useState<DexDoc[]>([])
  const [uploading, setUploading] = useState<string[]>([])
  const [error, setError] = useState('')
  const [accepted, setAccepted] = useState<string[]>([])
  const [maxMb, setMaxMb] = useState(50)
  const inputRef = useRef<HTMLInputElement>(null)

  const load = useCallback(async () => {
    try {
      const [lib, research] = await Promise.all([
        api.get('/library/documents'),
        api.get('/research/documents'),
      ])
      setDocs(lib.data.documents ?? [])
      setAccepted(lib.data.accepted ?? [])
      setMaxMb(lib.data.max_mb ?? 50)
      setDex(research.data.documents ?? [])
    } catch (err) {
      console.error('Failed to load sources:', err)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  // Indexing is a background task, so the list has to be re-read to learn it
  // finished — but only while something is actually in flight.
  const pending = docs.some((d) => d.status === 'processing') || uploading.length > 0
  useEffect(() => {
    if (!pending) return
    const timer = setInterval(load, POLL_MS)
    return () => clearInterval(timer)
  }, [pending, load])

  const upload = async (files: FileList | null) => {
    if (!files?.length) return
    setError('')
    const names = Array.from(files).map((f) => f.name)
    setUploading((prev) => [...prev, ...names])

    // Sequential, not Promise.all: each upload kicks off a background embed job
    // and the free embedding tier is metered per item, so firing ten at once
    // just makes them all queue behind the rate limiter anyway.
    for (const file of Array.from(files)) {
      try {
        const form = new FormData()
        form.append('file', file)
        await api.post('/library/documents', form)
      } catch (err: any) {
        const detail = err?.response?.data?.detail ?? err.message
        setError(`${file.name}: ${detail}`)
      } finally {
        setUploading((prev) => prev.filter((n) => n !== file.name))
      }
    }

    await load()
    if (inputRef.current) inputRef.current.value = '' // allow re-picking the same file
  }

  const remove = async (doc: LibraryDoc) => {
    try {
      await api.delete(`/library/documents/${doc.file_id}`)
      if (scope.fileId === doc.file_id) setScope(ALL_SOURCES)
      await load()
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? err.message)
    }
  }

  return (
    <div className="sources-panel">
      <div className="sources-actions">
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={accepted.join(',')}
          style={{ display: 'none' }}
          onChange={(e) => upload(e.target.files)}
        />
        <button className="sources-upload-btn" onClick={() => inputRef.current?.click()}>
          <Upload size={14} />
          Add VC documents
        </button>
        {/* The server accepts six extensions; listing all of them wraps to two
            lines and reads like noise. Name the ones people actually have. */}
        <p className="sources-hint">PDF · TXT · MD — up to {maxMb} MB each</p>
      </div>

      {error && (
        <div className="sources-error">
          <AlertCircle size={13} />
          <span>{error}</span>
        </div>
      )}

      <label className="sources-label">Chat scope</label>
      <select
        className="sources-select"
        value={scope.fileId ?? ''}
        onChange={(e) => {
          const id = e.target.value
          if (!id) return setScope(ALL_SOURCES)
          const doc = docs.find((d) => d.file_id === id)
          const entry = dex.find((d) => d.file_id === id)
          setScope({
            fileId: id,
            label: doc?.filename ?? entry?.company_name ?? entry?.filename ?? 'Document',
          })
        }}
      >
        <option value="">All sources</option>
        {docs.length > 0 && (
          <optgroup label="Library">
            {docs.map((d) => (
              <option key={d.file_id} value={d.file_id} disabled={d.status !== 'complete'}>
                {d.filename}
                {d.status !== 'complete' ? ` (${d.status})` : ''}
              </option>
            ))}
          </optgroup>
        )}
        {dex.length > 0 && (
          <optgroup label="Dex entries">
            {dex
              .filter((d) => d.file_id)
              .map((d) => (
                <option key={d.file_id} value={d.file_id}>
                  {d.company_name || d.filename}
                </option>
              ))}
          </optgroup>
        )}
      </select>

      <div className="sources-list">
        {uploading.map((name) => (
          <div className="source-item" key={`up-${name}`}>
            <span className="loading-spinner" style={{ width: 12, height: 12, borderWidth: 2 }} />
            <span className="source-name">{name}</span>
            <span className="source-meta">uploading</span>
          </div>
        ))}

        {docs.map((d) => (
          <div className="source-item" key={d.file_id}>
            <FileText size={13} className="source-icon" />
            <span className="source-name" title={d.error || d.filename}>
              {d.filename}
            </span>
            <SourceStatus doc={d} />
            <button
              className="source-remove"
              title={`Remove ${d.filename}`}
              aria-label={`Remove ${d.filename}`}
              onClick={() => remove(d)}
            >
              <Trash2 size={12} />
            </button>
          </div>
        ))}

        {dex.length > 0 && (
          <div className="source-item source-item-static">
            <Layers size={13} className="source-icon" />
            <span className="source-name">{dex.length} Dex {dex.length === 1 ? 'entry' : 'entries'}</span>
            <span className="source-meta">researched</span>
          </div>
        )}

        {docs.length === 0 && uploading.length === 0 && (
          <p className="sources-empty">
            No uploaded documents yet. Chat still searches every Dex entry.
          </p>
        )}
      </div>
    </div>
  )
}

function SourceStatus({ doc }: { doc: LibraryDoc }) {
  if (doc.status === 'processing') {
    return <span className="source-meta">indexing…</span>
  }
  if (doc.status === 'failed') {
    return (
      <span className="source-meta source-meta-failed" title={doc.error ?? 'Indexing failed'}>
        failed
      </span>
    )
  }
  return (
    <span className="source-meta source-meta-ok">
      <Check size={11} /> {doc.chunks ?? 0}
    </span>
  )
}
