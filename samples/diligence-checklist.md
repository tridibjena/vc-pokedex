# Venture Diligence Checklist

**SYNTHETIC SAMPLE DOCUMENT.** Harbor Lane Ventures internal process document.
Harbor Lane Ventures is a fictional firm.

Scope scales with stage. Running the Series B list on a pre-seed company wastes
everyone's time and signals that you do not understand what stage you are
investing at.

---

## Stage scoping

| | Pre-seed / Seed | Series A | Series B+ |
|---|---|---|---|
| Target duration | 2 weeks | 4–6 weeks | 6–10 weeks |
| Customer references | 3 | 8–12 | 15–25 |
| Financial review | Founder-prepared | Quality of earnings on request | Full QoE by a third party |
| Technical review | Architecture conversation | Code and infrastructure review | Full review + security audit |
| Legal | Cap table and IP assignment | Full corporate | Full corporate + regulatory |
| Background checks | Informal reference calls | Formal on founders | Formal on all executives |

---

## 1. Market

- [ ] Bottom-up TAM built from unit count × price, not a top-down analyst figure
- [ ] Who holds the budget today, and what line item does this displace?
- [ ] Is this a budget that exists, or one that has to be created? The second is
      a materially harder sale and lengthens every cycle in the model.
- [ ] What has to be true about the market in five years for this to be large?
- [ ] Regulatory trajectory — is the tailwind durable or a single election away?

## 2. Product and technology

- [ ] Live demo, driven by the interviewer rather than the founder
- [ ] Architecture review: what actually breaks at 10× current load?
- [ ] What is bought versus built? Model dependencies, infrastructure lock-in
- [ ] Technical debt honestly assessed — ask what they would rewrite
- [ ] Security posture: SOC 2 status, penetration test history, incident log
- [ ] For AI products: what happens to the value proposition when the
      underlying model improves by a generation? Is the company a beneficiary
      or an obsolescence candidate?

## 3. Traction and metrics

Ask for the raw export, not the deck chart. Rebuild the metrics yourself.

- [ ] Monthly revenue by customer for the trailing 24 months
- [ ] Cohort retention — logo and net revenue, by cohort, not blended
- [ ] Definition audit: what exactly counts as ARR here? Pilots? Non-recurring
      services? Signed-but-not-live? Multi-year contracts recognised upfront?
- [ ] Pipeline conversion by stage, with a stale-deal analysis
- [ ] Concentration: revenue in the top 1, 3 and 10 customers
- [ ] Contracted versus recognised revenue; any revenue with a right of return
- [ ] Churn reasons for every logo lost in the last 12 months, in writing

**Metrics to compute independently:**

| Metric | Formula | Watch for |
|---|---|---|
| Burn multiple | (monthly burn × 12) ÷ net new ARR | Comparing monthly burn to an annual ARR delta understates burn ~12× |
| Net revenue retention | (start ARR + expansion − churn − contraction) ÷ start ARR | Blended NRR hides a bad recent cohort |
| CAC payback | fully-loaded S&M ÷ (new ARR × gross margin) | "Fully-loaded" must include founder selling time |
| Magic number | net new ARR ÷ prior-quarter S&M | One good quarter proves nothing |
| Gross margin | (revenue − COGS) ÷ revenue | Are support and hosting in COGS or opex? |
| Rule of 40 | growth % + FCF margin % | Only meaningful above ~$10M ARR |

## 4. Team

- [ ] Founder references — at least two the founder did not provide
- [ ] Prior working relationship between the founders, and for how long
- [ ] Equity split and vesting; anyone with meaningful equity who has left
- [ ] Key-person concentration: what breaks if the CTO leaves on Friday?
- [ ] Hiring plan against the financial model — are the roles budgeted?
- [ ] Regretted attrition in the last 18 months and the reasons given at exit
- [ ] Compensation philosophy and current below/at/above-market position

## 5. Financial

- [ ] Monthly P&L, balance sheet and cash flow, trailing 24 months
- [ ] Model reconciled to actuals for the last four quarters — how good is
      management at forecasting its own business?
- [ ] Cash position, runway, and the date of the next financing decision
- [ ] Revenue recognition policy, and whether it survives an audit
- [ ] Debt: venture debt, equipment leases, convertible instruments, covenants
- [ ] Deferred revenue, and how much of the cash balance is customer money
- [ ] Payables ageing — a stretched vendor balance is a runway lie

## 6. Legal and corporate

- [ ] Cap table with every instrument: options, warrants, SAFEs, convertible notes
- [ ] SAFEs modelled through conversion at this round's price. Founders are
      routinely surprised by post-money SAFE stacking.
- [ ] IP assignment from every founder, employee and contractor, with no gaps
      around pre-incorporation work or university employment
- [ ] Patent status, freedom-to-operate opinion where relevant
- [ ] Material contracts: any change-of-control, exclusivity or MFN provisions
- [ ] Litigation, threatened or actual
- [ ] Open-source licence audit — any AGPL or SSPL in the distributed product
- [ ] Data protection: GDPR/CCPA posture, DPAs with subprocessors, retention policy
- [ ] Employment classification — contractors who are functionally employees

## 7. Customer references

Structure the call. Unstructured reference calls produce uniformly positive
noise because the founder chose the reference.

Ask:
1. Walk me through how you evaluated this and who else you looked at.
2. What was the problem you had before? What were you doing instead?
3. Who uses it, how often, and what would happen if it disappeared tomorrow?
4. What is not good about it?
5. What would have to change for you to double your spend? To cancel?
6. Would you have paid twice the price?

Question 6 is the useful one. Question 4 is the one that separates a real
reference from a favour.

## 8. Red flags

Any one of these is a conversation, not a decline. Three of them is a decline.

- Metric definitions that change between conversations
- Refusal to provide raw data, or a "system limitation" that prevents export
- Reference customers who are investors, advisors, or friends of the founders
- Revenue concentration above 40% in one account with no exclusivity or lock-in
- Founder disagreement about the story, surfaced when interviewed separately
- A cap table with a large inactive holder — a departed co-founder with 20%
  is a fundraising problem for the life of the company
- Unexplained executive departures in the last 12 months
- Deferred payroll, or founders who have stopped taking salary without saying so
- A model whose assumptions have no relationship to the trailing 12 months
- Aggressive pushback on standard terms early in the process

## 9. Investment committee output

The memo should answer four questions and nothing else:

1. **What has to be true** for this to return the fund?
2. **What is the strongest argument against** the investment? Write it as if
   you were arguing to decline. If you cannot make it compelling, diligence
   is incomplete.
3. **What would change our mind** post-investment, and what would we watch for?
4. **What is the reserve plan** and at what point do we stop following on?
