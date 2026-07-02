"""
fetch_parcel_universe.py
-------------------------

Pulls Cook County Assessor Parcel Universe data from the Cook County Open
Data portal via the Socrata SODA API, filtered to the City of Chicago.
"""

import os
import time
import logging
import pandas as pd
from sodapy import Socrata

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
# Parcel Sales Dataset ID:    wvhk-k5uv  (used in fetch.py)
# Parcel Universe Dataset ID: <FILL IN HERE>

DOMAIN          = "datacatalog.cookcountyil.gov"
DATASET_ID      = "pabr-t5kh"            # TODO: fill in the Parcel Universe dataset id
APP_TOKEN       = None          # Replace with your app token to avoid throttling
                                

BATCH_SIZE      = 50_000        # Max rows per request on SODA 2.1 endpoints
YEAR_FILTER     = None          # e.g. 2024 to pull a single tax year, or None for all years
                                 # Strongly recommended — Parcel Universe is a historic panel
                                 # (one row per PIN per year), so leaving this None on the full
                                 # historic dataset id will pull far more rows than you likely need.
OUTPUT_PATH     = "data/raw_parcel_universe.csv"
DRY_RUN         = False         # Set True to fetch one batch only (for verification)

# TODO: confirm this against --verify output. This is a placeholder guess —
# the real column is likely something like "mailing_municipality_name",
# "tax_municipality_name", or a spatial-join equivalent. Do not run a full
# production pull until this is confirmed.
# MUNICIPALITY_FIELD = "cook_municipality_name"
# MUNICIPALITY_VALUE = "City of Chicago"
MUNICIPALITY_FIELD = "triad_name"
MUNICIPALITY_VALUE = "City"


# Only pull the columns you actually need — Parcel Universe is wide (many
# characteristic/spatial columns), and at 50M+ rows, trimming columns
# server-side via $select meaningfully reduces payload size and memory.
# TODO: confirm exact field names via --verify, then uncomment.
SELECT_FIELDS = ",".join([
    "pin",
    "pin10",
    "year",
    "class",
    "township_code",
    "township_name",
    MUNICIPALITY_FIELD,
    "longitude",
    "latitude",
    "chicago_community_area_name",
    "centroid_x_crs_3435",
    "centroid_y_crs_3435"
])
SELECT_FIELDS = None  # None = fetch all columns (safe default until fields are confirmed)

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

def build_where_clause(municipality_field: str, municipality_value: str, year_filter: int | None) -> str:
    """
    Build the SODA $where clause to filter to a single municipality and
    (optionally) a single tax year.
    """
    where = f'{municipality_field} = "{municipality_value}"'
    if year_filter is not None:
        where += f" AND year = {year_filter}"
    return where


def fetch_all_records(client: Socrata, where: str, select: str | None) -> pd.DataFrame:
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
            kwargs = dict(
                where=where,
                limit=BATCH_SIZE,
                offset=offset,
                order="pin ASC",   # Stable ordering keeps pagination consistent
            )
            if select:
                kwargs["select"] = select

            results = client.get(DATASET_ID, **kwargs)
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
            log.info("Partial batch received — end of dataset reached.")
            break

        offset += BATCH_SIZE

        if DRY_RUN:
            log.info("DRY_RUN=True: stopping after first batch.")
            break

        # Brief pause to be a polite API citizen
        time.sleep(0.5)

    if not all_records:
        log.warning("No records returned. Check your WHERE clause and municipality field/value.")
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
    if not DATASET_ID:
        log.error("DATASET_ID is not set. Fill in the Parcel Universe dataset id before running.")
        return

    log.info("=== Phase 1: Data Acquisition (Parcel Universe) ===")
    log.info(f"Dataset:          {DATASET_ID} on {DOMAIN}")
    log.info(f"Municipality:     {MUNICIPALITY_FIELD} = '{MUNICIPALITY_VALUE}'")
    log.info(f"Year filter:      {YEAR_FILTER if YEAR_FILTER is not None else 'ALL YEARS (no filter)'}")
    log.info(f"Batch size:       {BATCH_SIZE:,} rows")
    log.info(f"Dry run:          {DRY_RUN}")

    client = Socrata(DOMAIN, APP_TOKEN, timeout=60)

    where = build_where_clause(MUNICIPALITY_FIELD, MUNICIPALITY_VALUE, YEAR_FILTER)
    log.info(f"WHERE clause:     {where}")

    df = fetch_all_records(client, where, SELECT_FIELDS)

    if df.empty:
        log.error("No data fetched. Exiting.")
        return

    # -----------------------------------------------------------------------
    # Basic inspection before saving
    # -----------------------------------------------------------------------
    log.info("\n--- Dataset snapshot ---")
    log.info(f"Shape:      {df.shape[0]:,} rows × {df.shape[1]} columns")
    log.info(f"Columns:    {list(df.columns)}")
    if "year" in df.columns:
        log.info(f"Years:      {sorted(df['year'].unique().tolist())}")
    if MUNICIPALITY_FIELD in df.columns:
        log.info(f"Municipalities present: {df[MUNICIPALITY_FIELD].unique().tolist()}")
    log.info(f"\nSample rows:\n{df.head(3).to_string()}")

    # -----------------------------------------------------------------------
    # Save raw backup
    # -----------------------------------------------------------------------
    save_raw(df, OUTPUT_PATH)
    log.info("Phase 1 complete.")


# ---------------------------------------------------------------------------
# Verification helper  (run this manually to confirm column names/values)
# ---------------------------------------------------------------------------

def verify_fields():
    """
    Run this once to inspect available columns and confirm the correct
    municipality field name and Chicago's exact value before a production run.

    Usage:
        python fetch_parcel_universe.py --verify
    """
    if not DATASET_ID:
        log.error("DATASET_ID is not set. Fill in the Parcel Universe dataset id before running.")
        return

    log.info("=== Parcel Universe Field Verification ===")
    client = Socrata(DOMAIN, APP_TOKEN, timeout=60)

    # Pull a small unfiltered sample to see all column names
    sample = client.get(DATASET_ID, limit=2000, offset=0)
    df = pd.DataFrame(sample)

    log.info(f"Sample size: {len(df):,} rows")
    log.info(f"All columns:\n{list(df.columns)}")

    # Look for likely municipality-related columns
    muni_candidates = [c for c in df.columns if "muni" in c.lower() or "city" in c.lower()]
    log.info(f"\nCandidate municipality columns: {muni_candidates}")
    for col in muni_candidates:
        log.info(f"\nUnique values in '{col}' (sample):")
        print(df[col].value_counts(dropna=False).head(20).to_string())

    # Look for lat/long and neighborhood-type columns too, since these
    # matter for the mapping/dashboard use case
    geo_candidates = [
        c for c in df.columns
        if any(k in c.lower() for k in ["lat", "lon", "community", "ward", "nbhd", "neighborhood", "centroid"])
    ]
    log.info(f"\nCandidate geo/neighborhood columns: {geo_candidates}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--verify":
        verify_fields()
    else:
        main()