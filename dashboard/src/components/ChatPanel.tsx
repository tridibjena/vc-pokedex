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
    <div className="chat-tab-container">
      <div className="chat-panel glass-card">
        <div className="chat-history" ref={chatHistoryRef}>
          {messages.length === 0 && (
            <div style={{ margin: 'auto', textAlign: 'center', color: 'var(--text-muted)' }}>
              <MessageSquare size={48} style={{ marginBottom: '12px', opacity: 0.3 }} />
              <p>Ask a question about your VC documents,</p>
              <p style={{ fontSize: '0.85rem', marginTop: '4px' }}>
                e.g. "What is the ARR growth of Startup X?"
              </p>
              <p style={{ fontSize: '0.8rem', marginTop: '10px', opacity: 0.7 }}>
                Upload your own under <strong>Sources</strong> →
              </p>
            </div>
          )}

          {messages.map((msg, index) => {
            // The empty assistant bubble is pushed as soon as the response
            // headers land, so it must carry the spinner itself. Rendering a
            // separate spinner bubble alongside it drew two empty boxes.
            const awaitingFirstToken =
              streaming && index === messages.length - 1 && msg.role === 'assistant' && !msg.content

            return (
              <div key={index} className={`chat-message ${msg.role}`}>
                {awaitingFirstToken ? (
                  <div className="loading-spinner" />
                ) : (
                  <div className="md" dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.content) }} />
                )}
                {msg.deal_analysis && (
                  <div style={{ marginTop: '12px', padding: '10px', background: 'rgba(0,0,0,0.2)', borderRadius: '4px', fontSize: '0.8rem' }}>
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
            <div className="chat-message assistant">
              <div className="loading-spinner" />
            </div>
          )}
        </div>

        <form onSubmit={sendQuery} className="chat-input-area">
          <input
            type="text"
            className="chat-input"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={
              scope.fileId ? `Ask about ${scope.label}...` : 'Type your diligence query...'
            }
            disabled={streaming}
          />
          <button type="submit" className="chat-send-btn" disabled={streaming || !query.trim()}>
            <Send size={18} />
            Send
          </button>
        </form>
      </div>

      <div className="activity-feed-panel glass-card">
        <div className="rail-tabs">
          <button
            className={`rail-tab ${rail === 'sources' ? 'active' : ''}`}
            onClick={() => setRail('sources')}
          >
            <Library size={14} />
            Sources
          </button>
          <button
            className={`rail-tab ${rail === 'activity' ? 'active' : ''}`}
            onClick={() => setRail('activity')}
          >
            <Cpu size={14} />
            Activity
          </button>
          <button
            onClick={clearHistory}
            className="rail-tab-action"
            title="Clear conversation"
            aria-label="Clear conversation"
          >
            <Trash2 size={13} />
          </button>
        </div>

        {rail === 'sources' ? (
          <SourcesPanel scope={scope} setScope={setScope} />
        ) : (
          <div className="activity-list">
            {currentNode && (
              <div className="activity-item active">
                <strong>Running:</strong> {currentNode}...
                <div className="loading-spinner" style={{ width: '12px', height: '12px', borderWidth: '2px', marginTop: '8px' }} />
              </div>
            )}

            {steps.map((step, idx) => (
              <div key={idx} className="activity-item">
                {step}
              </div>
            ))}

            {!currentNode && steps.length === 0 && (
              <div style={{ margin: 'auto', color: 'var(--text-muted)', fontSize: '0.85rem', textAlign: 'center' }}>
                No active tasks.
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
