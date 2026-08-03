"""Backfill Sentinel-2 from 2019 to the current year.

backfill_s2.py deliberately stops at 2019 (it only splices the thin
pre-2019 archive in underneath), and weekly_update.py only refreshes the
current calendar year. Neither builds 2019..now from scratch, which is what
a newly drawn set of blocks needs.

Reuses backfill_s2._pull_year, so the half-month windowing, retry and
bisection behaviour around EE's concurrent-aggregation limit is identical.
Re-runnable: years already present in the parquet are skipped, so a
throttled run resumes where it left off.

Run: uv run python scripts/backfill_s2_recent.py
"""

from __future__ import annotations

import datetime as dt
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vigor import extract, ingest  # noqa: E402

from backfill_s2 import _pull_year  # noqa: E402

OUT = ROOT / "data" / "processed" / "block_timeseries.parquet"
START_YEAR = 2019


def main() -> int:
    extract.init_ee()
    gdf = extract.load_blocks()
    print(f"{len(gdf)} blocks: {', '.join(gdf['block_id'])}", flush=True)

    this_year = dt.date.today().year
    incomplete = False

    for year in range(START_YEAR, this_year + 1):
        old = ingest.load_timeseries(OUT)
        if len(old):
            have = set(old.loc[old["date"].dt.year == year, "block_id"].unique())
            if have >= set(gdf["block_id"]):
                print(f"{year}: already stored for all blocks, skipping", flush=True)
                continue

        fresh = _pull_year(gdf, year)
        if fresh is None:
            print(f"{year}: incomplete; exiting so a fresh run can resume", flush=True)
            incomplete = True
            break

        print(f"{year}: {len(fresh)} block-scene rows", flush=True)
        if len(fresh):
            old = ingest.load_timeseries(OUT)
            keep = old[old["date"].dt.year != year] if len(old) else old
            merged = (
                pd.concat([keep, fresh], ignore_index=True)
                .sort_values(["block_id", "date", "scene_id"])
                .reset_index(drop=True)
            )
            ingest.write_timeseries(merged, OUT)
        time.sleep(30)  # cool down between years

    merged = ingest.load_timeseries(OUT)
    print(f"total {len(merged)} rows -> {OUT}")
    if len(merged):
        q = merged[(merged["valid_frac"] >= 0.8) & merged["ndvi_median"].notna()]
        print("analysis-quality observations per year:")
        print(q.groupby(q["date"].dt.year).size().to_string())
    return 1 if incomplete else 0


if __name__ == "__main__":
    raise SystemExit(main())
