"""Interactive HTML vigor dashboard (Phase 6, dashboard only - no scheduling).

Pure pandas/geopandas; runs offline. Reads the processed parquets and
blocks.geojson, serializes them to JSON, and writes ONE self-contained HTML
file to outputs/dashboard/ whose charts are live SVG (hand-rolled vanilla JS,
no external hosts, no server): hover readouts of the exact NDVI on any date,
per-year toggles, a season comparator, vigor-zone maps, and grower KPIs.

Grower-facing views on top of the raw curves:
- a season triage panel (active low-vigor runs, the weather-vs-single-block
  reading, and the historical stress log),
- per-block overview cards with status and a current-season sparkline,
- NDRE (canopy chlorophyll) alongside NDVI,
- a cross-block current-season comparator,
- CSV export of the features table and every flagged observation.

Everything the tooltips reveal is also reachable statically (the features
table, the flag list), per the dataviz "tooltips enhance, never gate" rule.

Regenerate any time with `python -m vigor.webdash` after refreshing the
parquets - the manual stand-in for the weekly scheduled run, which is
intentionally not built here.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd

from .clean import clean_and_smooth
from .vigor_alerts import stress_events
from ._webassets import render_page

SEASON_START_MONTH = 4
SEASON_END_MONTH = 10
MIN_VALID_FRAC = 0.8
BASELINE_FLOOR_YEAR = 2019


def _load(path: Path) -> pd.DataFrame | None:
    return pd.read_parquet(path) if path.exists() else None


def _block_meta(gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    gdf = gdf.copy()
    gdf.columns = gdf.columns.str.strip()
    cols = [c for c in ["block_id", "site", "variety", "planting_year", "baseline_start"]
            if c in gdf.columns]
    return pd.DataFrame(gdf[cols])


def _outlines_json(gdf: gpd.GeoDataFrame) -> dict:
    """Per block: exterior ring(s) in WGS84 as [[lon, lat], ...] lists, so the
    zone maps can draw the real planted boundary behind the pixels."""
    out: dict[str, list] = {}
    for _, row in gdf.iterrows():
        geom = row.geometry
        if geom is None:
            continue
        polys = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
        rings = []
        for p in polys:
            if p.geom_type != "Polygon":
                continue
            rings.append([[round(x, 6), round(y, 6)] for x, y in p.exterior.coords])
        if rings:
            out[str(row["block_id"])] = rings
    return out


def _quality(ts: pd.DataFrame) -> pd.DataFrame:
    """Analysis-quality in-season observations."""
    df = ts.dropna(subset=["ndvi_median"]).copy()
    df = df[df["valid_frac"] >= MIN_VALID_FRAC]
    m = df["date"].dt.month
    df = df[(m >= SEASON_START_MONTH) & (m <= SEASON_END_MONTH)]
    df["year"] = df["date"].dt.year
    df["doy"] = df["date"].dt.dayofyear
    return df.sort_values(["block_id", "date"])


def _smoothed_json(ts: pd.DataFrame, value_col: str, step: int = 3) -> dict:
    """Per block per year: the cleaned seasonal curve as [doy, value, iso_date].

    Raw scene readings spike on residual cloud/smoke the mask misses, which
    reads as vine stress that never happened. So the overlay charts show the
    Phase 3 pipeline instead: outlier screen, then Savitzky-Golay smoothing,
    downsampled to every `step` days. Exact scene readings remain reachable in
    the baseline chart and the CSV export. NDRE is smoothed by feeding it
    through the same pipeline in place of the NDVI column."""
    df = ts.copy()
    if value_col != "ndvi_median":
        df["ndvi_median"] = df[value_col]
    _, smoothed = clean_and_smooth(df)

    out: dict[str, dict[str, list]] = {}
    for block_id, g in smoothed.groupby("block_id"):
        seasons: dict[str, list] = {}
        for year, gy in g.groupby("year"):
            gy = gy.sort_values("doy")
            keep = gy.iloc[::step]
            if len(gy) and gy.index[-1] not in keep.index:
                keep = pd.concat([keep, gy.iloc[[-1]]])
            seasons[str(int(year))] = [
                [int(d), round(float(v), 4), ts_date.strftime("%Y-%m-%d")]
                for d, v, ts_date in zip(keep["doy"], keep["ndvi_smooth"], keep["date"])
            ]
        out[block_id] = seasons
    return out


def _baseline_json(al: pd.DataFrame | None) -> dict:
    """Per block per year: observations with baseline band + below-baseline
    marks, for the current-season-vs-baseline view."""
    if al is None:
        return {}
    out: dict[str, dict[str, dict]] = {}
    for block_id, g in al.groupby("block_id"):
        years: dict[str, dict] = {}
        for year, gy in g.groupby("year"):
            gy = gy.sort_values("doy")
            has_base = gy["base_p10"].notna()
            years[str(int(year))] = {
                "obs": [
                    [int(d), round(float(v), 4), iso.strftime("%Y-%m-%d"), bool(f)]
                    for d, v, iso, f in zip(gy["doy"], gy["ndvi"], gy["date"], gy["below_baseline"])
                ],
                "base": [
                    [int(d), round(float(p10), 4), round(float(p25), 4),
                     round(float(med), 4), round(float(p75), 4)]
                    for d, p10, p25, med, p75 in zip(
                        gy.loc[has_base, "doy"], gy.loc[has_base, "base_p10"],
                        gy.loc[has_base, "base_p25"], gy.loc[has_base, "base_median"],
                        gy.loc[has_base, "base_p75"],
                    )
                ],
            }
        out[block_id] = years
    return out


def _zones_json(z: pd.DataFrame | None) -> dict:
    """Per block per year: pixel points [lon, lat, zone, mean_ndvi]."""
    if z is None:
        return {}
    out: dict[str, dict[str, list]] = {}
    for block_id, g in z.groupby("block_id"):
        years: dict[str, list] = {}
        for year, gy in g.groupby("year"):
            years[str(int(year))] = [
                [round(float(lon), 6), round(float(lat), 6), int(zone), round(float(mn), 4)]
                for lon, lat, zone, mn in zip(gy["lon"], gy["lat"], gy["zone"], gy["mean_ndvi"])
            ]
        out[block_id] = years
    return out


def _features_json(f: pd.DataFrame | None) -> list:
    if f is None:
        return []
    df = f.sort_values(["block_id", "year"]).copy()
    records = []
    for r in df.itertuples(index=False):
        records.append({
            "block_id": r.block_id,
            "year": int(r.year),
            "peak_ndvi": None if pd.isna(r.peak_ndvi) else round(float(r.peak_ndvi), 3),
            "peak_doy": None if pd.isna(r.peak_doy) else int(r.peak_doy),
            "integral_may_sep": None if pd.isna(r.integral_may_sep) else round(float(r.integral_may_sep), 1),
            "greenup_date": None if (r.greenup_date in (None, "") or pd.isna(r.greenup_date)) else str(r.greenup_date),
        })
    return records


def _events_json(al: pd.DataFrame | None) -> list:
    """Historical stress log: one row per below-baseline block-season."""
    if al is None:
        return []
    ev = stress_events(al)
    return [
        {
            "block_id": r.block_id,
            "year": int(r.year),
            "n_low": int(r.n_low),
            "first_low": r.first_low.strftime("%Y-%m-%d"),
            "last_low": r.last_low.strftime("%Y-%m-%d"),
            "min_ndvi": round(float(r.min_ndvi), 3),
        }
        for r in ev.itertuples(index=False)
    ]


def _flags_json(al: pd.DataFrame | None) -> list:
    """Every flagged observation (for the CSV export)."""
    if al is None:
        return []
    low = al[al["below_baseline"]].sort_values(["block_id", "date"])
    return [
        {
            "block_id": r.block_id,
            "date": r.date.strftime("%Y-%m-%d"),
            "year": int(r.year),
            "ndvi": round(float(r.ndvi), 4),
            "base_p10": None if pd.isna(r.base_p10) else round(float(r.base_p10), 4),
            "base_median": None if pd.isna(r.base_median) else round(float(r.base_median), 4),
        }
        for r in low.itertuples(index=False)
    ]


def _status_json(al: pd.DataFrame | None, blocks: list[str], latest_year: int) -> dict:
    """Per block, where the latest season stands against its own baseline.

    state: "active"  - the most recent judged observation is in a below-baseline run
           "flagged" - flagged earlier this season, latest observation recovered
           "ok"      - judged all season, never flagged
           "no-baseline" - too little prior history to judge yet
    """
    out: dict[str, dict] = {}
    for b in blocks:
        st = {"state": "no-baseline", "n_low": 0, "first_low": None,
              "last_low": None, "min_ndvi": None, "last_obs": None}
        if al is not None:
            g = al[(al["block_id"] == b) & (al["year"] == latest_year)].sort_values("date")
            if len(g) and g["base_p10"].notna().any():
                low = g[g["below_baseline"]]
                last = g.iloc[-1]
                st["last_obs"] = last["date"].strftime("%Y-%m-%d")
                if len(low):
                    st.update({
                        "state": "active" if bool(last["below_baseline"]) else "flagged",
                        "n_low": int(len(low)),
                        "first_low": low["date"].min().strftime("%Y-%m-%d"),
                        "last_low": low["date"].max().strftime("%Y-%m-%d"),
                        "min_ndvi": round(float(low["ndvi"].min()), 3),
                    })
                else:
                    st["state"] = "ok"
        out[b] = st
    return out


def _reading(status: dict, meta: pd.DataFrame) -> str:
    """Plain-English weather-vs-single-block reading for the current season.

    Regenerated on every build. "active" blocks are still below baseline as of
    the latest reading; "flagged" ones dipped earlier and have recovered - the
    sentence keeps that distinction so it stays true as the season moves on.
    """
    judged = [b for b, s in status.items() if s["state"] != "no-baseline"]
    low = [b for b in judged if status[b]["state"] in ("active", "flagged")]
    active = sorted(b for b in low if status[b]["state"] == "active")
    recovered = sorted(set(low) - set(active))
    if not judged:
        return ""
    if not low:
        text = "No block sits below its own baseline this season."
    elif len(judged) == 1:
        text = (f"{low[0]} is below its baseline as of the latest reading; " if active else
                f"{low[0]} ran below its baseline earlier this season and has recovered; ")
        text += "with a single judged block there is no cross-block comparison."
    elif len(low) == len(judged):
        text = (f"All {len(judged)} blocks have run below their own baselines this season - "
                "a shared, regional cause (weather, heat, smoke) is more likely than a single-block failure.")
        if not active:
            text += " All have recovered as of the latest reading."
        elif recovered:
            text += f" Still below as of the latest reading: {', '.join(active)}; the rest have recovered."
    else:
        ok = sorted(set(judged) - set(low))
        if active:
            text = (f"{', '.join(active)} below baseline while {', '.join(ok)} tracks normally - "
                    "look for a cause specific to the flagged block (irrigation, virus, damage).")
            if recovered:
                text += f" {', '.join(recovered)} dipped earlier this season and recovered."
        else:
            text = (f"{', '.join(recovered)} ran below baseline earlier this season while "
                    f"{', '.join(ok)} tracked normally, and has since recovered - if it dips again, "
                    "look for a cause specific to that block (irrigation, virus, damage).")
    if len(judged) > 1 and "variety" in meta.columns:
        v = meta.set_index("block_id")["variety"].reindex(judged).dropna()
        if len(v) == len(judged) and v.nunique() == len(judged):
            text += " Blocks are different varieties, so read the comparison as a hint, not a control."
    return text


def _landsat_json(ls: pd.DataFrame | None) -> dict:
    """Per block: [year, May-Sep mean NDVI, n obs] from the 30 m Landsat
    history. Block-level context only - a different sensor and scale, never
    mixed into the Sentinel charts."""
    if ls is None:
        return {}
    df = ls.dropna(subset=["ndvi_median"]).copy()
    df = df[df["valid_frac"] >= 0.6]
    m = df["date"].dt.month
    df = df[(m >= 5) & (m <= 9)]
    df["year"] = df["date"].dt.year
    out: dict[str, list] = {}
    for block_id, g in df.groupby("block_id"):
        rows = []
        for year, gy in g.groupby("year"):
            rows.append([int(year), round(float(gy["ndvi_median"].mean()), 3), int(len(gy))])
        out[block_id] = sorted(rows)
    return out


def _outlook_json(band: pd.DataFrame | None, summary: pd.DataFrame | None) -> dict:
    """Per block: the GP projection band for the rest of the season plus its
    headline numbers (projected peak / May-Sep integral with 80% ranges)."""
    if band is None or summary is None:
        return {}
    out: dict[str, dict] = {}
    for block_id, g in band.groupby("block_id"):
        g = g.sort_values("doy")
        entry = {"band": [
            [int(d), round(float(m), 4), round(float(lo), 4), round(float(hi), 4)]
            for d, m, lo, hi in zip(g["doy"], g["mu"], g["lo"], g["hi"])
        ]}
        s = summary[summary["block_id"] == block_id]
        if len(s):
            r = s.iloc[0]
            entry["summary"] = {
                "n_train_seasons": int(r["n_train_seasons"]),
                "proj_peak": float(r["proj_peak"]),
                "proj_peak_lo": float(r["proj_peak_lo"]),
                "proj_peak_hi": float(r["proj_peak_hi"]),
                "proj_integral": float(r["proj_integral"]),
                "proj_integral_lo": float(r["proj_integral_lo"]),
                "proj_integral_hi": float(r["proj_integral_hi"]),
            }
        out[block_id] = entry
    return out


def _analogs_json(an: pd.DataFrame | None, meta: pd.DataFrame) -> dict:
    """Per block: ranked most-similar past seasons, pre-planting ones tagged."""
    if an is None or an.empty:
        return {}
    bstart = {}
    if "baseline_start" in meta.columns:
        bstart = {r.block_id: int(r.baseline_start) for r in meta.itertuples()
                  if not pd.isna(r.baseline_start)}
    out: dict[str, list] = {}
    for block_id, g in an.groupby("block_id"):
        out[block_id] = [
            {
                "block": r.analog_block,
                "year": int(r.analog_year),
                "diff": round(float(r.mean_abs_diff), 3),
                "pre": int(r.analog_year) < bstart.get(r.analog_block, 0),
            }
            for r in g.sort_values("rank").itertuples()
        ]
    return out


def _kpis(quality: pd.DataFrame, feats, al, meta) -> tuple[dict, int]:
    """Grower headline numbers per block: latest reading with its distance from
    baseline, latest NDRE, season peak so far vs typical, green-up vs typical,
    and the low-vigor flag count."""
    meta_ix = meta.set_index("block_id") if "block_id" in meta.columns else pd.DataFrame()

    def _m(block_id, col):
        if col in meta_ix.columns and block_id in meta_ix.index:
            v = meta_ix.loc[block_id, col]
            return None if pd.isna(v) else v
        return None

    events = stress_events(al) if al is not None else pd.DataFrame(columns=["block_id", "year", "n_low"])
    latest_year = int(quality["date"].dt.year.max())

    out = {}
    for block_id in sorted(quality["block_id"].unique()):
        b = quality[quality["block_id"] == block_id].sort_values("date")

        # Latest reading: prefer the judged (cleaned) alert series so the value,
        # its baseline distance, and the flag all describe the same observation.
        latest_ndvi = latest_date = latest_delta = None
        a_bl = al[(al["block_id"] == block_id) & (al["year"] == latest_year)].sort_values("date") \
            if al is not None else pd.DataFrame()
        if len(a_bl):
            last = a_bl.iloc[-1]
            latest_ndvi = round(float(last["ndvi"]), 3)
            latest_date = last["date"].strftime("%Y-%m-%d")
            if not pd.isna(last["base_median"]):
                latest_delta = round(float(last["ndvi"] - last["base_median"]), 3)
        elif len(b):
            last = b.iloc[-1]
            latest_ndvi = round(float(last["ndvi_median"]), 3)
            latest_date = last["date"].strftime("%Y-%m-%d")

        ndre = b.dropna(subset=["ndre_median"])
        latest_ndre = round(float(ndre.iloc[-1]["ndre_median"]), 3) if len(ndre) else None

        # Season features: this season so far vs the typical of baseline-eligible
        # prior seasons (>= the block's baseline_start, so pre-planting ground
        # cover never poses as "typical").
        peak = peak_typical = greenup = greenup_delta = None
        if feats is not None:
            bstart = _m(block_id, "baseline_start") or BASELINE_FLOOR_YEAR
            fb = feats[feats["block_id"] == block_id]
            f_now = fb[fb["year"] == latest_year]
            prior = fb[(fb["year"] < latest_year) & (fb["year"] >= int(bstart))]
            if len(f_now):
                r = f_now.iloc[0]
                peak = None if pd.isna(r["peak_ndvi"]) else round(float(r["peak_ndvi"]), 3)
                if not (r["greenup_date"] in (None, "") or pd.isna(r["greenup_date"])):
                    greenup = str(r["greenup_date"])
                if len(prior) and "greenup_doy" in fb.columns and not pd.isna(r.get("greenup_doy")):
                    typ = prior["greenup_doy"].dropna()
                    if len(typ):
                        greenup_delta = int(round(float(r["greenup_doy"]) - float(typ.median())))
            if len(prior):
                pk = prior["peak_ndvi"].dropna()
                if len(pk):
                    peak_typical = round(float(pk.median()), 3)

        n_low = int(
            events[(events["block_id"] == block_id) & (events["year"] == latest_year)]["n_low"].sum()
        ) if len(events) else 0

        py = _m(block_id, "planting_year")
        out[block_id] = {
            "variety": _m(block_id, "variety") or "",
            "site": _m(block_id, "site") or "",
            "planting_year": None if py is None else int(py),
            "latest_ndvi": latest_ndvi,
            "latest_date": latest_date,
            "latest_delta": latest_delta,
            "latest_ndre": latest_ndre,
            "peak_ndvi": peak,
            "peak_typical": peak_typical,
            "greenup_date": greenup,
            "greenup_delta_days": greenup_delta,
            "active_alerts": n_low,
        }
    return out, latest_year


def build_dashboard(
    processed_dir: str | Path,
    blocks_path: str | Path,
    out_dir: str | Path,
    freeze_year: int = 2024,
) -> Path:
    """Assemble the interactive dashboard HTML and return the written path."""
    processed_dir = Path(processed_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ts = _load(processed_dir / "block_timeseries.parquet")
    if ts is None:
        raise FileNotFoundError("block_timeseries.parquet is required to build the dashboard.")
    feats = _load(processed_dir / "season_features.parquet")
    zoned = _load(processed_dir / "vigor_zones.parquet")
    al = _load(processed_dir / "vigor_alerts.parquet")
    landsat = _load(processed_dir / "landsat_timeseries.parquet")
    ol_band = _load(processed_dir / "season_outlook.parquet")
    ol_summary = _load(processed_dir / "outlook_summary.parquet")
    analogs = _load(processed_dir / "season_analogs.parquet")

    gdf = gpd.read_file(Path(blocks_path))
    meta = _block_meta(gdf)

    quality = _quality(ts)
    kpis, latest_year = _kpis(quality, feats, al, meta)
    blocks = sorted(ts["block_id"].unique())
    status = _status_json(al, blocks, latest_year)

    sites = sorted({str(s).title() for s in meta["site"].dropna()}) if "site" in meta.columns else []

    data = {
        "generated": _dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "freeze_year": freeze_year,
        "history_floor": BASELINE_FLOOR_YEAR,  # older seasons render as gray context
        "latest_year": latest_year,
        "latest_obs": quality["date"].max().strftime("%Y-%m-%d") if len(quality) else None,
        "sites": " & ".join(sites),
        "blocks": blocks,
        "kpis": kpis,
        "status": status,
        "reading": _reading(status, meta),
        "timeseries": _smoothed_json(ts, "ndvi_median"),
        "ndre": _smoothed_json(ts, "ndre_median"),
        "baseline": _baseline_json(al),
        "zones": _zones_json(zoned),
        "outlines": _outlines_json(gdf),
        "features": _features_json(feats),
        "events": _events_json(al),
        "flags": _flags_json(al),
        "landsat": _landsat_json(landsat),
        "outlook": _outlook_json(ol_band, ol_summary),
        "analogs": _analogs_json(analogs, meta),
    }

    html = render_page(json.dumps(data, separators=(",", ":")))
    out_path = out_dir / "index.html"
    out_path.write_text(html, encoding="utf-8")
    return out_path


if __name__ == "__main__":  # manual refresh: python -m vigor.webdash
    root = Path(__file__).resolve().parents[2]
    out = build_dashboard(
        processed_dir=root / "data" / "processed",
        blocks_path=root / "data" / "blocks.geojson",
        out_dir=root / "outputs" / "dashboard",
    )
    print(f"interactive dashboard -> {out}")
