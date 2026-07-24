"""Weekly refresh (Phase 6 automation): new scenes -> parquets -> dashboard -> website.

Steps, each skippable:
1. extract   - re-pull the current calendar year for all blocks in one getInfo
               (a year of 2 blocks is a few hundred rows, well under the ~3000-row
               getInfo comfort zone) and splice it into block_timeseries.parquet.
               Prior years are immutable and never re-fetched.
2. derive    - rebuild season_features, vigor_alerts, and (once a season has
               fully ended) vigor_zones from the parquet. Pure offline pandas.
3. dashboard - rebuild outputs/dashboard/index.html via vigor.webdash.
4. publish   - shallow-clone the website repo, and if the dashboard's data
               payload actually changed (the generated-at timestamp is ignored),
               copy the page to public/vigor/index.html, commit, and push main.
               Cloudflare Pages deploys the site from main automatically.

Run manually:
    PYTHONPATH=src uv run python scripts/weekly_update.py [--no-extract]
        [--no-publish] [--force-publish]

Scheduled: scripts/weekly_update.cmd (Windows Task Scheduler, weekly), which
appends stdout/stderr to outputs/logs/weekly_update.log.
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

PROCESSED = ROOT / "data" / "processed"
BLOCKS = ROOT / "data" / "blocks.geojson"
DASH = ROOT / "outputs" / "dashboard" / "index.html"

SITE_REPO = "https://github.com/SukhmanH/hbwebsite"
SITE_PAGE = "public/vigor/index.html"

_DATA_RE = re.compile(r"const DATA = (\{.*?\});\n")


def log(msg: str) -> None:
    print(f"[{dt.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


OVERLAP_DAYS = 5  # re-pull a little history so a late-arriving scene is never missed


def refresh_timeseries() -> None:
    """Extract scenes since the last stored observation and splice them in.

    The window is deliberately short (days, not the whole year): a year-wide
    interactive pull fans out across ~70 scenes and trips EE's "Too many
    concurrent aggregations" limit. Rows inside the re-pulled window are
    replaced wholesale, so the overlap never duplicates observations.
    """
    import time

    import ee

    from vigor import extract, ingest

    extract.init_ee()
    gdf = extract.load_blocks(BLOCKS)

    path = PROCESSED / "block_timeseries.parquet"
    old = ingest.load_timeseries(path)
    prev_max = old["date"].max()
    start = (prev_max - pd.Timedelta(days=OVERLAP_DAYS)).date().isoformat()

    log(f"extracting scenes from {start} for {len(gdf)} blocks from Earth Engine...")
    table = extract.timeseries_table(gdf, start_date=start)
    for attempt in (1, 2, 3):
        try:
            raw = extract.fetch_table(table)
            break
        except ee.EEException as e:
            if attempt == 3 or "concurrent aggregations" not in str(e).lower():
                raise
            log(f"  EE busy ({e}); retrying in 60s...")
            time.sleep(60)

    if raw.empty:
        log("timeseries: no scenes in the window yet, parquet unchanged")
        return
    fresh = ingest.raw_to_timeseries(raw)
    merged = pd.concat([old[old["date"] < pd.Timestamp(start)], fresh], ignore_index=True)
    merged = merged.sort_values(["block_id", "date", "scene_id"]).reset_index(drop=True)
    ingest.write_timeseries(merged, path)

    n_new = int((fresh["date"] > prev_max).sum())
    log(f"timeseries: {len(merged)} rows total, {n_new} observations newer than {prev_max:%Y-%m-%d}")

    # Landsat long-term history: same incremental splice, 16-day revisit so
    # many weeks add nothing. Created by scripts/backfill_landsat.py; skipped
    # here until that has run once.
    ls_path = PROCESSED / "landsat_timeseries.parquet"
    if ls_path.exists():
        ls_old = ingest.load_timeseries(ls_path)
        ls_start = (ls_old["date"].max() - pd.Timedelta(days=16)).date().isoformat()
        ls_raw = extract.fetch_table(extract.landsat_timeseries_table(gdf, start_date=ls_start))
        if len(ls_raw):
            ls_fresh = ingest.raw_to_timeseries(ls_raw)
            ls_merged = pd.concat(
                [ls_old[ls_old["date"] < pd.Timestamp(ls_start)], ls_fresh], ignore_index=True
            ).sort_values(["block_id", "date", "scene_id"]).reset_index(drop=True)
            ingest.write_timeseries(ls_merged, ls_path)
            log(f"landsat: {len(ls_merged)} rows total after refresh from {ls_start}")
        else:
            log("landsat: no new scenes in the window")


def refresh_zones_if_season_done(ts: pd.DataFrame) -> None:
    """Zone any fully-ended season that isn't in the zones parquet yet.

    Zoning needs every Apr-Oct month band, so a season can only be zoned from
    November onward; mid-season the current year is left alone (this mirrors
    the existing parquet, which carries completed seasons only). Requires EE.
    """
    from vigor import extract, zones

    today = dt.date.today()
    last_complete = today.year if today.month >= 11 else today.year - 1
    path = PROCESSED / "vigor_zones.parquet"
    existing = pd.read_parquet(path) if path.exists() else pd.DataFrame(columns=["year"])
    have = set(existing["year"].unique())
    missing = [y for y in range(2019, last_complete + 1) if y not in have]
    if not missing:
        return

    gdf = extract.load_blocks(BLOCKS)
    for y in missing:
        log(f"zoning completed season {y}...")
        pixels = extract.fetch_pixels(extract.sample_seasonal_profiles(gdf, y))
        zoned = zones.zone_all(pixels)
        if zoned.empty:
            log(f"  season {y}: no zonable pixels, skipped")
            continue
        existing = pd.concat([existing, zoned], ignore_index=True)
    zones.write_zones(existing.sort_values(["block_id", "year"]).reset_index(drop=True), path)


def refresh_derived(with_ee: bool) -> None:
    """Rebuild features and alerts (offline); zones too when EE is allowed."""
    import geopandas as gpd

    from vigor import clean, features, ingest, vigor_alerts

    ts = ingest.load_timeseries(PROCESSED / "block_timeseries.parquet")

    _, smoothed = clean.clean_and_smooth(ts)
    feats = features.seasonal_features(smoothed)
    features.write_features(feats, PROCESSED / "season_features.parquet")
    log(f"features: {len(feats)} block-seasons")

    meta = gpd.read_file(BLOCKS)
    meta.columns = meta.columns.str.strip()
    bs = {}
    if "baseline_start" in meta.columns:
        bs = {r.block_id: int(r.baseline_start) for r in meta.itertuples()
              if not pd.isna(r.baseline_start)}
    alerts = vigor_alerts.below_baseline_seasons(ts, baseline_start=bs)
    vigor_alerts.write_alerts(alerts, PROCESSED / "vigor_alerts.parquet")
    n_low = int(alerts["below_baseline"].sum())
    log(f"alerts: {len(alerts)} judged observations, {n_low} below baseline")

    if with_ee:
        refresh_zones_if_season_done(ts)

    # ML layer: season outlook (GP projection) + analog seasons. Offline.
    from vigor import ml

    band, summary = ml.season_outlook(ts, baseline_start=bs)
    an = ml.analog_seasons(ts)
    ml.write_outlook(band, summary, an, PROCESSED)
    log(f"ml: outlook for {summary['block_id'].nunique() if len(summary) else 0} blocks, "
        f"{len(an)} analog rankings")


def rebuild_dashboard() -> None:
    from vigor.webdash import build_dashboard

    out = build_dashboard(PROCESSED, BLOCKS, DASH.parent)
    log(f"dashboard rebuilt -> {out}")


def _payload_without_timestamp(html: str) -> str | None:
    m = _DATA_RE.search(html)
    if not m:
        return None
    return re.sub(r'"generated":"[^"]*"', '"generated":""', m.group(1))


def _git(args: list[str], cwd: Path) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)
    return r.stdout.strip()


def publish(force: bool) -> None:
    """Push the rebuilt page to the website repo when its data changed."""
    new_html = DASH.read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="hbwebsite-") as td:
        clone = Path(td) / "hbwebsite"
        _git(["clone", "--depth", "1", SITE_REPO, str(clone)], Path(td))
        page = clone / SITE_PAGE

        old_payload = _payload_without_timestamp(page.read_text(encoding="utf-8")) if page.exists() else None
        new_payload = _payload_without_timestamp(new_html)
        if not force and old_payload == new_payload:
            log("publish: dashboard data unchanged, nothing to push")
            return

        page.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(DASH, page)
        _git(["add", SITE_PAGE], clone)
        data_to = re.search(r'"latest_obs":"([^"]*)"', new_html)
        msg = (f"Refresh vigor dashboard (data to {data_to.group(1) if data_to else 'n/a'})\n\n"
               "Automated weekly update from the vineyard-vigor pipeline.\n\n"
               "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>")
        _git(["commit", "-m", msg], clone)
        _git(["push", "origin", "HEAD:main"], clone)
        log("publish: pushed to main; Cloudflare Pages will redeploy /vigor/")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--no-extract", action="store_true",
                    help="skip Earth Engine; rebuild from the existing parquets")
    ap.add_argument("--no-publish", action="store_true",
                    help="rebuild locally but do not touch the website repo")
    ap.add_argument("--force-publish", action="store_true",
                    help="push even when the data payload is unchanged")
    args = ap.parse_args()

    log("weekly update starting")
    try:
        if not args.no_extract:
            refresh_timeseries()
        refresh_derived(with_ee=not args.no_extract)
        rebuild_dashboard()
        if not args.no_publish:
            publish(force=args.force_publish)
    except subprocess.CalledProcessError as e:
        log(f"FAILED: git {' '.join(e.cmd[1:])}: {e.stderr.strip()}")
        return 1
    except Exception as e:  # a scheduled run must log, not die silently
        log(f"FAILED: {type(e).__name__}: {e}")
        return 1
    log("weekly update done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
