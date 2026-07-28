# Sample VC documents

Six synthetic documents for exercising RAG chat before you have a library of
your own. Load them all with:

```bash
python seed_library.py
```

Or upload any of them by hand under **RAG Chat → Sources → Add VC documents**.

## Every company here is fictional

Northwind Robotics, LedgerLoop, Cellulon Bio, Harbor Lane Ventures and everyone
named in these files are invented. The numbers are plausible but made up.

That is deliberate. Real pitch decks are confidential or copyrighted, and the
ones that do circulate publicly are mostly a decade old — a 2014 Series A deck
would teach the retriever the wrong benchmarks for today's market. These are
written to be internally consistent instead: LedgerLoop's burn multiple really
does work out to 1.6×, and Northwind's runway really is 19 months at the stated
burn, so answers you get from chat can be checked by hand.

They are **not** a benchmark corpus. Comparable-deal retrieval runs against 232
real SEC Form D filings in the separate `vc_comps` collection — see
[SEEDING.md](../SEEDING.md). These live in `vc_documents` alongside researched
Dex entries, and only chat reads them.

## What's here

| File | Type | Useful for asking about |
|---|---|---|
| `pitch-deck-northwind-robotics.md` | Series A deck | unit economics, hardware margins, pilot conversion |
| `pitch-deck-ledgerloop.md` | Seed deck | burn multiple, net revenue retention, embedded payments |
| `pitch-deck-cellulon-bio.md` | Series B deck | milestone-based tranches, clinical risk, non-dilutive funding |
| `term-sheet-series-a.md` | Term sheet | liquidation preference, pro-rata, protective provisions |
| `diligence-checklist.md` | Process doc | what to ask for at each stage |
| `lp-update-q2.md` | LP letter | TVPI/DPI, reserve strategy, mark-up policy |

The term sheet reflects standard market terms (1× non-participating preferred,
broad-based weighted-average anti-dilution). It is illustrative, not legal
advice, and is not a substitute for the NVCA model documents.
