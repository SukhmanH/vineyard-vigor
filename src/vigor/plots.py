"""Figures for the vigor time series.

Pure matplotlib/pandas; must run offline. Figures go to outputs/figures/,
named {phase}_{block_id}_{description}.png.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.lines import Line2D

from .ingest import MIN_VALID_FRAC

# Day-of-year of each month start (non-leap; one day of drift is invisible here).
_MONTH_STARTS = {"Jan": 1, "Feb": 32, "Mar": 60, "Apr": 91, "May": 121, "Jun": 152,
                 "Jul": 182, "Aug": 213, "Sep": 244, "Oct": 274, "Nov": 305, "Dec": 335}

# Validated 8-slot categorical theme (dataviz skill, references/palette.md).
# Fixed hue order maximizes worst-case adjacent CVD separation; assign by
# position (oldest year -> slot 1) rather than picking hues ad hoc, and never
# reuse a slot for a different entity once assigned.
_CATEGORICAL_THEME = [
    "#2a78d6",  # 1 blue
    "#008300",  # 2 green
    "#e87ba4",  # 3 magenta
    "#eda100",  # 4 yellow
    "#1baf7a",  # 5 aqua
    "#eb6834",  # 6 orange
    "#4a3aa7",  # 7 violet
    "#e34948",  # 8 red
]


def ndvi_multiyear(
    df: pd.DataFrame,
    min_valid_frac: float = MIN_VALID_FRAC,
    emphasize_year: int | None = None,
) -> plt.Figure:
    """One panel per block: block-median NDVI vs day of year (Jan-Dec), one
    line per year.

    Each year gets a fixed, distinct hue from the validated categorical theme
    (assigned in year order, not cycled) so years read as identities rather
    than a gradient. `emphasize_year` (e.g. the 2024 freeze season) is drawn
    heavier with a filled marker so it stands out without relying on color
    alone. Rows below `min_valid_frac` are not drawn. Supports up to 8 years
    (2019-2026); add a slot to `_CATEGORICAL_THEME` before extending.
    """
    data = df[df["valid_frac"] >= min_valid_frac].dropna(subset=["ndvi_median"])
    blocks = sorted(data["block_id"].unique())
    years = sorted(data["date"].dt.year.unique())

    if len(years) > len(_CATEGORICAL_THEME):
        raise ValueError(
            f"{len(years)} years but only {len(_CATEGORICAL_THEME)} categorical "
            "slots defined - extend _CATEGORICAL_THEME (and re-validate) first."
        )
    color = dict(zip(years, _CATEGORICAL_THEME))

    fig, axes = plt.subplots(
        len(blocks), 1,
        figsize=(10, 3.4 * len(blocks)),
        sharex=True, sharey=True, squeeze=False,
    )
    for ax, block_id in zip(axes.flat, blocks):
        sub = data[data["block_id"] == block_id]
        for year, g in sub.groupby(sub["date"].dt.year):
            g = g.sort_values("date")
            emphasized = year == emphasize_year
            ax.plot(
                g["date"].dt.dayofyear, g["ndvi_median"],
                color=color[year],
                lw=2.4 if emphasized else 1.2,
                marker="o", markersize=5 if emphasized else 3,
                zorder=3 if emphasized else 2,
            )
        ax.set_title(block_id, loc="left", fontsize=11)
        ax.set_ylabel("NDVI (block median)")
        ax.grid(alpha=0.25, lw=0.5)

    for ax in axes.flat:
        ax.set_xlim(1, 366)
        ax.set_xticks(list(_MONTH_STARTS.values()))
        ax.set_xticklabels(list(_MONTH_STARTS.keys()))

    handles = [Line2D([0], [0], color=color[y],
                       lw=2.4 if y == emphasize_year else 2)
               for y in years]
    labels = [f"{y} (freeze)" if y == emphasize_year else str(y) for y in years]
    fig.legend(handles, labels, ncol=min(len(years), 8),
               loc="upper center", frameon=False)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    return fig


# Per-year facets use the emphasis pattern (dataviz "one series is the point,
# rest are context"): the focal year in the accent hue, every other season in a
# recessive gray behind it. Identity is carried by the panel title, not color,
# so a single accent hue is all that's needed - no categorical cycling.
_FACET_FOCAL = "#2a78d6"     # accent blue
_FACET_FREEZE = "#d03b3b"    # focal freeze year (status critical)
_FACET_CONTEXT = "#c3c2b7"   # other seasons (recessive)


def ndvi_year_facets(
    df: pd.DataFrame,
    block_id: str,
    min_valid_frac: float = MIN_VALID_FRAC,
    emphasize_year: int | None = 2024,
) -> plt.Figure:
    """One small panel per year for a block, so the years are spaced out and
    each is legible - while every other season sits faded in gray behind the
    focal year, keeping it comparable to prior (and later) seasons.

    Focal year in accent blue (red when it is `emphasize_year`, the freeze
    season); context seasons in recessive gray. Growing-season window
    (Apr-Oct), matching the cleaning and baseline figures. Rows below
    `min_valid_frac` are not drawn.
    """
    data = df[df["block_id"] == block_id]
    data = data[data["valid_frac"] >= min_valid_frac].dropna(subset=["ndvi_median"]).copy()
    month = data["date"].dt.month
    data = data[(month >= 4) & (month <= 10)]
    data["year"] = data["date"].dt.year
    data["doy"] = data["date"].dt.dayofyear
    years = sorted(data["year"].unique())

    ncol = min(4, len(years)) or 1
    nrow = max(1, -(-len(years) // ncol))
    fig, axes = plt.subplots(
        nrow, ncol, figsize=(2.9 * ncol, 2.3 * nrow),
        sharex=True, sharey=True, squeeze=False,
    )
    flat = axes.flat

    for ax, year in zip(flat, years):
        # Context: every other season, faded gray, behind.
        for other, g in data.groupby("year"):
            if other == year:
                continue
            g = g.sort_values("doy")
            ax.plot(g["doy"], g["ndvi_median"], color=_FACET_CONTEXT,
                    lw=0.8, alpha=0.7, zorder=1)
        # Focal year on top.
        f = data[data["year"] == year].sort_values("doy")
        focal_color = _FACET_FREEZE if year == emphasize_year else _FACET_FOCAL
        ax.plot(f["doy"], f["ndvi_median"], color=focal_color, lw=1.8,
                marker="o", markersize=3, zorder=3)

        title = f"{year} (freeze)" if year == emphasize_year else str(year)
        ax.set_title(title, loc="left", fontsize=10)
        ax.set_xlim(_MONTH_STARTS["Apr"], _MONTH_STARTS["Nov"])
        ax.set_xticks([_MONTH_STARTS[m] for m in ("Apr", "Jun", "Aug", "Oct")])
        ax.set_xticklabels(["Apr", "Jun", "Aug", "Oct"])
        ax.grid(alpha=0.25, lw=0.5)

    for ax in flat[len(years):]:
        ax.set_visible(False)
    for ax in axes[:, 0]:
        ax.set_ylabel("NDVI")

    handles = [
        Line2D([0], [0], color=_FACET_FOCAL, lw=1.8, marker="o", label="this season"),
        Line2D([0], [0], color=_FACET_FREEZE, lw=1.8, label="freeze year"),
        Line2D([0], [0], color=_FACET_CONTEXT, lw=1.5, label="other seasons"),
    ]
    fig.suptitle(f"{block_id} — NDVI by season (each year vs the others)",
                 x=0.02, ha="left", fontsize=12)
    fig.legend(handles=handles, loc="upper right", ncol=3, frameon=False, fontsize=9)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    return fig


# Phase 3 cleaning figure. Roles, not raw hue: kept observations recede, the
# smoothed curve carries the signal, dropped outliers wear the reserved
# "critical" status color (with a distinct marker so it never rests on color
# alone), and green-up is marked in the categorical green slot.
_OBS_COLOR = "#898781"       # muted ink; raw points recede behind the curve
_SMOOTH_COLOR = "#2a78d6"    # categorical blue; the signal
_OUTLIER_COLOR = "#d03b3b"   # status: critical (dropped points)
_GREENUP_COLOR = "#008300"   # categorical green; green-up marker


def cleaning_seasons(
    observations: pd.DataFrame,
    smoothed: pd.DataFrame,
    features: pd.DataFrame,
    block_id: str,
) -> plt.Figure:
    """One panel per season for a block: kept NDVI observations, dropped
    outliers, the Savitzky-Golay curve, and the extracted features marked.

    `observations` (block_id, date, ndvi, is_outlier), `smoothed`
    (block_id, year, date, doy, ndvi_smooth) and `features` (per block-year)
    are the Phase 3 outputs. Peak is a filled dot, green-up a vertical rule -
    each labeled, so identity never rests on color alone.
    """
    obs = observations[observations["block_id"] == block_id].copy()
    obs["year"] = obs["date"].dt.year
    sm = smoothed[smoothed["block_id"] == block_id]
    feats = features[features["block_id"] == block_id].set_index("year")

    years = sorted(sm["year"].unique())
    ncol = 2
    nrow = max(1, -(-len(years) // ncol))  # ceil
    fig, axes = plt.subplots(
        nrow, ncol, figsize=(11, 2.4 * nrow), sharey=True, squeeze=False
    )
    flat = axes.flat

    for ax, year in zip(flat, years):
        o = obs[obs["year"] == year]
        s = sm[sm["year"] == year].sort_values("doy")
        kept = o[~o["is_outlier"]]
        dropped = o[o["is_outlier"]]

        ax.plot(s["doy"], s["ndvi_smooth"], color=_SMOOTH_COLOR, lw=2, zorder=3)
        ax.scatter(kept["date"].dt.dayofyear, kept["ndvi"],
                   s=12, color=_OBS_COLOR, zorder=2, label="observation")
        if len(dropped):
            ax.scatter(dropped["date"].dt.dayofyear, dropped["ndvi"],
                       s=40, color=_OUTLIER_COLOR, marker="x", lw=1.6,
                       zorder=4, label="dropped (smoke/haze)")

        if year in feats.index:
            f = feats.loc[year]
            ax.scatter([f["peak_doy"]], [f["peak_ndvi"]], s=45,
                       color=_SMOOTH_COLOR, zorder=5, edgecolor="white", lw=1)
            if pd.notna(f["greenup_doy"]):
                ax.axvline(f["greenup_doy"], color=_GREENUP_COLOR, lw=1.3,
                           ls="--", zorder=1)

        ax.set_title(str(year), loc="left", fontsize=10)
        ax.set_xlim(_MONTH_STARTS["Apr"], _MONTH_STARTS["Nov"])
        ax.set_xticks([_MONTH_STARTS[m] for m in ("Apr", "Jun", "Aug", "Oct")])
        ax.set_xticklabels(["Apr", "Jun", "Aug", "Oct"])
        ax.grid(alpha=0.25, lw=0.5)

    for ax in flat[len(years):]:
        ax.set_visible(False)
    for ax in axes[:, 0]:
        ax.set_ylabel("NDVI")

    handles = [
        Line2D([0], [0], color=_SMOOTH_COLOR, lw=2, label="smoothed (Savitzky-Golay)"),
        Line2D([0], [0], marker="o", color=_OBS_COLOR, lw=0, label="observation"),
        Line2D([0], [0], marker="x", color=_OUTLIER_COLOR, lw=0, label="dropped (smoke/haze)"),
        Line2D([0], [0], marker="o", color=_SMOOTH_COLOR, lw=0,
               markeredgecolor="white", label="peak NDVI"),
        Line2D([0], [0], color=_GREENUP_COLOR, lw=1.3, ls="--", label="green-up"),
    ]
    fig.suptitle(f"{block_id} — season cleaning & features", x=0.02, ha="left", fontsize=12)
    fig.legend(handles=handles, loc="upper right", ncol=3, frameon=False, fontsize=9)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    return fig


# Vigor zones are an ORDERED magnitude scale (low -> high vigor), so they use a
# sequential single-hue ramp, not categorical hues. These are the validated
# ordinal steps of the blue ramp (dataviz palette: >= step 250 on light), dark
# = higher vigor. Indexed by zone id after the low->high relabel in zones.py.
_ZONE_RAMP = ["#86b6ef", "#3987e5", "#184f95"]  # k=3: low, medium, high vigor


def _zone_colors(k: int) -> list[str]:
    if k == len(_ZONE_RAMP):
        return _ZONE_RAMP
    # Even sampling of the ramp for other k (k=2 -> lightest + darkest).
    idx = [round(i * (len(_ZONE_RAMP) - 1) / (k - 1)) for i in range(k)] if k > 1 else [0]
    return [_ZONE_RAMP[i] for i in idx]


def zone_maps(zoned: pd.DataFrame, block_id: str, k: int | None = None) -> plt.Figure:
    """Per-season vigor-zone maps for one block: pixel centroids colored by zone.

    `zoned` is the output of zones.zone_all (per-pixel lon/lat + integer `zone`,
    0 = lowest vigor). One panel per season; darker = higher vigor (sequential
    ramp, since zones are an ordered magnitude, not distinct identities). Read
    zones that hold their shape across years as soil/rootstock, zones that
    appear in a single year as management, irrigation, or damage.
    """
    b = zoned[zoned["block_id"] == block_id]
    years = sorted(b["year"].unique())
    if k is None:
        k = int(b["zone"].max()) + 1 if len(b) else len(_ZONE_RAMP)
    colors = _zone_colors(k)

    ncol = min(4, len(years)) or 1
    nrow = max(1, -(-len(years) // ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(3.0 * ncol, 3.0 * nrow), squeeze=False)
    flat = axes.flat

    for ax, year in zip(flat, years):
        s = b[b["year"] == year]
        for zone in range(k):
            z = s[s["zone"] == zone]
            ax.scatter(z["lon"], z["lat"], s=14, color=colors[zone],
                       edgecolors="none", label=f"zone {zone}")
        ax.set_title(str(year), fontsize=10, loc="left")
        ax.set_aspect("equal")
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_edgecolor("#c3c2b7")

    for ax in flat[len(years):]:
        ax.set_visible(False)

    labels = ["low vigor", *[f"zone {i}" for i in range(1, k - 1)], "high vigor"] if k >= 2 else ["vigor"]
    handles = [Line2D([0], [0], marker="o", lw=0, color=colors[i], label=labels[i])
               for i in range(k)]
    fig.suptitle(f"{block_id} — vigor zones by season (k={k})", x=0.02, ha="left", fontsize=12)
    fig.legend(handles=handles, loc="upper right", ncol=k, frameon=False, fontsize=9)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    return fig


# Baseline-comparison figure. Baseline structure recedes (gray band + median
# line); the current season's observations carry the signal, and below-baseline
# points wear the reserved critical red with a distinct marker so identity
# isn't color-alone.
_BASELINE_BAND = "#c3c2b7"   # IQR band (recessive)
_BASELINE_LINE = "#898781"   # baseline median
_P10_LINE = "#eb6834"        # the 10th-percentile threshold (status orange)
_OBS_LINE = "#2a78d6"        # current-season observations
_LOW_COLOR = "#d03b3b"       # status: critical (below baseline)


def baseline_comparison(alerts: pd.DataFrame, block_id: str) -> plt.Figure:
    """Per-season view for one block: current observations against the
    prior-season day-of-year baseline, with below-baseline runs marked.

    `alerts` is the output of vigor_alerts.below_baseline_seasons. Only seasons
    with a baseline are drawn (early seasons have no prior history to judge
    against). The gray band is the baseline IQR, the gray line its median, the
    orange line the 10th-percentile threshold; red ×'s are below-baseline points
    (two or more consecutive observations below the threshold).
    """
    b = alerts[alerts["block_id"] == block_id].copy()
    have_base = b[b["n_baseline"] >= 1].dropna(subset=["base_p10"])
    years = sorted(have_base["year"].unique())
    if not years:
        fig, ax = plt.subplots(figsize=(8, 2))
        ax.axis("off")
        ax.text(0.5, 0.5, f"{block_id}: no baseline yet (needs prior vine seasons)",
                ha="center", va="center", fontsize=11)
        return fig

    ncol = min(2, len(years))
    nrow = max(1, -(-len(years) // ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(11, 2.4 * nrow), sharey=True, squeeze=False)
    flat = axes.flat

    for ax, year in zip(flat, years):
        s = b[b["year"] == year].sort_values("doy")
        base = s.dropna(subset=["base_p10"])
        ax.fill_between(base["doy"], base["base_p25"], base["base_p75"],
                        color=_BASELINE_BAND, alpha=0.6, zorder=1, label="baseline IQR")
        ax.plot(base["doy"], base["base_median"], color=_BASELINE_LINE, lw=1.2, zorder=2)
        ax.plot(base["doy"], base["base_p10"], color=_P10_LINE, lw=1.2, ls="--", zorder=2)
        ax.plot(s["doy"], s["ndvi"], color=_OBS_LINE, lw=1.3, marker="o",
                markersize=3, zorder=3)
        low = s[s["below_baseline"]]
        if len(low):
            ax.scatter(low["doy"], low["ndvi"], s=45, color=_LOW_COLOR, marker="x",
                       lw=1.8, zorder=4)

        ax.set_title(str(year), loc="left", fontsize=10)
        ax.set_xlim(_MONTH_STARTS["Apr"], _MONTH_STARTS["Nov"])
        ax.set_xticks([_MONTH_STARTS[m] for m in ("Apr", "Jun", "Aug", "Oct")])
        ax.set_xticklabels(["Apr", "Jun", "Aug", "Oct"])
        ax.grid(alpha=0.25, lw=0.5)

    for ax in flat[len(years):]:
        ax.set_visible(False)
    for ax in axes[:, 0]:
        ax.set_ylabel("NDVI")

    handles = [
        Line2D([0], [0], color=_OBS_LINE, lw=1.3, marker="o", label="current season"),
        Line2D([0], [0], color=_BASELINE_LINE, lw=1.2, label="baseline median"),
        Line2D([0], [0], color=_P10_LINE, lw=1.2, ls="--", label="10th pct"),
        Line2D([0], [0], marker="x", color=_LOW_COLOR, lw=0, label="below baseline"),
    ]
    fig.suptitle(f"{block_id} — below-baseline check vs prior seasons",
                 x=0.02, ha="left", fontsize=12)
    fig.legend(handles=handles, loc="upper right", ncol=4, frameon=False, fontsize=9)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    return fig


def save_figure(fig: plt.Figure, path: str | Path, dpi: int = 150) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=dpi, bbox_inches="tight")
    return path
