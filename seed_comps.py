"""
One-time seeding of the comparable-deals benchmark corpus.

Run:  python seed_comps.py

Writes into the `vc_comps` ChromaDB collection only. Uploaded pitch decks go to
`vc_documents` — keeping them apart is what stops an uploaded company from being
returned as its own comparable. See SEEDING.md.
"""
import os
import sys
from pathlib import Path

# Add project root to path if necessary
sys.path.insert(0, str(Path(__file__).parent.resolve()))

from loguru import logger

from tools.vector_store import comps_col, upsert_comp

# 15 highly realistic, representative startup deals spanning different sectors and stages
SAMPLE_COMPS = [
    {
        "id": "comp_1",
        "text": "SaaS startup offering collaborative design workspace. Raising $15M Series A. Currently has $3.2M ARR, growing 120% YoY. Burn rate is $150k monthly. Gross margins at 78%. Target market is product design teams and agency designers. Valuation is $65M post-money.",
        "meta": {
            "company_name": "FigmaClone",
            "sector": "SaaS",
            "stage": "series-a",
            "arr": 3200000,
            "burn_monthly": 150000,
            "valuation": 65000000,
            "business_model": "Subscription"
        }
    },
    {
        "id": "comp_2",
        "text": "AI startup developing proprietary LLMs optimized for legal contract analysis. Raising $8M Seed round. ARR is $500k from early design partners. Monthly burn is $80k. Key moat is proprietary fine-tuned models trained on private legal corpuses. Valuation is $35M pre-money.",
        "meta": {
            "company_name": "LexAI",
            "sector": "AI",
            "stage": "seed",
            "arr": 500000,
            "burn_monthly": 80000,
            "valuation": 35000000,
            "business_model": "Subscription"
        }
    },
    {
        "id": "comp_3",
        "text": "FinTech infrastructure platform providing cross-border payment APIs for Latin American businesses. Raising $25M Series B. Processing volume is $400M annualized. Net revenue is $8.5M ARR with 45% YoY growth. Burn rate is $250k monthly. Lead investor is Tiger Global.",
        "meta": {
            "company_name": "PayaLatam",
            "sector": "FinTech",
            "stage": "series-b",
            "arr": 8500000,
            "burn_monthly": 250000,
            "valuation": 120000000,
            "business_model": "Transaction Fee"
        }
    },
    {
        "id": "comp_4",
        "text": "Biotech platform using machine learning to accelerate lead discovery for small molecule drugs. Raising $12M Series A. Partnered with 3 major pharma companies. Headcount is 22. Monthly burn is $180k. Moat lies in its proprietary cell-imaging datasets.",
        "meta": {
            "company_name": "CellDiscovery",
            "sector": "Biotech",
            "stage": "series-a",
            "arr": 0,
            "burn_monthly": 180000,
            "valuation": 50000000,
            "business_model": "Licensing & Milestones"
        }
    },
    {
        "id": "comp_5",
        "text": "B2C marketplace for verified refurbished consumer electronics. Raising $20M Series B. Annual Gross Merchandise Value (GMV) is $80M. Net revenue is $12M ARR, growing 35% YoY. Cash balance is $15M with $400k monthly burn. Lead investor is General Catalyst.",
        "meta": {
            "company_name": "ReTech",
            "sector": "Consumer",
            "stage": "series-b",
            "arr": 12000000,
            "burn_monthly": 400000,
            "valuation": 95000000,
            "business_model": "Commission"
        }
    },
    {
        "id": "comp_6",
        "text": "Developer tool providing automated end-to-end security audits for GitHub repositories. Raising $4M Seed. Current ARR is $750k from 150 mid-market tech customers. Headcount is 8. Burn rate is $50k monthly. Moat is the speed of scanning and deep context rules.",
        "meta": {
            "company_name": "SecurePull",
            "sector": "SaaS",
            "stage": "seed",
            "arr": 750000,
            "burn_monthly": 50000,
            "valuation": 20000000,
            "business_model": "Subscription"
        }
    },
    {
        "id": "comp_7",
        "text": "Cybersecurity startup building decentralized identity management solutions for cloud infrastructure. Raising $10M Series A. Currently has $2.1M ARR. Monthly burn is $110k. Lead investor is Sequoia Capital. Growth is 90% YoY.",
        "meta": {
            "company_name": "CloudPass",
            "sector": "SaaS",
            "stage": "series-a",
            "arr": 2100000,
            "burn_monthly": 110000,
            "valuation": 45000000,
            "business_model": "Subscription"
        }
    },
    {
        "id": "comp_8",
        "text": "AI-powered customer support agent platform utilizing real-time agent assist and automated ticket resolution. Raising $15M Series A. Current ARR is $4.5M, growing 150% YoY. Monthly burn is $200k. Net negative churn is -5% annually.",
        "meta": {
            "company_name": "ResolveAI",
            "sector": "AI",
            "stage": "series-a",
            "arr": 4500000,
            "burn_monthly": 200000,
            "valuation": 80000000,
            "business_model": "Subscription"
        }
    },
    {
        "id": "comp_9",
        "text": "Neobank for small and medium-sized enterprises in Southeast Asia offering multi-currency cards and credit lines. Raising $30M Series B. Annual transaction volume is $1.2B. ARR is $18M with 80% YoY growth. Burn rate is $500k monthly. Backed by Y Combinator.",
        "meta": {
            "company_name": "SMEBank",
            "sector": "FinTech",
            "stage": "series-b",
            "arr": 18000000,
            "burn_monthly": 500000,
            "valuation": 180000000,
            "business_model": "Interchange & Interest"
        }
    },
    {
        "id": "comp_10",
        "text": "Biotech developer of gene editing therapies targeting rare inherited cardiovascular conditions. Raising $40M Series B. Pre-clinical stage with positive animal trial data. Burn rate is $900k monthly. Key IP is a patent-protected delivery vector.",
        "meta": {
            "company_name": "GeneHeart",
            "sector": "Biotech",
            "stage": "series-b",
            "arr": 0,
            "burn_monthly": 900000,
            "valuation": 160000000,
            "business_model": "Therapeutics Pipeline"
        }
    },
    {
        "id": "comp_11",
        "text": "B2C direct-to-consumer personalized nutrition subscription service using blood bio-markers. Raising $6M Seed. Active subscriber count is 15,000. ARR is $2.8M. Monthly burn is $90k. CAC is $45 with LTV of $300.",
        "meta": {
            "company_name": "NutriLife",
            "sector": "Consumer",
            "stage": "seed",
            "arr": 2800000,
            "burn_monthly": 90000,
            "valuation": 22000000,
            "business_model": "Subscription"
        }
    },
    {
        "id": "comp_12",
        "text": "EdTech platform using AI to auto-generate personalized practice problems and tests for K-12 students. Raising $3M Seed. ARR is $600k. Monthly burn is $40k. 300,000 active students. Growth is 15% month-over-month.",
        "meta": {
            "company_name": "MathGenius",
            "sector": "SaaS",
            "stage": "seed",
            "arr": 600000,
            "burn_monthly": 40000,
            "valuation": 15000000,
            "business_model": "Subscription"
        }
    },
    {
        "id": "comp_13",
        "text": "CleanTech hardware startup manufacturing smart building insulation panels that dynamically adjust thermal conductivity. Raising $18M Series B. Annual revenue is $5M. Gross margins are 38%. Monthly burn is $300k. Production facility has 10k units capacity.",
        "meta": {
            "company_name": "EcoTherm",
            "sector": "CleanTech",
            "stage": "series-b",
            "arr": 5000000,
            "burn_monthly": 300000,
            "valuation": 75000000,
            "business_model": "Hardware Sale"
        }
    },
    {
        "id": "comp_14",
        "text": "No-code workflow automation platform for warehouse logistics and inventory operations. Raising $12M Series A. Current ARR is $1.9M. Monthly burn is $130k. Growing 110% YoY. Integrates with SAP and NetSuite.",
        "meta": {
            "company_name": "FlowLog",
            "sector": "SaaS",
            "stage": "series-a",
            "arr": 1900000,
            "burn_monthly": 130000,
            "valuation": 40000000,
            "business_model": "Subscription"
        }
    },
    {
        "id": "comp_15",
        "text": "Decentralized automated market maker protocol and liquidity network on Solana. Raising $5M Seed. Daily trading volume is $12M. Protocol revenue is $2.5M annualized. Backed by top Solana ecosystem funds.",
        "meta": {
            "company_name": "SolSwap",
            "sector": "FinTech",
            "stage": "seed",
            "arr": 2500000,
            "burn_monthly": 60000,
            "valuation": 25000000,
            "business_model": "Protocol Fees"
        }
    }
]

def seed() -> int:
    """Upsert every sample comp. Idempotent — ids are stable, so re-running updates."""
    count_before = comps_col.count()
    logger.info(f"'{comps_col.name}' count before seeding: {count_before}")

    failures = 0
    for comp in SAMPLE_COMPS:
        try:
            upsert_comp(comp["id"], comp["text"], comp["meta"])
        except Exception as exc:
            failures += 1
            logger.error(f"Failed to upsert comp {comp['id']}: {exc}")

    count_after = comps_col.count()
    logger.success(
        f"Seeding complete. '{comps_col.name}' count: {count_after} "
        f"(+{count_after - count_before}, {failures} failure(s))"
    )
    return failures


if __name__ == "__main__":
    from config.settings import settings
    from tools.chroma_guard import ensure_exclusive_access

    # Writing to Chroma under a live server leaves it with a stale index.
    ensure_exclusive_access(force="--allow-running-api" in sys.argv)

    if not (settings.gemini_api_key or os.environ.get("GEMINI_API_KEY")):
        logger.error(
            "GEMINI_API_KEY is not set. Seeding needs it to generate embeddings."
        )
        sys.exit(1)

    sys.exit(1 if seed() else 0)
