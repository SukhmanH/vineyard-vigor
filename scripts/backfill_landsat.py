"""One-off backfill: Landsat 8/9 block NDVI, 2014 -> present, into
data/processed/landsat_timeseries.parquet (same contract as the S2 parquet;
ndre_median is NaN - Landsat has no red-edge band).

Pulled in month-sized windows with a retry, because wider interactive EE
requests trip the "Too many concurrent aggregations" limit. Re-runnable:
completed years are skipped, so a failed run resumes where it left off.

Run: uv run python scripts/backfill_landsat.py
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

OUT = ROOT / "data" / "processed" / "landsat_timeseries.parquet"


def _pull_year(gdf, year: int) -> pd.DataFrame | None:
    """One year in MONTH-sized windows with patient backoff. Even a quarter
    of scenes x blocks can brush EE's ~20-concurrent-aggregations limit (the
    per-scene reductions inside one request run in parallel server-side), so
    quarter pulls fail whenever the scheduler is busy; a month stays far
    under it."""
    frames = []
    months = [(f"{year}-{m:02d}-01",
               f"{year + 1}-01-01" if m == 12 else f"{year}-{m + 1:02d}-01")
              for m in range(1, 13)]
    for q_start, q_end in months:
        table = extract.landsat_timeseries_table(gdf, start_date=q_start, end_date=q_end)
        for attempt in (1, 2, 3, 4, 5):
            try:
                raw = extract.fetch_table(table)
                break
            except Exception as e:
                if attempt == 5:
                    print(f"  {q_start}: giving up this run ({e})", flush=True)
                    return None
                wait = 90 * attempt
                print(f"  {q_start}: EE error ({e}); retrying in {wait}s...", flush=True)
                time.sleep(wait)
        if len(raw):
            frames.append(ingest.raw_to_timeseries(raw))
        time.sleep(10)  # be polite between aggregation requests
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _splice_year(fresh: pd.DataFrame, year: int) -> None:
    old = ingest.load_timeseries(OUT) if OUT.exists() else fresh.iloc[0:0]
    keep = old[old["date"].dt.year != year]
    merged = (
        pd.concat([keep, fresh], ignore_index=True)
        .sort_values(["block_id", "date", "scene_id"])
        .reset_index(drop=True)
    )
    ingest.write_timeseries(merged, OUT)


def main() -> int:
    extract.init_ee()
    gdf = extract.load_blocks(ROOT / "data" / "blocks.geojson")
    this_year = dt.date.today().year

    have = set()
    if OUT.exists():
        have = set(ingest.load_timeseries(OUT)["date"].dt.year.unique())

    incomplete = False
    for year in range(extract.LANDSAT_START_YEAR, this_year + 1):
        if year in have and year != this_year:
            print(f"{year}: already stored, skipping", flush=True)
            continue
        fresh = _pull_year(gdf, year)
        if fresh is None:
            incomplete = True
            continue  # resumable: rerun picks this year up again
        if len(fresh):
            _splice_year(fresh, year)
        print(f"{year}: {len(fresh)} block-scene rows", flush=True)
        time.sleep(30)  # cool down between years; sustained pulls trip throttling

    if not OUT.exists():
        print("no Landsat rows at all - nothing written")
        return 1
    merged = ingest.load_timeseries(OUT)
    q = merged[(merged["valid_frac"] >= 0.6) & merged["ndvi_median"].notna()]
    print(f"total {len(merged)} rows ({len(q)} analysis-quality) -> {OUT}")
    print(q.groupby(q["date"].dt.year).size().to_string())
    return 1 if incomplete else 0


if __name__ == "__main__":
    raise SystemExit(main())
