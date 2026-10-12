import { useEffect, useState } from 'react'
import { FileText, RefreshCw } from 'lucide-react'
import { api } from '../api'
import MemoDocument from './MemoDocument'

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
      <div className="panel-loading panel-loading-tall">
        <span className="spinner" />
      </div>
    )
  }

  return (
    <div className="memo-layout">
      <nav className="comic-card memo-index" aria-label="Memos">
        <div className="memo-index-head">
          <span className="section-title">Screened startups</span>
          <button onClick={fetchReports} className="btn btn-sm btn-icon" title="Refresh" aria-label="Refresh memos">
            <RefreshCw size={13} />
          </button>
        </div>

        {reports.length === 0 ? (
          <p className="memo-index-empty">No memos written yet.</p>
        ) : (
          <ul className="memo-index-list">
            {reports.map((report) => (
              <li key={report._id}>
                <button
                  type="button"
                  className="memo-index-item"
                  aria-current={selectedReportId === report._id ? 'true' : undefined}
                  onClick={() => setSelectedReportId(report._id)}
                >
                  <span className="memo-index-name">{report.company_name}</span>
                  <span className="memo-index-date">
                    {report.created_at ? new Date(report.created_at).toLocaleDateString() : 'N/A'}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </nav>

      <section className="comic-card memo-reader">
        {loadingReport ? (
          <div className="panel-loading">
            <span className="spinner" />
          </div>
        ) : selectedReport ? (
          <>
            <header className="memo-reader-head">
              <h2 className="memo-reader-title">{selectedReport.company_name}</h2>
              <p className="memo-reader-meta">
                {new Date(selectedReport.created_at).toLocaleDateString()} · ref {selectedReport._id.substring(0, 8)}
              </p>
            </header>
            <MemoDocument
              content={selectedReport.content}
              companyName={selectedReport.company_name}
              createdAt={selectedReport.created_at}
              bare
            />
          </>
        ) : (
          <div className="empty-card empty-card-flat">
            <FileText size={36} strokeWidth={2} aria-hidden="true" />
            <p>Select a startup to read its investment memo.</p>
          </div>
        )}
      </section>
    </div>
  )
}
