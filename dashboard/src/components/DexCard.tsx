import { useState } from 'react'
import { Check, MapPin, ScrollText, Trash2, X } from 'lucide-react'
import {
  STAGES,
  asVerdict,
  dexNumber,
  hasPin,
  shortSector,
  stageIndex,
  stageShort,
  typeColor,
  verdictColor,
  verdictTextColor,
} from '../dex'
import type { DexEntry } from '../dex'
import { formatUsd } from '../format'

interface Props {
  entry: DexEntry
  selected: boolean
  hovered: boolean
  /** Fly to it and put it in the spotlight. */
  onOpen: (entry: DexEntry) => void
  /** The long-form dossier in the rail. */
  onDossier: (entry: DexEntry) => void
  onHover: (key: string | null) => void
  onRemove: (entry: DexEntry) => Promise<void> | void
}

/**
 * One Dex entry in the list rail — the counterpart of a pin on the map.
 *
 * Laid out like a review card: who it is and where, the call, then the case
 * for and against, then actions. The whole card opens the dossier; the action
 * row is a sibling of that target, never nested inside a button.
 */
export default function DexCard({ entry, selected, hovered, onOpen, onDossier, onHover, onRemove }: Props) {
  if (entry.state === 'scanning') return <ScanningCard entry={entry} selected={selected} />
  if (entry.state === 'failed') return <FailedCard entry={entry} onRemove={onRemove} />

  const accent = typeColor(entry.sector)
  const pinned = hasPin(entry)

  return (
    <article
      className={`dex-card${selected ? ' is-selected' : ''}${hovered ? ' is-hovered' : ''}`}
      onMouseEnter={() => onHover(entry.key)}
      onMouseLeave={() => onHover(null)}
    >
      <button type="button" className="dex-card-open" onClick={() => onOpen(entry)}>
        <span className="dex-card-top">
          <span className="dex-num">No.{dexNumber(entry.dex)}</span>
          <span className="tag" style={{ ['--tag-color' as string]: accent }} title={entry.sector}>
            {shortSector(entry.sector)}
          </span>
          <StageTag stage={entry.stage} />
        </span>

        <span className="dex-card-name">{entry.companyName}</span>

        <span className="dex-card-where">
          <MapPin size={12} strokeWidth={2.5} aria-hidden="true" />
          {entry.location && entry.location !== 'Unknown' ? entry.location : 'HQ unknown'}
          {pinned && entry.geoPrecision !== 'address' && <span className="dex-card-approx">· city pin</span>}
        </span>

        {entry.product && <span className="dex-card-tagline">{entry.product}</span>}

        <span className="dex-card-verdict">
          <VerdictBadge recommendation={entry.recommendation} score={entry.overallScore} />
          <StatSpine entry={entry} />
          <FundingLine entry={entry} />
        </span>

        {(entry.strengths.length > 0 || entry.risks.length > 0) && (
          <span className="dex-case">
            {entry.strengths.length > 0 && (
              <span className="dex-case-block">
                <span className="dex-case-label dex-case-bull">Bull case</span>
                <span className="dex-case-list">
                  {entry.strengths.slice(0, 2).map((s, i) => (
                    <span key={i} className="dex-case-item">{s}</span>
                  ))}
                </span>
              </span>
            )}
            {entry.risks.length > 0 && (
              <span className="dex-case-block">
                <span className="dex-case-label dex-case-bear">Pass if</span>
                <span className="dex-case-list">
                  {entry.risks.slice(0, 2).map((s, i) => (
                    <span key={i} className="dex-case-item">{s}</span>
                  ))}
                </span>
              </span>
            )}
          </span>
        )}
      </button>

      <div className="dex-card-actions">
        <button
          type="button"
          className="btn btn-sm"
          onClick={() => onOpen(entry)}
          disabled={!pinned}
          title={pinned ? 'Show on the map' : 'No HQ location found'}
        >
          <MapPin size={13} /> Map
        </button>
        <button type="button" className="btn btn-sm" onClick={() => onDossier(entry)}>
          <ScrollText size={13} /> Dossier
        </button>
        <RemoveButton entry={entry} onRemove={onRemove} />
      </div>
    </article>
  )
}

export function VerdictBadge({
  recommendation,
  score,
  large,
}: {
  recommendation: string | null
  score: number | null
  large?: boolean
}) {
  const verdict = asVerdict(recommendation)
  return (
    <span
      className={`verdict-badge${large ? ' verdict-badge-lg' : ''}`}
      style={{ background: verdictColor(recommendation, score), color: verdictTextColor(recommendation) }}
    >
      <span className="verdict-word">{verdict ?? 'Unscored'}</span>
      <span className="verdict-score">{score != null ? score.toFixed(1) : '—'}</span>
    </span>
  )
}

export function StageTag({ stage }: { stage: string }) {
  return (
    <span className="tag tag-plain" title={`Stage: ${stage}`}>
      {stageIndex(stage) === -1 ? stage : stage.replace('-', ' ')}
    </span>
  )
}

function FundingLine({ entry }: { entry: DexEntry }) {
  const amount = formatUsd(entry.roundAmount ?? null)
  const valuation = formatUsd(entry.valuation ?? null)
  const parts = [entry.lastRound, amount, valuation ? `@ ${valuation}` : null].filter(Boolean)
  if (!parts.length) return null
  return <span className="dex-card-funding">{parts.join(' · ')}</span>
}

/**
 * Five dimension scores as a compact equalizer: height-encoded columns, the
 * numbers on hover and in the accessible label.
 */
export function StatSpine({ entry }: { entry: DexEntry }) {
  if (entry.stats.length === 0) return null
  return (
    <span className="dex-spine" role="img" aria-label={entry.stats.map((s) => `${s.label} ${s.value}`).join(', ')}>
      {entry.stats.map((s) => (
        <span
          key={s.key}
          className="dex-spine-col"
          title={`${s.label} ${s.value}/10`}
          style={{ height: `${Math.max(10, Math.min(10, s.value) * 10)}%` }}
        />
      ))}
    </span>
  )
}

export function EvolutionChain({ stage }: { stage: string }) {
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

/**
 * No remove control while a scan runs: deleting the entry would not stop the
 * background job, which would then write an orphaned deal back into the Dex.
 */
function ScanningCard({ entry, selected }: { entry: DexEntry; selected: boolean }) {
  return (
    <article
      className={`dex-card dex-card-scanning${selected ? ' is-selected' : ''}`}
      aria-label={`${entry.companyName}, scan in progress`}
    >
      <div className="dex-card-open dex-card-static">
        <span className="dex-card-top">
          <span className="dex-num">No.{dexNumber(entry.dex)}</span>
          <span className="tag tag-plain scanning-tag">Scanning…</span>
        </span>
        <span className="dex-card-name dex-card-name-muted">{entry.companyName}</span>
        <span className="dex-card-tagline">
          Six agents are researching, benchmarking and scoring it. The pin drops when they finish.
        </span>
      </div>
    </article>
  )
}

function FailedCard({ entry, onRemove }: { entry: DexEntry; onRemove: Props['onRemove'] }) {
  return (
    <article className="dex-card dex-card-failed" aria-label={`${entry.companyName}, scan failed`}>
      <div className="dex-card-open dex-card-static">
        <span className="dex-card-top">
          <span className="dex-num">No.{dexNumber(entry.dex)}</span>
          <span className="tag tag-failed">Scan failed</span>
        </span>
        <span className="dex-card-name dex-card-name-muted">{entry.companyName}</span>
        {entry.error && <span className="dex-card-error">{entry.error}</span>}
      </div>
      <div className="dex-card-actions">
        <RemoveButton entry={entry} onRemove={onRemove} />
      </div>
    </article>
  )
}

/**
 * Two-step delete.
 *
 * Removal is irreversible — it drops the deal, the memo, the dossier and the
 * embedded chunks — so a stray click must not do it. Confirming inline rather
 * than in a modal keeps the action attached to the card it affects.
 */
export function RemoveButton({ entry, onRemove }: { entry: DexEntry; onRemove: Props['onRemove'] }) {
  const [armed, setArmed] = useState(false)
  const [busy, setBusy] = useState(false)

  if (busy) {
    return (
      <span className="dex-remove-busy" aria-live="polite">
        <span className="spinner spinner-sm" /> removing
      </span>
    )
  }

  if (armed) {
    return (
      <span className="dex-remove-confirm" role="group" aria-label={`Remove ${entry.companyName}?`}>
        <button
          type="button"
          className="btn btn-sm btn-danger"
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
          <Check size={13} /> Sure?
        </button>
        <button type="button" className="btn btn-sm btn-icon" title="Keep it" aria-label="Keep it" onClick={() => setArmed(false)}>
          <X size={13} />
        </button>
      </span>
    )
  }

  return (
    <button
      type="button"
      className="btn btn-sm btn-ghost dex-remove"
      title={`Remove ${entry.companyName} from the Dex`}
      aria-label={`Remove ${entry.companyName}`}
      onClick={() => setArmed(true)}
    >
      <Trash2 size={13} /> Remove
    </button>
  )
}
