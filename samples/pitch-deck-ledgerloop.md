# LedgerLoop — Seed Round

**SYNTHETIC SAMPLE DOCUMENT. LedgerLoop is a fictional company.**

Raising $6M Seed · Austin, TX · Founded 2024

---

## The one-line version

LedgerLoop is embedded accounts-receivable financing for vertical SaaS
platforms. Their merchants get paid on invoice day instead of day 47; the
platform earns a share; we take the credit risk and the spread.

## The problem

A roofing contractor invoices $84,000 on completion and is paid in 47 days.
Payroll runs every 14. The gap is filled with a personal credit card at 24% APR,
or the job is not taken at all.

Traditional factoring exists but is priced for a different world: 3.5% of face
value, a 30-page master agreement, personal guarantees, and a two-week
underwriting cycle for a business that needs money on Thursday.

The vertical SaaS platform running that contractor's business already knows
everything an underwriter would ask. It has the work order, the completion
photo, the customer's payment history across 400 other contractors, and the
invoice itself. It just has no way to act on it.

## What we do

One API. The platform adds a "Get paid now" button; we underwrite in under 400
milliseconds off data the platform already holds and fund within one business
day.

- Advance rate: 90% of invoice face value
- Fee: 1.9% for net-30, 2.6% for net-60
- Platform revenue share: 22% of our fee
- No personal guarantee, no master agreement, no minimum volume

## Why now

1. **Vertical SaaS reached scale.** ServiceTitan, Jobber and Procore each run
   >$20B of annualised invoice volume through platforms that monetise at 2–3%.
2. **Instant payment rails went live.** FedNow settlement removed the two-day
   float that made small advances uneconomic.
3. **Platforms want it.** Payments monetisation has compressed. Every vertical
   SaaS board has "financial services attach" on the 2026 plan and no credit team.

## Traction

Live 11 months.

| | Q3 2025 | Q4 2025 | Q1 2026 | Q2 2026 |
|---|---|---|---|---|
| Platform partners | 2 | 3 | 6 | 9 |
| Active merchants | 340 | 1,120 | 2,890 | 5,410 |
| Advance volume | $2.1M | $7.8M | $21.4M | $44.6M |
| Net revenue | $41K | $152K | $418K | $871K |
| Loss rate (annualised) | 1.4% | 1.1% | 0.9% | 0.8% |

- ARR run-rate: $3.5M
- Net revenue retention: 164%
- Prior-year ARR: $610K → **year-over-year growth 474%**
- 71% of merchants who use the product once use it again within 60 days

Loss rate is falling because the model now sees repeat payer behaviour. An
invoice to a payer we have collected from three times prices 40bps below a
first-time payer.

## Unit economics

Per $100,000 of advance volume:

| | |
|---|---|
| Gross fee (blended 2.1%) | $2,100 |
| Platform revenue share (22%) | ($462) |
| Cost of capital (9.4% APR, 38-day duration) | ($979) |
| Expected credit loss (0.8%) | ($800) — recovers to ($210) net of collections |
| Servicing and payment cost | ($95) |
| **Contribution** | **$354** |

Contribution margin: 16.9% of gross fee, improving with the cost of capital as
we move from a fund facility to a warehouse line.

- CAC per platform partner: $46,000 fully loaded
- Average platform contributes $290K of annual net revenue by month 12
- Payback: 4.8 months

## Capital structure

We do not lend off the balance sheet. A $60M warehouse facility from a regional
bank funds the advances at SOFR + 4.1%, with LedgerLoop holding a 6% first-loss
piece. Equity is not consumed by loan book growth — that is the whole point of
the structure, and it is what separates us from the balance-sheet lenders that
blew up in 2022.

## Competition

**Traditional factors (Triumph, RTS)** — 3.5% pricing, weeks of underwriting,
sold direct. We are a third the price and invisible.

**Parafin, Wayflyer** — merchant cash advance against future revenue, not
against a specific receivable. Different product, worse pricing for the
merchant, and they cannot underwrite a $84K job.

**The platforms themselves** — the real risk. ServiceTitan could build this.
Our answer: they would need a credit team, a warehouse facility, a collections
operation and a state-by-state lending licence footprint. We have 41 state
licences and it took us 14 months. That is the moat, and it is a boring one.

## Team

**Adaeze Okonkwo, CEO** — led underwriting at Square Capital, took the small-
business loan book from $200M to $2.1B in originations. Built the licensing
footprint there too.

**Marcus Bell, CTO** — early engineer at Plaid, then eight years building
core ledger infrastructure at Modern Treasury.

**Sofia Restrepo, Head of Credit** — 12 years at Capital One, latterly running
small-business credit policy across a $9B book.

9 employees.

## Financials

- Cash on hand: $2.8M
- Monthly net burn: $385K
- Runway: 7.3 months
- Post-raise runway: 21 months

Net new ARR over the trailing twelve months: $2.9M. Annualised burn of $4.6M
against that gives a **burn multiple of 1.6×** — good for a seed-stage lender,
and it is falling.

## The ask

$6M seed. 18 months to $12M ARR and a Series A.

- 40% — engineering, principally the underwriting model and platform SDK
- 25% — credit and collections
- 20% — the remaining 9 state licences and compliance
- 15% — general and administrative

## Risks

- **Credit cycle.** Our loss model has never seen a recession. A 2008-style
  contraction in residential construction takes losses to an estimated 4.2%,
  which wipes out contribution and eats into the first-loss piece.
- **Warehouse concentration.** One facility, one bank. If it is pulled,
  origination stops within days. A second lender is in diligence.
- **Regulatory.** State-level commercial financing disclosure rules (CA, NY, UT)
  are expanding. We comply today; the trend is toward APR-equivalent disclosure
  that would make our pricing look worse than it is.
- **Platform concentration.** Top two partners are 58% of volume.
