import { useRef } from 'react'
import { Download, FileText } from 'lucide-react'
import { renderMarkdown } from '../markdown'

interface Props {
  content: string
  companyName?: string
  createdAt?: string
  /** Rendered inside a card that already has a title (the Dex detail). */
  bare?: boolean
}

/**
 * The investment memo as a document.
 *
 * Export goes through the browser's print pipeline rather than a JS PDF
 * library: the result is real selectable text with working page breaks, and it
 * adds nothing to the bundle. `@media print` in style.css strips the app chrome
 * and re-inks the memo for paper.
 */
export default function MemoDocument({ content, companyName, createdAt, bare }: Props) {
  const ref = useRef<HTMLDivElement>(null)

  const exportPdf = () => {
    // Give the browser a title it will use as the default filename.
    const previous = document.title
    const stamp = createdAt ? new Date(createdAt).toISOString().slice(0, 10) : ''
    document.title = [companyName || 'Investment Memo', stamp, 'VC Pokedex']
      .filter(Boolean)
      .join(' — ')
    window.addEventListener('afterprint', () => { document.title = previous }, { once: true })
    window.print()
  }

  return (
    <div className="memo-block">
      <div className="memo-toolbar">
        {!bare && (
          <h3 className="section-title">
            <FileText size={14} aria-hidden="true" />
            Investment memo
          </h3>
        )}
        <button className="btn btn-sm" onClick={exportPdf} title="Save as PDF">
          <Download size={13} aria-hidden="true" />
          Export PDF
        </button>
      </div>

      <div className="memo-doc" ref={ref}>
        {/* Only appears on paper — the screen already has a header. */}
        <div className="print-only print-header">
          <div className="print-title">{companyName || 'Investment Memo'}</div>
          <div className="print-meta">
            VC Pokedex · investment memo
            {createdAt ? ` · ${new Date(createdAt).toLocaleDateString()}` : ''}
          </div>
        </div>

        <div className="md" dangerouslySetInnerHTML={{ __html: renderMarkdown(content) }} />
      </div>
    </div>
  )
}
