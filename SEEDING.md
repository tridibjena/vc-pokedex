# Comps Corpus Seeding

The comparable-deals corpus is what `comps_agent` benchmarks a new startup
against. This document makes that index reproducible.

There are two seeders. **`seed_edgar.py` is the real one**; `seed_comps.py` is a
15-record synthetic fallback for offline demos.

---

## 1. `seed_edgar.py` — real SEC Form D filings (preferred)

```bash
python seed_edgar.py                          # 2 recent quarters, 200 comps
python seed_edgar.py --quarters 4 --limit 400
python seed_edgar.py --dry-run                # parse and print, zero API calls
```

### Why Form D

Form D is the notice filed for a Regulation D exempt offering — effectively
every US private round. The SEC publishes it as bulk structured data, so issuer,
sector, and **actual money raised** are public and free.

| | |
|---|---|
| Dataset | `https://www.sec.gov/files/structureddata/data/form-d-data-sets/{YYYY}q{N}_d.zip` |
| Size | ~3.6 MB/quarter, ~15,700 filings |
| Auth | none — but a declared `User-Agent` is required |
| Cache | `data/edgar/` |

The older `/files/dera/data/...` path 404s; use `structureddata`.

### Tables used

| File | Fields consumed |
|---|---|
| `OFFERING.tsv` | `INDUSTRYGROUPTYPE`, `REVENUERANGE`, `SALE_DATE`, `TOTALOFFERINGAMOUNT`, `TOTALAMOUNTSOLD` |
| `ISSUERS.tsv` | `ENTITYNAME`, `CIK`, `CITY`, `STATEORCOUNTRYDESCRIPTION`, `YEAROFINC_VALUE_ENTERED` |
| `RELATEDPERSONS.tsv` | `FIRSTNAME`, `LASTNAME` (executives / directors) |

Joined on `ACCESSIONNUMBER`.

### Filtering

Raw Form D is dominated by things that are **not** startups. Of 15,735 filings in
2026Q1, **10,135 are `Pooled Investment Fund`** — the VC funds themselves. Those
plus real-estate and oil-and-gas vehicles are excluded outright, because a REIT
is not a comparable deal for a startup and its presence poisons retrieval.

`tools/edgar.py` keeps an explicit **allowlist** (`SECTOR_MAP`) and drops
everything else. After filtering, 2026Q1 yields ~1,485 venture-relevant
offerings. A further floor of `TOTALAMOUNTSOLD >= $250,000` removes noise.

### Inferred, not disclosed

Form D has **no stage field**. Stage is inferred from round size:

| Amount sold | Stage |
|---|---|
| < $1M | pre-seed |
| $1M – $5M | seed |
| $5M – $20M | series-a |
| $20M – $60M | series-b |
| > $60M | growth |

This is a heuristic and is labelled as such in the comp text
("Estimated stage from round size"). Do not read it as a disclosed fact.

### What Form D does NOT give you

**No ARR, no burn, no headcount.** Those are not public at scale for private US
companies. Comps therefore carry round size and a revenue *band*
(`REVENUERANGE`), and `REVENUERANGE` is `Decline to Disclose` on 8,648 of 15,735
filings. The memo and scorecard prompts simply see fewer metrics for these comps
than for an uploaded deck.

### Record shape

```python
id   = "formd_0001865052-26-000004"
text = ("Gearflow Inc. is a Technology company based in Chicago, ILLINOIS. "
        "The company raised $3.6M of a $3.8M Regulation D offering with first "
        "sale on 2024-07-11. Estimated stage from round size: seed. "
        "Key people: Luke Powers, Greg Owens, Austin Yount, Benjamin Preston. "
        "Industry classification: Other Technology. "
        "Source: SEC Form D filing 0001865052-26-000004.")
meta = {"company_name", "sector", "stage", "industry_group", "amount_sold",
        "offering_amount", "revenue_range", "location", "year_incorporated",
        "sale_date", "cik", "accession", "source": "SEC Form D"}
```

Ids are the accession number, so re-running **updates** rather than duplicates.

### SEC fair-access rules

- Declare a **real** contact in `SEC_USER_AGENT` (`.env`). The shipped default is
  a placeholder and the script warns when it is unchanged.
- Limit 10 requests/second. This script makes one request per quarter and
  caches, so it is nowhere near the cap.

### Rate limits (Gemini, not SEC)

The free embedding tier allows **100 requests/minute, metered per input item**,
not per batched call. A 232-comp seed therefore trips it partway through.
`tools/llm_client.py` paces items with a sliding-window limiter
(`EMBED_ITEMS_PER_MINUTE`, default 90), so a large seed pauses rather than
failing. A 232-record run takes roughly three minutes.

---

## 2. `seed_comps.py` — synthetic fallback

```bash
python seed_comps.py
```

15 hand-written records spanning SaaS / AI / FinTech / Biotech / Consumer /
CleanTech at seed through series-B. They are plausible but **not real filings**.
Useful for offline demos and for exercising retrieval without network access;
not a defensible benchmark for a real investment decision.

---

## Collections

| Collection | Contents |
|---|---|
| `vc_comps` | the benchmark corpus — both seeders write here |
| `vc_documents` | chunks of uploaded pitch decks and scraped reports |

Kept separate deliberately: mixing them means an uploaded deck is returned as a
"comparable deal" for the next upload, and a company gets benchmarked against
itself.

Both seeders embed with `gemini-embedding-001` at
`task_type=RETRIEVAL_DOCUMENT`; queries use `RETRIEVAL_QUERY`, since Gemini's
retrieval embeddings are asymmetric.

## Resetting

```bash
rm -rf data/chroma && python seed_edgar.py
```

That also drops the uploaded-document index. To clear only the comps:

```python
from tools.vector_store import comps_col
comps_col.delete(ids=comps_col.get()["ids"])
```

## Verifying

```python
from tools.vector_store import comps_col, query_comps

print(comps_col.count())
for r in query_comps("biotech seed stage therapeutics company", n=3):
    m = r["meta"]
    print(m["company_name"], m["sector"], m["stage"], m["amount_sold"])
```

Results come back in RRF-fused rank order, best match first.

## Not used, and why

| Source | Verdict |
|---|---|
| **Y Combinator directory** | `robots.txt` has `Disallow: /companies?*` — the query-string routes a crawler needs are explicitly disallowed. Not scraped. |
| **EDGAR S-1 filings** | Real financials, but only for companies at IPO scale — the wrong stage to benchmark a seed startup against. |
| **Crunchbase / Tracxn / VCCEdge** | Have exactly the round + ARR data we lack. All paid, none redistributable. |
