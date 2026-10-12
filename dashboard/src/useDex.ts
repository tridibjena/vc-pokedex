import { useCallback, useEffect, useState } from 'react'
import { api } from './api'
import { buildDex } from './dex'
import type { DexEntry } from './dex'

/** Re-read the Dex this often while any scan is still running. */
const POLL_MS = 4000

/**
 * The Dex, loaded and kept fresh: deals merged with in-flight scans, re-polled
 * while anything is still scanning and left alone once everything settles.
 * Shared by the map and by Firm Watch's "Add to Dex", so both agree on what is
 * already in it.
 */
export function useDex() {
  const [entries, setEntries] = useState<DexEntry[]>([])
  const [loading, setLoading] = useState(true)

  const reload = useCallback(async () => {
    try {
      const [dealsRes, docsRes] = await Promise.all([
        api.get('/reports/deals?limit=100'),
        api.get('/research/documents').catch(() => ({ data: { documents: [] } })),
      ])
      setEntries(buildDex(dealsRes.data.deals || [], docsRes.data.documents || []))
    } catch (err) {
      console.error('Failed to load the dex:', err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    reload()
  }, [reload])

  const scanning = entries.some((e) => e.state === 'scanning')
  useEffect(() => {
    if (!scanning) return
    const timer = setInterval(reload, POLL_MS)
    return () => clearInterval(timer)
  }, [scanning, reload])

  return { entries, setEntries, loading, reload }
}
