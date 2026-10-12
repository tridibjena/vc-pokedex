import { useEffect, useRef } from 'react'
import { ArrowLeft, MapPin, X } from 'lucide-react'
import { dexNumber, shortSector, typeColor } from '../dex'
import type { DexEntry } from '../dex'
import { formatUsd } from '../format'
import { scoreColor } from '../theme'
import { DossierBody } from './DealDetail'
import { EvolutionChain, StageTag, VerdictBadge } from './DexCard'

const DIMENSION_LABEL: Record<string, string> = {
  market_size_score: 'Market',
  team_score: 'Team',
  traction_score: 'Traction',
  competitive_moat_score: 'Moat',
  financial_health_score: 'Financials',
}

interface Props {
  entry: DexEntry
  onBack: () => void
}

/**
 * A startup in the spotlight: what the map flew to, sized up over it.
 *
 * The card opens on the first look — who, where, the call, the five scores,
 * the case for and against, the last round — with the full dossier straight
 * below it in the same scroll. Back to map stays pinned to the bottom edge.
 */
export default function SpotlightCard({ entry, onBack }: Props) {
  const backRef = useRef<HTMLButtonElement>(null)

  // Land keyboard users on the way out, so Back is one keypress away.
  useEffect(() => {
    backRef.current?.focus({ preventScroll: true })
  }, [entry.key])

  const amount = formatUsd(entry.roundAmount ?? null)
  const valuation = formatUsd(entry.valuation ?? null)
  const funding = [entry.lastRound, amount, valuation ? `@ ${valuation}` : null].filter(Boolean)

  return (
    <section className="spotlight" aria-label={`${entry.companyName} in the spotlight`}>
      <div className="spotlight-top">
        <span className="dex-num">No.{dexNumber(entry.dex)}</span>
        <span className="tag" style={{ ['--tag-color' as string]: typeColor(entry.sector) }} title={entry.sector}>
          {shortSector(entry.sector)}
        </span>
        <StageTag stage={entry.stage} />
        <button type="button" className="btn btn-sm btn-icon spotlight-close" onClick={onBack} aria-label="Back to the map">
          <X size={14} />
        </button>
      </div>

      <h2 className="spotlight-name">{entry.companyName}</h2>

      <p className="spotlight-where">
        <MapPin size={14} strokeWidth={2.5} aria-hidden="true" />
        {entry.location && entry.location !== 'Unknown' ? entry.location : 'HQ unknown'}
        {entry.geoPrecision && entry.geoPrecision !== 'address' && <span className="dex-card-approx">· city pin</span>}
      </p>

      {entry.product && <p className="spotlight-pitch">{entry.product}</p>}

      <div className="spotlight-verdict">
        <VerdictBadge recommendation={entry.recommendation} score={entry.overallScore} large />
        <EvolutionChain stage={entry.stage} />
      </div>

      {entry.stats.length > 0 && (
        <ul className="spotlight-scores">
          {entry.stats.map((s) => (
            <li key={s.key}>
              <span className="spotlight-score-label">{DIMENSION_LABEL[s.key] ?? s.label}</span>
              <span className="score-bar-track">
                <span className="score-bar-fill" style={{ width: `${s.value * 10}%`, background: scoreColor(s.value) }} />
              </span>
              <span className="score-bar-value">{s.value}</span>
            </li>
          ))}
        </ul>
      )}

      {(entry.strengths.length > 0 || entry.risks.length > 0) && (
        <div className="spotlight-case">
          {entry.strengths.length > 0 && (
            <div>
              <span className="dex-case-label dex-case-bull">Bull case</span>
              <ul className="bullet-list">
                {entry.strengths.map((s, i) => (
                  <li key={i} title={s}>
                    <span className="clamp-2">{s}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {entry.risks.length > 0 && (
            <div>
              <span className="dex-case-label dex-case-bear">Pass if</span>
              <ul className="bullet-list">
                {entry.risks.map((s, i) => (
                  <li key={i} title={s}>
                    <span className="clamp-2">{s}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {funding.length > 0 && <p className="spotlight-funding">Last round · {funding.join(' · ')}</p>}

      <div className="spotlight-dossier">
        <DossierBody entry={entry} withSummary={false} />
      </div>

      <div className="spotlight-actions">
        <button ref={backRef} type="button" className="btn btn-pink" onClick={onBack}>
          <ArrowLeft size={15} /> Back to map
        </button>
      </div>
    </section>
  )
}
