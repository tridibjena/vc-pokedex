import { useEffect, useState } from 'react'
import { api } from '../api'
import MemoDocument from './MemoDocument'
import { FileText, Calendar, Compass, RefreshCw } from 'lucide-react'

export default function MemoPanel() {
  const [reports, setReports] = useState<any[]>([])
  const [selectedReportId, setSelectedReportId] = useState<string | null>(null)
  const [selectedReport, setSelectedReport] = useState<any>(null)
  const [loadingList, setLoadingList] = useState(true)
  const [loadingReport, setLoadingReport] = useState(false)

  const fetchReports = async () => {
    setLoadingList(true)
    try {
      const res = await api.get('/reports/list')
      setReports(res.data.reports || [])
      if (res.data.reports && res.data.reports.length > 0) {
        setSelectedReportId(res.data.reports[0]._id)
      }
    } catch (err) {
      console.error('Failed to load investment memos list:', err)
    } finally {
      setLoadingList(false)
    }
  }

  useEffect(() => {
    fetchReports()
  }, [])

  useEffect(() => {
    const fetchReportContent = async () => {
      if (!selectedReportId) return
      setLoadingReport(true)
      try {
        const res = await api.get(`/reports/${selectedReportId}`)
        setSelectedReport(res.data)
      } catch (err) {
        console.error('Failed to load memo content:', err)
      } finally {
        setLoadingReport(false)
      }
    }
    fetchReportContent()
  }, [selectedReportId])

  if (loadingList) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '40vh' }}>
        <div className="loading-spinner" />
      </div>
    )
  }

  return (
    <div className="split-layout">
      {/* Sidebar List */}
      <div className="glass-card" style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <div style={{ padding: '16px', borderBottom: '1px solid rgba(255,255,255,0.05)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontWeight: 600, fontSize: '0.95rem' }}>Screened Startups</span>
          <button onClick={fetchReports} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}>
            <RefreshCw size={14} />
          </button>
        </div>
        
        <div style={{ flexGrow: 1, overflowY: 'auto', padding: '8px' }}>
          {reports.length === 0 ? (
            <p style={{ textAlign: 'center', padding: '24px', fontSize: '0.85rem', color: 'var(--text-muted)' }}>
              No memos compiled yet.
            </p>
          ) : (
            reports.map((report) => (
              <div
                key={report._id}
                onClick={() => setSelectedReportId(report._id)}
                className={`deal-row-item ${selectedReportId === report._id ? 'active' : ''}`}
                style={{
                  padding: '12px',
                  borderRadius: 'var(--radius-sm)',
                  cursor: 'pointer',
                  marginBottom: '6px',
                  transition: 'background 0.2s',
                  background: selectedReportId === report._id ? 'rgba(255,255,255,0.05)' : 'transparent'
                }}
              >
                <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
                  <FileText size={16} color={selectedReportId === report._id ? '#8b5cf6' : 'var(--text-muted)'} />
                  <div style={{ overflow: 'hidden' }}>
                    <p style={{ fontWeight: 600, fontSize: '0.85rem', textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap', color: selectedReportId === report._id ? 'var(--text-primary)' : 'var(--text-secondary)' }}>
                      {report.company_name}
                    </p>
                    <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                      {report.created_at ? new Date(report.created_at).toLocaleDateString() : 'N/A'}
                    </span>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Memo Contents */}
      <div className="glass-card" style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {loadingReport ? (
          <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}>
            <div className="loading-spinner" />
          </div>
        ) : selectedReport ? (
          <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
            {/* Header info */}
            <div style={{ padding: '20px', borderBottom: '1px solid rgba(255,255,255,0.05)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <h1 style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                  Investment Memo: {selectedReport.company_name}
                </h1>
                <div style={{ display: 'flex', gap: '16px', marginTop: '6px', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <Calendar size={12} />
                    {new Date(selectedReport.created_at).toLocaleDateString()}
                  </span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <Compass size={12} />
                    Report Ref: {selectedReport._id.substring(0, 8)}
                  </span>
                </div>
              </div>
            </div>

            {/* Markdown Text Area */}
            <div style={{ flexGrow: 1, overflowY: 'auto', padding: '20px 24px 32px' }}>
              <MemoDocument
                content={selectedReport.content}
                companyName={selectedReport.company_name}
                createdAt={selectedReport.created_at}
                bare
              />
            </div>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', height: '100%', color: 'var(--text-muted)', gap: '12px' }}>
            <FileText size={48} strokeWidth={1} />
            <p>Select a startup to read its Investment Memo.</p>
          </div>
        )}
      </div>
    </div>
  )
}
