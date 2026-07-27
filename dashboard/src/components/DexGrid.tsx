import { useState } from 'react'
import { Trash2, Check, X } from 'lucide-react'
import { STAGES, dexNumber, shortSector, stageIndex, stageShort, typeColor, verdictColor } from '../dex'
import type { DexEntry } from '../dex'
import { formatUsd } from './Ticker'

interface Props {
  entries: DexEntry[]
  onSelect: (entry: DexEntry) => void
  onRemove?: (entry: DexEntry) => Promise<void> | void
}

export default function DexGrid({ entries, onSelect, onRemove }: Props) {
  return (
    <div className="dex-grid">
      {entries.map((e) => (
        // The card is a <button>; the remove control has to be a sibling rather
        // than a nested button, which is invalid HTML and breaks activation.
        <div className="dex-cell" key={e.key}>
          {e.pending ? <PendingCard entry={e} /> : <DexCard entry={e} onSelect={onSelect} />}
          {onRemove && <RemoveButton entry={e} onRemove={onRemove} />}
        </div>
      ))}
    </div>
  )
}

/**
 * Two-step delete.
 *
 * Removal is irreversible — it drops the deal, the memo, the dossier and the
 * embedded chunks — so a stray click must not do it. Confirming inline rather
 * than in a modal keeps the action attached to the card it affects.
 */
function RemoveButton({
  entry,
  onRemove,
}: {
  entry: DexEntry
  onRemove: (entry: DexEntry) => Promise<void> | void
}) {
  const [armed, setArmed] = useState(false)
  const [busy, setBusy] = useState(false)

  if (busy) {
    return (
      <span className="dex-remove dex-remove-busy" aria-live="polite">
        <span className="loading-spinner" style={{ width: 11, height: 11, borderWidth: 2 }} />
      </span>
    )
  }

  if (armed) {
    return (
      <span className="dex-remove-confirm" role="group" aria-label={`Remove ${entry.companyName}?`}>
        <button
          type="button"
          className="dex-remove-yes"
          onClick={async () => {
            setBusy(true)
            try {
              await onRemove(entry)
            } finally {
              setBusy(false)
              setArmed(false)
            }
          }}
        >
          <Check size={11} /> remove
        </button>
        <button type="button" className="dex-remove-no" title="Cancel" onClick={() => setArmed(false)}>
          <X size={11} />
        </button>
      </span>
    )
  }

  return (
    <button
      type="button"
      className="dex-remove"
      title={`Remove ${entry.companyName} from the Dex`}
      aria-label={`Remove ${entry.companyName} from the Dex`}
      onClick={() => setArmed(true)}
    >
      <Trash2 size={12} />
    </button>
  )
}

function DexCard({ entry, onSelect }: { entry: DexEntry; onSelect: (e: DexEntry) => void }) {
  const accent = typeColor(entry.sector)
  const verdict = verdictColor(entry.recommendation, entry.overallScore)

  return (
    <button
      type="button"
      className="dex-card"
      onClick={() => onSelect(entry)}
      style={{ ['--dex-accent' as string]: accent, ['--dex-verdict' as string]: verdict }}
      aria-label={`${entry.companyName}, ${entry.sector}, ${entry.stage}, score ${entry.overallScore ?? 'none'}`}
    >
      <header className="dex-card-top">
        <span className="dex-num">NO.{dexNumber(entry.dex)}</span>
        <span className="dex-type" style={{ color: accent, borderColor: `${accent}66` }} title={entry.sector}>
          {shortSector(entry.sector)}
        </span>
      </header>

      <h3 className="dex-name" title={entry.companyName}>{entry.companyName}</h3>

      <FundingLine entry={entry} />

      <div className="dex-mid">
        <StatSpine entry={entry} />
        <div className="dex-verdict">
          <span className="dex-score">{entry.overallScore != null ? entry.overallScore.toFixed(1) : '—'}</span>
          {entry.recommendation && <span className="dex-rec">{entry.recommendation}</span>}
        </div>
      </div>

      <EvolutionChain stage={entry.stage} />
    </button>
  )
}

function FundingLine({ entry }: { entry: DexEntry }) {
  const amount = formatUsd(entry.roundAmount ?? null)
  const valuation = formatUsd(entry.valuation ?? null)
  const parts = [entry.lastRound, amount, valuation ? `@ ${valuation}` : null].filter(Boolean)

  return (
    <div className="dex-funding">
      {parts.length ? parts.join('  ·  ') : <span className="dex-funding-none">no round disclosed</span>}
    </div>
  )
}

/**
 * Five dimension scores as a compact equalizer.
 *
 * These used to be five labelled progress bars per card — forty coloured bars
 * across a grid of eight, which read as a generated dashboard template and
 * drowned out the score. Height-encoded columns carry the same information in a
 * fifth of the space; the numbers are still available on hover.
 */
function StatSpine({ entry }: { entry: DexEntry }) {
  if (entry.stats.length === 0) {
    return <div className="dex-spine dex-spine-empty">awaiting scorecard</div>
  }
  return (
    <div className="dex-spine" role="img" aria-label={entry.stats.map((s) => `${s.label} ${s.value}`).join(', ')}>
      {entry.stats.map((s) => (
        <span
          key={s.key}
          className="dex-spine-col"
          title={`${s.label} ${s.value}/10`}
          style={{ height: `${Math.max(10, Math.min(10, s.value) * 10)}%` }}
        />
      ))}
    </div>
  )
}

function EvolutionChain({ stage }: { stage: string }) {
  const current = stageIndex(stage)
  return (
    <div className="dex-evo" title={`Stage: ${stage}`}>
      {STAGES.map((s, i) => {
        const state = current === -1 ? 'unknown' : i < current ? 'past' : i === current ? 'current' : 'future'
        return (
          <span key={s} className={`dex-evo-node ${state}`}>
            {stageShort(s)}
          </span>
        )
      })}
    </div>
  )
}

function PendingCard({ entry }: { entry: DexEntry }) {
  return (
    <div className="dex-card dex-card-pending" aria-label={`${entry.companyName}, analysis in progress`}>
      <header className="dex-card-top">
        <span className="dex-num">NO.{dexNumber(entry.dex)}</span>
        <span className="dex-pending-dot" />
      </header>
      <div className="dex-silhouette">?</div>
      <h3 className="dex-name dex-name-muted" title={entry.companyName}>{entry.companyName}</h3>
      <p className="dex-pending-label">scanning…</p>
    </div>
  )
}
