import axios from 'axios'

export const api = axios.create({ timeout: 120_000 })

const SESSION_KEY = 'vc.agentic.sessionId'

/**
 * Stable chat session id.
 *
 * Previously this was regenerated on every mount, so the history fetch always
 * asked for a brand-new id and the /chat/history endpoint could never return
 * anything. Persisting it makes conversation memory actually reachable.
 */
export function getSessionId(): string {
  try {
    const existing = localStorage.getItem(SESSION_KEY)
    if (existing) return existing
    const fresh = `session_${crypto.randomUUID()}`
    localStorage.setItem(SESSION_KEY, fresh)
    return fresh
  } catch {
    // Private browsing / storage disabled — fall back to an in-memory id.
    return `session_${Math.random().toString(36).slice(2, 11)}`
  }
}

export function resetSessionId(): string {
  try {
    localStorage.removeItem(SESSION_KEY)
  } catch {
    /* ignore */
  }
  return getSessionId()
}

export interface SSEEvent {
  type: 'step' | 'response' | 'sources' | 'deal_analysis' | 'error' | 'done'
  node?: string
  steps?: string[]
  content?: any
}

/**
 * Read an SSE body, yielding one parsed event at a time.
 *
 * A network read can split an event mid-frame, so incomplete trailing data is
 * buffered until the next chunk rather than parsed and dropped.
 */
export async function* readSSE(body: ReadableStream<Uint8Array>): AsyncGenerator<SSEEvent> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })

      const frames = buffer.split('\n\n')
      buffer = frames.pop() ?? '' // keep the incomplete tail for the next read

      for (const frame of frames) {
        const event = parseFrame(frame)
        if (event) yield event
      }
    }

    buffer += decoder.decode()
    const tail = parseFrame(buffer)
    if (tail) yield tail
  } finally {
    reader.releaseLock()
  }
}

function parseFrame(frame: string): SSEEvent | null {
  const dataLines = frame
    .split('\n')
    .filter((l) => l.startsWith('data:'))
    .map((l) => l.slice(5).trim())

  if (dataLines.length === 0) return null
  const payload = dataLines.join('\n')
  if (!payload) return null

  try {
    return JSON.parse(payload) as SSEEvent
  } catch {
    console.warn('Discarding unparseable SSE frame:', payload.slice(0, 200))
    return null
  }
}
