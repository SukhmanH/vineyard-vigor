"""One-off backfill: ERA5-Land daily site weather, 2019 -> present, into
data/processed/site_weather.parquet.

Two sites x ~2700 days is a small table, but a single getInfo over the whole
range still trips EE limits, so it is pulled a year at a time. Re-runnable:
years already stored for every site are skipped.

Run: uv run python scripts/backfill_weather.py
"""

from __future__ import annotations

import datetime as dt
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vigor import extract, weather  # noqa: E402

OUT = ROOT / "data" / "processed" / "site_weather.parquet"


def main() -> int:
    extract.init_ee()
    gdf = extract.load_blocks()
    sites = set(gdf["site"].unique())
    print(f"{len(sites)} sites: {', '.join(sorted(sites))}", flush=True)

    existing = pd.read_parquet(OUT) if OUT.exists() else pd.DataFrame()
    this_year = dt.date.today().year

    for year in range(extract.WEATHER_START_YEAR, this_year + 1):
        if len(existing):
            have = existing[existing["date"].dt.year == year]
            if set(have["site"].unique()) >= sites and len(have) > 300:
                print(f"{year}: already stored, skipping", flush=True)
                continue

        end = f"{year + 1}-01-01"
        if year == this_year:
            end = (dt.date.today() + dt.timedelta(days=1)).isoformat()

        raw = extract.fetch_weather(
            extract.weather_table(gdf, start_date=f"{year}-01-01", end_date=end)
        )
        if not len(raw):
            print(f"{year}: no rows returned", flush=True)
            continue

        fresh = weather.raw_to_weather(raw)
        print(f"{year}: {len(fresh)} site-days", flush=True)

        keep = existing[existing["date"].dt.year != year] if len(existing) else existing
        existing = pd.concat([keep, fresh], ignore_index=True)
        existing = existing.sort_values(["site", "date"]).reset_index(drop=True)
        weather.write_weather(existing, OUT)
        time.sleep(5)

    print(f"\ntotal {len(existing)} rows -> {OUT}")
    print("\ncontinuity (gaps break the trailing windows):")
    print(weather.check_continuity(existing).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
