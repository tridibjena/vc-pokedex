import { useState, useEffect, useRef } from 'react'
import { Send, Cpu, MessageSquare, Trash2, Library } from 'lucide-react'
import { api, getSessionId, readSSE } from '../api'
import { renderMarkdown } from '../markdown'
import SourcesPanel, { ALL_SOURCES } from './SourcesPanel'
import type { Scope } from './SourcesPanel'

interface Message {
  role: 'user' | 'assistant'
  content: string
  timestamp?: string
  deal_analysis?: any
}

export default function ChatPanel() {
  const [query, setQuery] = useState('')
  const [messages, setMessages] = useState<Message[]>([])
  const [steps, setSteps] = useState<string[]>([])
  const [currentNode, setCurrentNode] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [sessionId] = useState(getSessionId)
  const [scope, setScope] = useState<Scope>(ALL_SOURCES)
  const [rail, setRail] = useState<'sources' | 'activity'>('sources')
  const chatHistoryRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (chatHistoryRef.current) {
      chatHistoryRef.current.scrollTop = chatHistoryRef.current.scrollHeight
    }
  }, [messages])

  // The session id is persisted, so this genuinely restores prior turns.
  useEffect(() => {
    api
      .get(`/chat/history/${sessionId}`)
      .then((res) => {
        if (res.data.messages?.length) setMessages(res.data.messages)
      })
      .catch((err) => console.error('Failed to load chat history:', err))
  }, [sessionId])

  const clearHistory = async () => {
    try {
      await api.delete(`/chat/history/${sessionId}`)
    } catch (err) {
      console.error('Failed to clear history:', err)
    }
    setMessages([])
    setSteps([])
  }

  const sendQuery = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!query.trim() || streaming) return

    const userMsg = query.trim()
    setQuery('')
    setMessages((prev) => [...prev, { role: 'user', content: userMsg }])
    setSteps([])
    setCurrentNode('retrieve_context')
    setStreaming(true)
    setRail('activity')

    try {
      const response = await fetch('/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: userMsg,
          session_id: sessionId,
          stream: true,
          file_id: scope.fileId,
        }),
      })

      if (!response.ok) throw new Error(`Server responded ${response.status}`)
      if (!response.body) throw new Error('Streaming is not supported by this browser')

      let assistantResponse = ''
      setMessages((prev) => [...prev, { role: 'assistant', content: '' }])

      const updateLast = (patch: Partial<Message>) =>
        setMessages((prev) => {
          if (prev.length === 0) return prev
          const updated = [...prev]
          updated[updated.length - 1] = { ...updated[updated.length - 1], ...patch }
          return updated
        })

      for await (const event of readSSE(response.body)) {
        switch (event.type) {
          case 'step':
            if (event.node) setCurrentNode(event.node)
            if (event.steps?.length) setSteps((prev) => [...prev, ...event.steps!])
            break
          case 'response':
            assistantResponse += event.content ?? ''
            updateLast({ role: 'assistant', content: assistantResponse })
            break
          case 'sources':
            if (Array.isArray(event.content)) {
              setSteps((prev) => [...prev, `Cited ${event.content.length} source chunk(s).`])
            }
            break
          case 'deal_analysis':
            updateLast({ deal_analysis: event.content })
            break
          case 'error':
            assistantResponse += `\n\n[System Error: ${event.content}]`
            updateLast({ content: assistantResponse })
            break
          case 'done':
            break
        }
      }
    } catch (err: any) {
      console.error('Chat error:', err)
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: `Diligence query failed: ${err.message}` },
      ])
    } finally {
      setStreaming(false)
      setCurrentNode('')
    }
  }

  return (
    <div className="chat-layout">
      <section className="comic-card chat-panel">
        <div className="chat-history" ref={chatHistoryRef} aria-live="polite">
          {messages.length === 0 && (
            <div className="chat-empty">
              <MessageSquare size={40} strokeWidth={2} aria-hidden="true" />
              <p className="empty-title">Ask the Dex anything</p>
              <p>e.g. “What did Ramp raise, and who led it?”</p>
              <p className="chat-empty-hint">Add your own term sheets and decks under <strong>Sources</strong> →</p>
            </div>
          )}

          {messages.map((msg, index) => {
            // The empty assistant bubble is pushed as soon as the response
            // headers land, so it must carry the spinner itself. Rendering a
            // separate spinner bubble alongside it drew two empty boxes.
            const awaitingFirstToken =
              streaming && index === messages.length - 1 && msg.role === 'assistant' && !msg.content

            return (
              <div key={index} className={`bubble bubble-${msg.role}`}>
                <span className="bubble-who">{msg.role === 'user' ? 'You' : 'Analyst'}</span>
                {awaitingFirstToken ? (
                  <span className="spinner spinner-sm" />
                ) : (
                  <div className="md" dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.content) }} />
                )}
                {msg.deal_analysis && (
                  <div className="bubble-note">
                    <strong>Scorecard:</strong> {msg.deal_analysis.scorecard?.recommendation} (
                    {msg.deal_analysis.scorecard?.overall_score}/10)
                  </div>
                )}
              </div>
            )
          })}

          {/* Between clicking Send and the response arriving there is no
              assistant bubble yet, so this covers that window only. */}
          {streaming && messages[messages.length - 1]?.role === 'user' && (
            <div className="bubble bubble-assistant">
              <span className="bubble-who">Analyst</span>
              <span className="spinner spinner-sm" />
            </div>
          )}
        </div>

        <form onSubmit={sendQuery} className="chat-input-row">
          <input
            type="text"
            className="input chat-input"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={scope.fileId ? `Ask about ${scope.label}…` : 'Type your diligence question…'}
            aria-label="Your question"
            disabled={streaming}
          />
          <button type="submit" className="btn btn-pink" disabled={streaming || !query.trim()}>
            <Send size={15} />
            Send
          </button>
        </form>
      </section>

      <aside className="comic-card chat-rail">
        <div className="rail-tabs" role="tablist">
          <button
            role="tab"
            aria-selected={rail === 'sources'}
            className="rail-tab"
            onClick={() => setRail('sources')}
          >
            <Library size={14} />
            Sources
          </button>
          <button
            role="tab"
            aria-selected={rail === 'activity'}
            className="rail-tab"
            onClick={() => setRail('activity')}
          >
            <Cpu size={14} />
            Activity
          </button>
          <button onClick={clearHistory} className="btn btn-sm btn-icon rail-clear" title="Clear conversation" aria-label="Clear conversation">
            <Trash2 size={13} />
          </button>
        </div>

        {rail === 'sources' ? (
          <SourcesPanel scope={scope} setScope={setScope} />
        ) : (
          <ol className="activity-list">
            {currentNode && (
              <li className="activity-item is-active">
                <span className="spinner spinner-sm" />
                <span><strong>Running:</strong> {currentNode}…</span>
              </li>
            )}

            {steps.map((step, idx) => (
              <li key={idx} className="activity-item">
                {step}
              </li>
            ))}

            {!currentNode && steps.length === 0 && <li className="activity-empty">No active tasks.</li>}
          </ol>
        )}
      </aside>
    </div>
  )
}
