"""Static HTML vigor dashboard (Phase 6, dashboard only - no scheduling).

Pure pandas/matplotlib/geopandas; runs offline. Reads the processed parquets
and blocks.geojson, regenerates the curves / zone maps / baseline figures in
memory, and writes one self-contained HTML file (figures embedded as base64,
so it needs no server and no sibling image files) to outputs/dashboard/.

Regenerate it any time with `python -m vigor.dashboard` after refreshing the
parquets - that is the manual stand-in for the weekly scheduled run, which is
intentionally not built here.
"""

from __future__ import annotations

import base64
import datetime as _dt
import html
import io
from pathlib import Path

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")  # headless; no display needed to render figures
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from . import plots  # noqa: E402

# Palette (dataviz reference instance) - keep the dashboard consistent with the
# figures it embeds.
_INK = "#0b0b0b"
_MUTED = "#52514e"
_SURFACE = "#fcfcfb"
_PLANE = "#f9f9f7"
_ACCENT = "#2a78d6"
_CRITICAL = "#d03b3b"
_GOOD = "#0ca30c"
_HAIRLINE = "#e1e0d9"


def _fig_to_data_uri(fig: plt.Figure, dpi: int = 130) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _load(path: Path) -> pd.DataFrame | None:
    return pd.read_parquet(path) if path.exists() else None


def _block_meta(blocks_path: Path) -> pd.DataFrame:
    """block_id -> site/variety/planting_year, straight from the geojson.

    Offline (geopandas only); avoids importing the Earth Engine module.
    """
    gdf = gpd.read_file(blocks_path)
    gdf.columns = gdf.columns.str.strip()
    cols = [c for c in ["block_id", "site", "variety", "planting_year", "baseline_start"]
            if c in gdf.columns]
    return pd.DataFrame(gdf[cols])


def build_dashboard(
    processed_dir: str | Path,
    blocks_path: str | Path,
    out_dir: str | Path,
    freeze_year: int = 2024,
) -> Path:
    """Assemble the dashboard HTML and return the written path."""
    processed_dir = Path(processed_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ts = _load(processed_dir / "block_timeseries.parquet")
    feats = _load(processed_dir / "season_features.parquet")
    zoned = _load(processed_dir / "vigor_zones.parquet")
    alerts = _load(processed_dir / "vigor_alerts.parquet")
    meta = _block_meta(Path(blocks_path))
    if ts is None:
        raise FileNotFoundError("block_timeseries.parquet is required to build the dashboard.")

    blocks = sorted(ts["block_id"].unique())
    variety = dict(zip(meta.get("block_id", []), meta.get("variety", [])))
    site = dict(zip(meta.get("block_id", []), meta.get("site", [])))

    sections: list[str] = []

    # --- Low-vigor alerts banner (most recent season) ---
    active_html, current_year = _active_alerts_section(alerts, variety, site)
    sections.append(active_html)

    # --- Per-block: NDVI-by-season facets, zone maps, baseline figures ---
    # Curves are drawn as per-year small multiples (each season vs the others)
    # rather than one crowded all-years panel, so they stay readable while
    # remaining comparable to prior seasons.
    for block_id in blocks:
        parts = [
            ("NDVI by season (each year vs the others)",
             _fig_to_data_uri(plots.ndvi_year_facets(ts, block_id, emphasize_year=freeze_year))),
        ]
        if zoned is not None and block_id in set(zoned["block_id"]):
            parts.append(("Vigor zones by season",
                          _fig_to_data_uri(plots.zone_maps(zoned, block_id))))
        if alerts is not None and block_id in set(alerts["block_id"]):
            parts.append(("Below-baseline check vs prior seasons",
                          _fig_to_data_uri(plots.baseline_comparison(alerts, block_id))))
        sections.append(_block_section(block_id, variety.get(block_id), site.get(block_id), parts))

    # --- Season features table ---
    if feats is not None:
        sections.append(_features_section(feats))

    page = _page(sections, current_year)
    out_path = out_dir / "index.html"
    out_path.write_text(page, encoding="utf-8")
    return out_path


def _active_alerts_section(alerts, variety, site) -> tuple[str, int | None]:
    if alerts is None or not alerts["below_baseline"].any():
        return (
            f'<section class="banner ok"><h2>No low-vigor alerts</h2>'
            f'<p>No block-season currently sits below its prior-season 10th '
            f'percentile for two consecutive observations.</p></section>',
            None,
        )
    from .vigor_alerts import stress_events

    events = stress_events(alerts)
    current_year = int(events["year"].max())
    active = events[events["year"] == current_year].sort_values("block_id")

    rows = "".join(
        f"<tr><td>{html.escape(str(r.block_id))}</td>"
        f"<td>{html.escape(str(variety.get(r.block_id, '')))}</td>"
        f"<td>{r.n_low}</td>"
        f"<td>{r.first_low.date()} &ndash; {r.last_low.date()}</td>"
        f"<td>{r.min_ndvi:.3f}</td></tr>"
        for r in active.itertuples()
    )
    tone = "alert" if len(active) else "ok"
    return (
        f'<section class="banner {tone}">'
        f"<h2>Low-vigor alerts &mdash; {current_year} season</h2>"
        f'<table class="flags"><thead><tr>'
        f"<th>block</th><th>variety</th><th>low obs</th><th>window</th><th>min NDVI</th>"
        f"</tr></thead><tbody>{rows}</tbody></table>"
        f'<p class="note">Baselines respect each block&rsquo;s <code>baseline_start</code>, '
        f"so these compare vines to prior vine seasons only. On blocks planted in 2024 the "
        f"baseline is still thin&mdash;read early alerts as provisional until more seasons "
        f"accrue, and note the same-variety comparison has no peers yet.</p>"
        f"</section>",
        current_year,
    )


def _figure_section(title: str, caption: str, uri: str) -> str:
    return (
        f'<section><h2>{html.escape(title)}</h2>'
        f'<p class="caption">{html.escape(caption)}</p>'
        f'<img src="{uri}" alt="{html.escape(title)}"></section>'
    )


def _block_section(block_id, variety, site, parts) -> str:
    subtitle = " &middot; ".join(
        html.escape(str(x)) for x in [variety, site] if x not in (None, "")
    )
    figs = "".join(
        f'<figure><figcaption>{html.escape(t)}</figcaption>'
        f'<img src="{uri}" alt="{html.escape(t)}"></figure>'
        for t, uri in parts
    )
    return (
        f'<section class="block"><h2>{html.escape(str(block_id))} '
        f'<span class="sub">{subtitle}</span></h2>{figs}</section>'
    )


def _features_section(feats: pd.DataFrame) -> str:
    df = feats.sort_values(["block_id", "year"]).copy()
    disp = df[["block_id", "year", "peak_ndvi", "peak_doy", "integral_may_sep", "greenup_date"]]
    header = "".join(f"<th>{html.escape(c)}</th>" for c in
                     ["block", "year", "peak NDVI", "peak DOY", "May-Sep integral", "green-up"])
    body = ""
    for r in disp.itertuples(index=False):
        integral = "" if pd.isna(r.integral_may_sep) else f"{r.integral_may_sep:.1f}"
        greenup = "" if r.greenup_date in (None, "") or pd.isna(r.greenup_date) else html.escape(str(r.greenup_date))
        body += (
            f"<tr><td>{html.escape(str(r.block_id))}</td><td>{r.year}</td>"
            f"<td>{r.peak_ndvi:.3f}</td><td>{int(r.peak_doy)}</td>"
            f"<td>{integral}</td><td>{greenup}</td></tr>"
        )
    return (
        f'<section><h2>Season features</h2>'
        f'<table class="data"><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table>'
        f'</section>'
    )


def _page(sections: list[str], current_year: int | None) -> str:
    generated = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    body = "\n".join(sections)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Vineyard Vigor Dashboard</title>
<style>
  :root {{
    --ink: {_INK}; --muted: {_MUTED}; --surface: {_SURFACE}; --plane: {_PLANE};
    --accent: {_ACCENT}; --critical: {_CRITICAL}; --good: {_GOOD}; --hairline: {_HAIRLINE};
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --ink: #ffffff; --muted: #c3c2b7; --surface: #1a1a19; --plane: #0d0d0d;
      --accent: #3987e5; --critical: #e66767; --good: #0ca30c; --hairline: #2c2c2a;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: var(--plane); color: var(--ink);
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    line-height: 1.5;
  }}
  header {{ padding: 28px 32px 16px; border-bottom: 1px solid var(--hairline); }}
  header h1 {{ margin: 0; font-size: 22px; }}
  header .meta {{ color: var(--muted); font-size: 13px; margin-top: 4px; }}
  main {{ max-width: 1100px; margin: 0 auto; padding: 24px 32px 64px; }}
  section {{
    background: var(--surface); border: 1px solid var(--hairline);
    border-radius: 10px; padding: 20px 22px; margin: 20px 0;
  }}
  section h2 {{ margin: 0 0 6px; font-size: 17px; }}
  .sub {{ color: var(--muted); font-weight: 400; font-size: 14px; }}
  .caption, .note {{ color: var(--muted); font-size: 13px; margin: 4px 0 14px; }}
  .note {{ margin-top: 14px; }}
  img {{ max-width: 100%; height: auto; display: block; border-radius: 6px; }}
  figure {{ margin: 18px 0 0; }}
  figcaption {{ color: var(--muted); font-size: 13px; margin-bottom: 6px; }}
  .banner {{ border-left: 4px solid var(--accent); }}
  .banner.alert {{ border-left-color: var(--critical); }}
  .banner.ok {{ border-left-color: var(--good); }}
  table {{ border-collapse: collapse; width: 100%; font-size: 14px; font-variant-numeric: tabular-nums; }}
  th, td {{ text-align: left; padding: 7px 12px; border-bottom: 1px solid var(--hairline); }}
  th {{ color: var(--muted); font-weight: 600; }}
  code {{ background: var(--plane); padding: 1px 5px; border-radius: 4px; font-size: 12px; }}
  .overflow {{ overflow-x: auto; }}
</style>
</head>
<body>
<header>
  <h1>Vineyard Vigor Dashboard</h1>
  <div class="meta">South Okanagan blocks &middot; generated {generated}
  {f"&middot; current season {current_year}" if current_year else ""}</div>
</header>
<main>
{body}
</main>
</body>
</html>
"""


if __name__ == "__main__":  # manual refresh: python -m vigor.dashboard
    root = Path(__file__).resolve().parents[2]
    out = build_dashboard(
        processed_dir=root / "data" / "processed",
        blocks_path=root / "data" / "blocks.geojson",
        out_dir=root / "outputs" / "dashboard",
    )
    print(f"dashboard -> {out}")
