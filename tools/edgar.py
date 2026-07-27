"""
SEC EDGAR Form D → comparable-deal records.

Form D is the notice filed for a Regulation D exempt offering — i.e. essentially
every US private round. The quarterly structured datasets give, per filing:
issuer name/location/year of incorporation, industry group, revenue band,
total offering amount, amount actually sold, and the related persons.

That is real money and real sectors, which is what the comps corpus needs. What
it does NOT give is ARR, burn or headcount — those are not public at scale for
private companies, so comps built from Form D carry round size and revenue band
instead, and the memo prompts simply see fewer metrics.

Dataset: https://www.sec.gov/files/structureddata/data/form-d-data-sets/{YYYY}q{N}_d.zip
(the older `/files/dera/...` path now 404s)

Everything in this module is pure — no network. Downloading lives in seed_edgar.py.
"""
import csv
import io
import re
import zipfile
from dataclasses import dataclass, field
from typing import Iterator

from loguru import logger

DATASET_URL = "https://www.sec.gov/files/structureddata/data/form-d-data-sets/{quarter}_d.zip"

# Form D INDUSTRYGROUPTYPE → our sector vocabulary.
# Deliberately an allowlist: a REIT or an oil-and-gas partnership is not a
# comparable deal for a startup, and including them poisons retrieval.
SECTOR_MAP = {
    "Other Technology": "Technology",
    "Computers": "Technology",
    "Telecommunications": "Telecom",
    "Business Services": "Business Services",
    "Biotechnology": "Biotech",
    "Pharmaceuticals": "Biotech",
    "Other Health Care": "HealthTech",
    "Hospitals and Physicians": "HealthTech",
    "Commercial Banking": "FinTech",
    "Investment Banking": "FinTech",
    "Other Banking and Financial Services": "FinTech",
    "Insurance": "InsurTech",
    "Retailing": "Consumer",
    "Restaurants": "Consumer",
    "Tourism and Travel Services": "Consumer",
    "Lodging and Conventions": "Consumer",
    "Other Travel": "Consumer",
    "Other Energy": "CleanTech",
    "Energy Conservation": "CleanTech",
    "Environmental Services": "CleanTech",
    "Manufacturing": "Industrials",
    "Construction": "Industrials",
    "Agriculture": "AgTech",
}

# Explicitly dropped: funds and real estate vehicles, which dominate Form D by
# volume (10,135 of 15,735 filings in 2026Q1 are Pooled Investment Fund alone).
EXCLUDED_INDUSTRIES = {
    "Pooled Investment Fund",
    "Investing",
    "REITS and Finance",
    "Other Real Estate",
    "Residential",
    "Commercial",
    "Oil and Gas",
    "Coal Mining",
    "Electric Utilities",
    "Airlines and Airports",
    "Other",
}

# Round-size → stage. A heuristic, not a disclosed field: Form D has no stage
# concept. Documented in SEEDING.md so the inference is never mistaken for fact.
STAGE_BANDS = [
    (1_000_000, "pre-seed"),
    (5_000_000, "seed"),
    (20_000_000, "series-a"),
    (60_000_000, "series-b"),
    (float("inf"), "growth"),
]

MIN_AMOUNT_SOLD = 250_000

_MONEY_RE = re.compile(r"^\d+$")


@dataclass
class Comp:
    """One comparable deal ready for the vector store."""

    id: str
    text: str
    meta: dict = field(default_factory=dict)


def parse_money(value: str | None) -> int | None:
    """Form D amounts are plain integers, but blanks and 'Indefinite' appear."""
    if not value:
        return None
    v = value.strip().replace(",", "").replace("$", "")
    if not _MONEY_RE.match(v):
        return None
    try:
        return int(v)
    except ValueError:
        return None


def infer_stage(amount_sold: int | None) -> str:
    """Map a raise size onto a venture stage label."""
    if amount_sold is None:
        return "unknown"
    for ceiling, label in STAGE_BANDS:
        if amount_sold < ceiling:
            return label
    return "growth"


def _fmt_money(amount: int | None) -> str | None:
    if amount is None:
        return None
    if amount >= 1_000_000_000:
        return f"${amount / 1_000_000_000:.2f}B".replace(".00B", "B")
    if amount >= 1_000_000:
        return f"${amount / 1_000_000:.1f}M".replace(".0M", "M")
    if amount >= 1_000:
        return f"${amount / 1_000:.0f}k"
    return f"${amount}"


def _clean_revenue(raw: str | None) -> str | None:
    """Drop the non-answers so they never reach the comp text."""
    if not raw:
        return None
    v = raw.strip()
    if v in ("", "Decline to Disclose", "Not Applicable"):
        return None
    return v


def is_venture_relevant(offering: dict) -> bool:
    """Filter a Form D offering down to plausible venture rounds."""
    industry = (offering.get("INDUSTRYGROUPTYPE") or "").strip()
    if industry in EXCLUDED_INDUSTRIES or industry not in SECTOR_MAP:
        return False
    if (offering.get("ISPOOLEDINVESTMENTFUNDTYPE") or "").strip().lower() in ("true", "1", "y"):
        return False
    amount = parse_money(offering.get("TOTALAMOUNTSOLD"))
    if amount is None or amount < MIN_AMOUNT_SOLD:
        return False
    return True


def compose_comp(issuer: dict, offering: dict, people: list[dict]) -> Comp | None:
    """Build one Comp from joined Form D rows, or None if it isn't usable."""
    name = (issuer.get("ENTITYNAME") or "").strip()
    accession = (offering.get("ACCESSIONNUMBER") or issuer.get("ACCESSIONNUMBER") or "").strip()
    if not name or not accession:
        return None

    industry = (offering.get("INDUSTRYGROUPTYPE") or "").strip()
    sector = SECTOR_MAP.get(industry)
    if not sector:
        return None

    sold = parse_money(offering.get("TOTALAMOUNTSOLD"))
    total = parse_money(offering.get("TOTALOFFERINGAMOUNT"))
    stage = infer_stage(sold)
    revenue = _clean_revenue(offering.get("REVENUERANGE"))

    city = (issuer.get("CITY") or "").strip().title()
    state = (issuer.get("STATEORCOUNTRYDESCRIPTION") or "").strip()
    location = ", ".join(p for p in (city, state) if p)
    year_inc = (issuer.get("YEAROFINC_VALUE_ENTERED") or "").strip()
    sale_date = (offering.get("SALE_DATE") or "").strip()

    exec_names = []
    for p in people[:4]:
        full = " ".join(
            part for part in ((p.get("FIRSTNAME") or "").strip(), (p.get("LASTNAME") or "").strip()) if part
        )
        if full:
            exec_names.append(full)

    # Prose, with the numbers inline — this string is what gets embedded and
    # BM25-indexed, so retrieval quality depends on it reading naturally.
    parts = [f"{name} is a {sector} company"]
    if location:
        parts.append(f"based in {location}")
    if year_inc:
        parts.append(f"incorporated in {year_inc}")
    sentence = " ".join(parts) + "."

    raise_bits = []
    if sold is not None:
        raise_bits.append(f"raised {_fmt_money(sold)}")
    if total is not None and total != sold:
        raise_bits.append(f"of a {_fmt_money(total)} Regulation D offering")
    else:
        raise_bits.append("in a Regulation D offering")
    if sale_date:
        raise_bits.append(f"with first sale on {sale_date}")
    sentence += " The company " + " ".join(raise_bits) + "."

    sentence += f" Estimated stage from round size: {stage}."
    if revenue:
        sentence += f" Reported revenue range: {revenue}."
    if exec_names:
        sentence += f" Key people: {', '.join(exec_names)}."
    sentence += f" Industry classification: {industry}. Source: SEC Form D filing {accession}."

    meta = {
        "company_name": name,
        "sector": sector,
        "stage": stage,
        "industry_group": industry,
        "amount_sold": sold if sold is not None else 0,
        "offering_amount": total if total is not None else 0,
        "source": "SEC Form D",
        "accession": accession,
        "cik": (issuer.get("CIK") or "").strip(),
    }
    if revenue:
        meta["revenue_range"] = revenue
    if location:
        meta["location"] = location
    if year_inc:
        meta["year_incorporated"] = year_inc
    if sale_date:
        meta["sale_date"] = sale_date

    return Comp(id=f"formd_{accession}", text=sentence, meta=meta)


def _read_tsv(zf: zipfile.ZipFile, quarter_dir: str, filename: str) -> Iterator[dict]:
    """Stream one TSV out of the Form D archive."""
    path = f"{quarter_dir}/{filename}"
    with zf.open(path) as fh:
        text = io.TextIOWrapper(fh, encoding="utf-8", errors="replace")
        # These files are tab-separated with unquoted fields containing quotes.
        for row in csv.DictReader(text, delimiter="\t", quoting=csv.QUOTE_NONE):
            yield row


def extract_comps(zip_bytes: bytes, limit: int | None = None) -> list[Comp]:
    """Parse a Form D quarterly archive into venture-relevant Comp records."""
    comps: list[Comp] = []

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        quarter_dir = next(
            (n.split("/")[0] for n in names if n.endswith("OFFERING.tsv")), None
        )
        if quarter_dir is None:
            raise ValueError("OFFERING.tsv not found in archive")

        offerings = {
            r["ACCESSIONNUMBER"]: r
            for r in _read_tsv(zf, quarter_dir, "OFFERING.tsv")
            if r.get("ACCESSIONNUMBER") and is_venture_relevant(r)
        }
        logger.info(f"{len(offerings)} venture-relevant offerings in {quarter_dir}")
        if not offerings:
            return []

        issuers: dict[str, dict] = {}
        for r in _read_tsv(zf, quarter_dir, "ISSUERS.tsv"):
            acc = r.get("ACCESSIONNUMBER")
            if acc not in offerings:
                continue
            # Keep the primary issuer when the filing lists several.
            if acc not in issuers or (r.get("IS_PRIMARYISSUER_FLAG") or "").strip().lower() == "true":
                issuers[acc] = r

        people: dict[str, list[dict]] = {}
        for r in _read_tsv(zf, quarter_dir, "RELATEDPERSONS.tsv"):
            acc = r.get("ACCESSIONNUMBER")
            if acc in offerings:
                people.setdefault(acc, []).append(r)

    for acc, offering in offerings.items():
        issuer = issuers.get(acc)
        if not issuer:
            continue
        comp = compose_comp(issuer, offering, people.get(acc, []))
        if comp:
            comps.append(comp)
        if limit and len(comps) >= limit:
            break

    logger.success(f"Composed {len(comps)} comps from Form D archive.")
    return comps


def recent_quarters(count: int, latest_year: int, latest_q: int) -> list[str]:
    """Return the `count` most recent quarter identifiers, newest first."""
    out = []
    y, q = latest_year, latest_q
    for _ in range(count):
        out.append(f"{y}q{q}")
        q -= 1
        if q == 0:
            q = 4
            y -= 1
    return out
