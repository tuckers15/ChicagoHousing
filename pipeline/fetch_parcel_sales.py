"""
fetch.py
--------
Data Acquisition
Pulls Cook County Assessor Parcel Sales data from the Cook County Open Data portal
via the Socrata SODA API, filtered to Chicago city townships and sales from 2021
onwards. Paginates in batches of 50,000 rows (SODA 2.1 max) and saves a raw
CSV backup before any transformation.

Dataset: Assessor - Parcel Sales
ID:      wvhk-k5uv
Portal:  datacatalog.cookcountyil.gov

Chicago city township codes (first two digits of PIN):
    70 - South Chicago / Calumet area (verify against portal)
    71 - Hyde Park
    72 - Lake
    73 - Lakeview
    74 - Jefferson
    75 - North Chicago
    76 - Rogers Park
    77 - West Chicago
"""

import os
import time
import logging
import pandas as pd
from sodapy import Socrata
from datetime import datetime

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
# Parcel Sales Dataset ID: wvhk-k5uv
# Parcel Universe Dataset ID: nj4t-kc8j


DOMAIN          = "datacatalog.cookcountyil.gov"
DATASET_ID      = "wvhk-k5uv"
APP_TOKEN       = None          # Replace with your app token to avoid throttling
                                # Get a free token at: https://datacatalog.cookcountyil.gov/profile/app_tokens

BATCH_SIZE      = 50_000        # Max rows per request on SODA 2.1 endpoints
DATE_FILTER     = "2021-01-01"  # Include sales on or after this date
OUTPUT_PATH     = "data/raw_parcel_sales.csv"
DRY_RUN         = False         # Set True to fetch one batch only (for verification)

# Chicago city township codes (township_code field in the dataset).
# These correspond to the 8 townships that make up the City of Chicago.
CHICAGO_TOWNSHIP_CODES = [70, 71, 72, 73, 74, 75, 76, 77]

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def build_where_clause(township_codes: list[int], date_filter: str) -> str:
    """
    Build the SODA $where clause to filter by Chicago township codes
    and sale date on or after date_filter (YYYY-MM-DD).

    sale_date in this dataset is stored as a human-readable string
    (e.g. "January 12 2023"), so we filter on the `year` integer column
    which is reliably numeric and fast to filter.
    """
    year = int(date_filter[:4])
    # codes_str = ", ".join(str(c) for c in township_codes)
    codes_str = ", ".join(f'"{c}"' for c in township_codes)
    where = (
        f"township_code in({codes_str}) "
        f"AND year >= {year}"
    )
    return where


def fetch_all_records(client: Socrata, where: str) -> pd.DataFrame:
    """
    Paginate through the full dataset using $limit + $offset and
    return a single combined DataFrame.
    """
    all_records = []
    offset = 0
    batch_num = 0

    while True:
        batch_num += 1
        log.info(f"Fetching batch {batch_num} (offset={offset:,}, limit={BATCH_SIZE:,})...")

        try:
            results = client.get(
                DATASET_ID,
                where=where,
                limit=BATCH_SIZE,
                offset=offset,
                order="row_id ASC",   # Stable ordering keeps pagination consistent
            )
        except Exception as e:
            log.error(f"API error on batch {batch_num}: {e}")
            raise

        if not results:
            log.info("Empty batch returned — pagination complete.")
            break

        batch_df = pd.DataFrame(results)
        all_records.append(batch_df)
        log.info(f"  → {len(batch_df):,} rows received (running total: {sum(len(d) for d in all_records):,})")

        if len(results) < BATCH_SIZE:
            # Last partial batch — no more pages
            log.info("Partial batch received — end of dataset reached.")
            break

        offset += BATCH_SIZE

        if DRY_RUN:
            log.info("DRY_RUN=True: stopping after first batch.")
            break

        # Brief pause to be a polite API citizen
        time.sleep(0.5)

    if not all_records:
        log.warning("No records returned. Check your WHERE clause and township codes.")
        return pd.DataFrame()

    combined = pd.concat(all_records, ignore_index=True)
    log.info(f"Total records fetched: {len(combined):,}")
    return combined


def save_raw(df: pd.DataFrame, path: str) -> None:
    """Save a raw CSV backup before any transformation."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    df.to_csv(path, index=False)
    log.info(f"Raw data saved to: {path}  ({os.path.getsize(path) / 1_048_576:.1f} MB)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    log.info("=== Phase 1: Data Acquisition ===")
    log.info(f"Dataset:          {DATASET_ID} on {DOMAIN}")
    log.info(f"Date filter:      sales from {DATE_FILTER} onwards (year >= {DATE_FILTER[:4]})")
    log.info(f"Township codes:   {CHICAGO_TOWNSHIP_CODES}")
    log.info(f"Batch size:       {BATCH_SIZE:,} rows")
    log.info(f"Dry run:          {DRY_RUN}")

    client = Socrata(DOMAIN, APP_TOKEN, timeout=60)

    where = build_where_clause(CHICAGO_TOWNSHIP_CODES, DATE_FILTER)
    log.info(f"WHERE clause:     {where}")

    df = fetch_all_records(client, where)

    if df.empty:
        log.error("No data fetched. Exiting.")
        return

    # -----------------------------------------------------------------------
    # Basic inspection before saving
    # -----------------------------------------------------------------------
    log.info("\n--- Dataset snapshot ---")
    log.info(f"Shape:      {df.shape[0]:,} rows × {df.shape[1]} columns")
    log.info(f"Columns:    {list(df.columns)}")
    log.info(f"Date range: {df['sale_date'].min()} → {df['sale_date'].max()}")
    log.info(f"Townships:  {sorted(df['township_code'].unique().tolist())}")
    log.info(f"Years:      {sorted(df['year'].unique().tolist())}")
    log.info(f"\nSample rows:\n{df.head(3).to_string()}")

    # -----------------------------------------------------------------------
    # Save raw backup
    # -----------------------------------------------------------------------
    save_raw(df, OUTPUT_PATH)
    log.info("Phase 1 complete.")


# ---------------------------------------------------------------------------
# Verification helper  (run this manually to confirm township codes)
# ---------------------------------------------------------------------------

def verify_township_codes():
    """
    Run this once to inspect what township_code values exist and cross-check
    them against known Chicago addresses. Fetches a small sample only.

    Usage:
        python fetch.py --verify
    """
    log.info("=== Township Code Verification ===")
    client = Socrata(DOMAIN, APP_TOKEN, timeout=60)

    # Pull a sample with NO township filter to see all codes present
    sample = client.get(DATASET_ID, limit=5000, offset=0, order="row_id DESC")
    df = pd.DataFrame(sample)

    log.info(f"Sample size: {len(df):,} rows")
    log.info("Unique township_code values and counts:")
    print(df["township_code"].value_counts().sort_index().to_string())

    log.info("\nSample of rows with township_code and PIN (first 2 digits = township):")
    df["pin_township"] = df["pin"].astype(str).str.zfill(14).str[:2]
    print(df[["pin", "pin_township", "township_code", "sale_date", "sale_price"]].head(20).to_string())


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--verify":
        verify_township_codes()
    else:
        main()