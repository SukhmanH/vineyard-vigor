"""One-off backfill: Sentinel-2 back to the start of the usable archive.

Queries from 2015 (Sentinel-2A launch); over the South Okanagan the
S2_SR_HARMONIZED collection effectively begins ~2017 and is thin through
2018 (why the analysis baselines start 2019 - that floor is unchanged).
Whatever exists is spliced into block_timeseries.parquet BEFORE 2019;
rows from 2019 onward are never touched.

Half-month windows with a retry, because wider interactive EE pulls trip
the "Too many concurrent aggregations" limit (the per-scene reductions in
one request run in parallel server-side). Re-runnable: completed years are
skipped, so a failed run resumes where it left off.

Run: uv run python scripts/backfill_s2.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vigor import extract, ingest  # noqa: E402

OUT = ROOT / "data" / "processed" / "block_timeseries.parquet"
QUERY_START_YEAR = 2015
SPLICE_BEFORE = "2019-01-01"


def _fetch_window(gdf, start: str, end: str) -> pd.DataFrame | None:
    """Fetch one window; on a stubborn "Too many concurrent aggregations"
    error, bisect. The concurrency EE objects to is the request's OWN
    per-scene reductions running in parallel, so a window with a dense
    granule stack fails deterministically no matter the backoff - only a
    smaller window (fewer scenes per request) gets through."""
    table = extract.timeseries_table(gdf, start_date=start, end_date=end)
    err = None
    for attempt in (1, 2, 3):
        try:
            raw = extract.fetch_table(table)
            return ingest.raw_to_timeseries(raw) if len(raw) else pd.DataFrame()
        except Exception as e:
            err = e
            if attempt < 3:
                wait = 60 * attempt
                print(f"  {start}..{end}: EE error ({e}); retrying in {wait}s...", flush=True)
                time.sleep(wait)
    s, t = pd.Timestamp(start), pd.Timestamp(end)
    if (t - s).days <= 4:
        print(f"  {start}..{end}: giving up this run ({err})", flush=True)
        return None
    mid = (s + (t - s) / 2).strftime("%Y-%m-%d")
    print(f"  {start}..{end}: still failing; bisecting at {mid}", flush=True)
    left = _fetch_window(gdf, start, mid)
    if left is None:
        return None
    time.sleep(10)
    right = _fetch_window(gdf, mid, end)
    if right is None:
        return None
    return pd.concat([left, right], ignore_index=True)


def _pull_year(gdf, year: int) -> pd.DataFrame | None:
    # Half-month windows (S2A+S2B in an orbit overlap can stack 10+ scenes
    # a month); _fetch_window bisects further wherever that is still dense.
    frames = []
    windows = []
    for m in range(1, 13):
        nxt = f"{year + 1}-01-01" if m == 12 else f"{year}-{m + 1:02d}-01"
        windows.append((f"{year}-{m:02d}-01", f"{year}-{m:02d}-15"))
        windows.append((f"{year}-{m:02d}-15", nxt))
    for q_start, q_end in windows:
        df = _fetch_window(gdf, q_start, q_end)
        if df is None:
            return None
        if len(df):
            frames.append(df)
        time.sleep(10)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def main() -> int:
    extract.init_ee()
    gdf = extract.load_blocks(ROOT / "data" / "blocks.geojson")

    old = ingest.load_timeseries(OUT)
    pre = old[old["date"] < pd.Timestamp(SPLICE_BEFORE)]
    have = set(pre["date"].dt.year.unique())

    incomplete = False
    for year in range(QUERY_START_YEAR, 2019):
        if year in have:
            print(f"{year}: already stored, skipping", flush=True)
            continue
        fresh = _pull_year(gdf, year)
        if fresh is None:
            # This session is throttled for good; a rerun resumes this year.
            print(f"{year}: incomplete; exiting so a fresh run can resume", flush=True)
            incomplete = True
            break
        fresh = fresh[fresh["date"] < pd.Timestamp(SPLICE_BEFORE)]
        print(f"{year}: {len(fresh)} block-scene rows", flush=True)
        if len(fresh):
            old = ingest.load_timeseries(OUT)
            merged = (
                pd.concat([old[old["date"].dt.year != year], fresh], ignore_index=True)
                .sort_values(["block_id", "date", "scene_id"])
                .reset_index(drop=True)
            )
            ingest.write_timeseries(merged, OUT)
        time.sleep(30)  # cool down between years; sustained pulls trip throttling

    merged = ingest.load_timeseries(OUT)
    q = merged[(merged["valid_frac"] >= 0.8) & merged["ndvi_median"].notna()]
    print(f"total {len(merged)} rows -> {OUT}")
    print("analysis-quality observations per year:")
    print(q.groupby(q["date"].dt.year).size().to_string())
    return 1 if incomplete else 0


if __name__ == "__main__":
    raise SystemExit(main())
