"""
Deterministic financial ratio calculations.

Pure Python arithmetic — this module must never call an LLM. Every ratio
returns None rather than a guess when its inputs are missing or degenerate.
"""
import re

from loguru import logger

RAW_KEYS = ("arr", "prev_arr", "burn", "cash", "headcount", "revenue", "cogs")

MONTHS_PER_YEAR = 12

_SUFFIXES = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000, "bn": 1_000_000_000}

# e.g. "$1.2M", "(500,000)", "78%", "3.5 bn"
_NUM_RE = re.compile(r"^-?\d*\.?\d+$")


def parse_number(val) -> float | None:
    """Coerce a model-supplied value into a float.

    Gemini routinely emits "$5M", "1.2 bn", "78%" or "(500,000)" for negatives,
    all of which float() rejects. Returning None for those silently zeroed out
    every downstream ratio, so parse them explicitly.
    """
    if val is None:
        return None
    if isinstance(val, bool):  # bool is an int subclass; never a financial figure
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if not isinstance(val, str):
        return None

    s = val.strip().lower()
    if not s:
        return None

    # Accounting negatives: (1,234) means -1234
    negative = s.startswith("(") and s.endswith(")")
    if negative:
        s = s[1:-1].strip()

    if s.startswith("-"):
        negative = True
        s = s[1:].strip()

    s = s.replace("$", "").replace("€", "").replace("£", "").replace(",", "").replace("_", "")
    s = s.rstrip("%").strip()

    multiplier = 1
    for suffix, factor in sorted(_SUFFIXES.items(), key=lambda kv: -len(kv[0])):
        if s.endswith(suffix):
            candidate = s[: -len(suffix)].strip()
            if _NUM_RE.match(candidate):
                s, multiplier = candidate, factor
                break

    if not _NUM_RE.match(s):
        logger.debug(f"Could not parse numeric value: {val!r}")
        return None

    try:
        return (-1 if negative else 1) * float(s) * multiplier
    except ValueError:
        return None


def _safe_div(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def compute_ratios(raw: dict) -> dict:
    """
    Compute financial ratios deterministically.

    Expected raw keys: arr, prev_arr, burn (MONTHLY net burn), cash, headcount,
    revenue, cogs. Returns a dict of metrics, each None when uncomputable.
    """
    p = {k: parse_number(raw.get(k)) for k in RAW_KEYS}

    arr, prev_arr, burn = p["arr"], p["prev_arr"], p["burn"]

    # Burn Multiple = net burn / net new ARR, over the SAME period.
    # `burn` is monthly and ARR is annual, so annualize the burn before dividing —
    # comparing monthly burn to an annual ARR delta understates it ~12x.
    net_new_arr = None
    if arr is not None:
        net_new_arr = arr - (prev_arr if prev_arr is not None else 0.0)

    annual_burn = burn * MONTHS_PER_YEAR if burn is not None else None
    burn_multiple = _safe_div(annual_burn, net_new_arr)
    # A negative burn multiple (ARR shrank) is real information, but a positive
    # value computed from shrinking ARR would be misleading, so keep the sign.

    r = {
        "burn_multiple": round(burn_multiple, 2) if burn_multiple is not None else None,
        "runway_months": None,
        "yoy_growth": None,
        "gross_margin": None,
        "arr_per_head": None,
        "net_new_arr": round(net_new_arr, 2) if net_new_arr is not None else None,
        "annual_burn": round(annual_burn, 2) if annual_burn is not None else None,
    }

    runway = _safe_div(p["cash"], burn)
    r["runway_months"] = round(runway, 1) if runway is not None else None

    if arr is not None and prev_arr:  # prev_arr must be non-zero and non-None
        r["yoy_growth"] = round(((arr - prev_arr) / prev_arr) * 100, 2)

    revenue = p["revenue"]
    if revenue:  # non-zero, non-None
        cogs = p["cogs"] if p["cogs"] is not None else 0.0
        r["gross_margin"] = round(((revenue - cogs) / revenue) * 100, 2)

    arr_per_head = _safe_div(arr, p["headcount"])
    r["arr_per_head"] = round(arr_per_head, 2) if arr_per_head is not None else None

    return r
