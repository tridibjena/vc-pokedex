/**
 * Minimal block-level Markdown → HTML renderer.
 *
 * Shared by the memo viewer and the chat transcript. Both previously carried
 * their own copy; the memo one had no table support at all, so the metric
 * tables the memo prompt explicitly asks for rendered as raw pipe-delimited
 * text, and every wrapped source line became its own <p> with a full margin.
 *
 * Input is escaped before any tag is emitted, so model output cannot inject
 * markup. Styling lives in style.css under `.md`, not in inline attributes.
 */

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

/** Inline spans: code, bold, italic, links. Runs on already-escaped text. */
function inline(text: string): string {
  return text
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>')
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
}

const isTableRow = (line: string) => line.startsWith('|') && line.endsWith('|')
const isDivider = (line: string) => /^\|[\s:|-]+\|$/.test(line)

function splitRow(line: string): string[] {
  return line.slice(1, -1).split('|').map((c) => c.trim())
}

export function renderMarkdown(source: string): string {
  if (!source) return ''

  const lines = escapeHtml(source).split('\n')
  const out: string[] = []
  let i = 0

  while (i < lines.length) {
    const line = lines[i]
    const trimmed = line.trim()

    // Blank
    if (!trimmed) {
      i++
      continue
    }

    // Fenced code block
    if (trimmed.startsWith('```')) {
      const body: string[] = []
      i++
      while (i < lines.length && !lines[i].trim().startsWith('```')) {
        body.push(lines[i])
        i++
      }
      i++ // closing fence
      out.push(`<pre><code>${body.join('\n')}</code></pre>`)
      continue
    }

    // Horizontal rule
    if (/^(-{3,}|\*{3,}|_{3,})$/.test(trimmed)) {
      out.push('<hr/>')
      i++
      continue
    }

    // Heading
    const heading = /^(#{1,6})\s+(.*)$/.exec(trimmed)
    if (heading) {
      const level = heading[1].length
      out.push(`<h${level}>${inline(heading[2])}</h${level}>`)
      i++
      continue
    }

    // Table — a header row, an optional divider, then body rows
    if (isTableRow(trimmed)) {
      const header = splitRow(trimmed)
      let j = i + 1
      const hasDivider = j < lines.length && isDivider(lines[j].trim())
      if (hasDivider) j++

      const body: string[][] = []
      while (j < lines.length && isTableRow(lines[j].trim())) {
        if (!isDivider(lines[j].trim())) body.push(splitRow(lines[j].trim()))
        j++
      }

      // A single pipe line with no divider and no body isn't a table.
      if (hasDivider || body.length > 0) {
        const head = `<thead><tr>${header.map((c) => `<th>${inline(c)}</th>`).join('')}</tr></thead>`
        const rows = body
          .map((r) => `<tr>${r.map((c) => `<td>${inline(c)}</td>`).join('')}</tr>`)
          .join('')
        out.push(`<div class="md-table-wrap"><table>${head}<tbody>${rows}</tbody></table></div>`)
        i = j
        continue
      }
    }

    // List — consecutive bullet or ordered items
    const bullet = /^\s*[-*+]\s+(.*)$/.exec(line)
    const ordered = /^\s*\d+[.)]\s+(.*)$/.exec(line)
    if (bullet || ordered) {
      const tag = ordered ? 'ol' : 'ul'
      const items: string[] = []
      while (i < lines.length) {
        const m = ordered
          ? /^\s*\d+[.)]\s+(.*)$/.exec(lines[i])
          : /^\s*[-*+]\s+(.*)$/.exec(lines[i])
        if (!m) break
        items.push(`<li>${inline(m[1])}</li>`)
        i++
      }
      out.push(`<${tag}>${items.join('')}</${tag}>`)
      continue
    }

    // Blockquote
    if (trimmed.startsWith('&gt;')) {
      const body: string[] = []
      while (i < lines.length && lines[i].trim().startsWith('&gt;')) {
        body.push(lines[i].trim().replace(/^&gt;\s?/, ''))
        i++
      }
      out.push(`<blockquote>${inline(body.join(' '))}</blockquote>`)
      continue
    }

    // Paragraph — join consecutive plain lines rather than one <p> per line.
    const para: string[] = []
    while (i < lines.length) {
      const l = lines[i]
      const t = l.trim()
      if (
        !t ||
        t.startsWith('```') ||
        /^#{1,6}\s/.test(t) ||
        isTableRow(t) ||
        /^\s*[-*+]\s+/.test(l) ||
        /^\s*\d+[.)]\s+/.test(l) ||
        /^(-{3,}|\*{3,}|_{3,})$/.test(t) ||
        t.startsWith('&gt;')
      ) {
        break
      }
      para.push(t)
      i++
    }
    if (para.length) out.push(`<p>${inline(para.join(' '))}</p>`)
  }

  return out.join('\n')
}
