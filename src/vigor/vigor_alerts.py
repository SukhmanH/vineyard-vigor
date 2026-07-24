"""Per-block low-vigor alerts against a day-of-year baseline (Phase 5).

Pure pandas/numpy; must run offline. Plain statistics - this is the whole
model, and no upgrade is warranted until it works.

For each block, a day-of-year baseline is built from that block's PRIOR
seasons: at each observation's day of year, pool all prior-season observations
within +/-10 days and take their median, IQR, and 10th percentile. The current
observation is "below baseline" when it sits under that 10th percentile; a
block-season raises an alert where two consecutive observations are both below.

A comparison against same-variety blocks in the same season points at the
cause: if every same-variety block is down it reads as weather; if just one is
down it reads as a single-block cause (irrigation, virus, damage).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .clean import seasonal_observations

DOY_WINDOW = 10          # +/- days pooled around each observation's day of year
LOW_PERCENTILE = 0.10    # "below the 10th percentile"
IQR_LOW, IQR_HIGH = 0.25, 0.75
N_CONSECUTIVE = 2        # consecutive below-baseline observations to raise an alert
MIN_BASELINE = 8         # prior-season points in-window required to judge a point
BASELINE_FLOOR_YEAR = 2019  # earliest season admissible to any baseline


def _mark_consecutive(below: pd.Series, n: int) -> np.ndarray:
    """Mark points that fall in a run of >= n consecutive True values.

    NaN (no baseline) breaks a run - an unconfirmable point neither starts nor
    extends one.
    """
    b = below.fillna(False).to_numpy(dtype=bool)
    marked = np.zeros(len(b), dtype=bool)
    i = 0
    while i < len(b):
        if b[i]:
            j = i
            while j < len(b) and b[j]:
                j += 1
            if j - i >= n:
                marked[i:j] = True
            i = j
        else:
            i += 1
    return marked


def below_baseline_seasons(
    df: pd.DataFrame,
    baseline_floor: int = BASELINE_FLOOR_YEAR,
    doy_window: int = DOY_WINDOW,
    low_pct: float = LOW_PERCENTILE,
    n_consecutive: int = N_CONSECUTIVE,
    min_baseline: int = MIN_BASELINE,
    baseline_start: dict[str, int] | None = None,
) -> pd.DataFrame:
    """Mark low-vigor observations per block against a prior-season DOY baseline.

    `df` is a contract timeseries (block_id, date, ndvi_median, valid_frac, ...);
    it is reduced to analysis-quality in-season observations internally. Only
    seasons strictly before the current one feed a baseline, so an alert is
    always out-of-sample. `baseline_start` optionally raises the floor per block
    (e.g. the first real post-planting season from blocks.geojson) above the
    global `baseline_floor`.

    Returns one row per observation with the baseline stats used, `below_p10`,
    and `below_baseline` (part of a >= n_consecutive below-baseline run).
    """
    obs = seasonal_observations(df)
    obs["doy"] = obs["date"].dt.dayofyear
    baseline_start = baseline_start or {}

    rows = []
    for block_id, g in obs.groupby("block_id", sort=True):
        floor = max(baseline_floor, baseline_start.get(block_id, baseline_floor))
        g = g.sort_values("date")
        for year, season in g.groupby("year"):
            prior = g[(g["year"] < year) & (g["year"] >= floor)]
            season = season.copy()
            p10 = np.full(len(season), np.nan)
            med = np.full(len(season), np.nan)
            q25 = np.full(len(season), np.nan)
            q75 = np.full(len(season), np.nan)
            nbase = np.zeros(len(season), dtype=int)
            for i, (_, row) in enumerate(season.iterrows()):
                pool = prior["ndvi"][prior["doy"].sub(row["doy"]).abs() <= doy_window]
                nbase[i] = len(pool)
                if len(pool) >= min_baseline:
                    p10[i] = pool.quantile(low_pct)
                    med[i] = pool.median()
                    q25[i] = pool.quantile(IQR_LOW)
                    q75[i] = pool.quantile(IQR_HIGH)
            season["base_p10"] = p10
            season["base_median"] = med
            season["base_p25"] = q25
            season["base_p75"] = q75
            season["n_baseline"] = nbase
            below = pd.Series(
                np.where(np.isnan(p10), np.nan, season["ndvi"].to_numpy() < p10),
                index=season.index,
            )
            season["below_p10"] = below
            season["below_baseline"] = _mark_consecutive(below, n_consecutive)
            rows.append(season)

    cols = [
        "block_id", "date", "year", "doy", "ndvi",
        "base_p10", "base_median", "base_p25", "base_p75",
        "n_baseline", "below_p10", "below_baseline",
    ]
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.concat(rows).sort_values(["block_id", "date"]).reset_index(drop=True)[cols]


def stress_events(alerts: pd.DataFrame) -> pd.DataFrame:
    """Collapse the per-observation marks to one row per below-baseline season.

    Columns: block_id, year, n_low, first_low, last_low, min_ndvi.
    """
    low = alerts[alerts["below_baseline"]]
    if low.empty:
        return pd.DataFrame(
            columns=["block_id", "year", "n_low", "first_low", "last_low", "min_ndvi"]
        )
    return (
        low.groupby(["block_id", "year"])
        .agg(
            n_low=("date", "size"),
            first_low=("date", "min"),
            last_low=("date", "max"),
            min_ndvi=("ndvi", "min"),
        )
        .reset_index()
    )


def compare_same_variety(
    alerts: pd.DataFrame, blocks: pd.DataFrame
) -> pd.DataFrame:
    """Compare each below-baseline season against same-variety blocks that year.

    `blocks` supplies block_id -> variety. For every (variety, year) that has at
    least one block below baseline, report how many same-variety blocks were low
    out of how many exist, and a reading:
    - "weather"      : every same-variety block that season is below baseline.
    - "single-block" : a strict subset is low (irrigation/virus/damage).
    - "no peers"     : only one block of that variety exists, so weather vs a
                       single-block cause cannot be told apart from vigor alone.
    """
    variety = (
        blocks.assign(variety=blocks["variety"].astype(str).str.strip().str.lower())
        .set_index("block_id")["variety"]
    )
    a = alerts.copy()
    a["variety"] = a["block_id"].map(variety)

    out = []
    for (var, year), g in a.groupby(["variety", "year"]):
        peers = sorted(g["block_id"].unique())
        low_blocks = sorted(g[g["below_baseline"]]["block_id"].unique())
        if not low_blocks:
            continue
        if len(peers) == 1:
            reading = "no peers"
        elif len(low_blocks) == len(peers):
            reading = "weather"
        else:
            reading = "single-block"
        out.append(
            {
                "variety": var,
                "year": year,
                "n_peers": len(peers),
                "n_low": len(low_blocks),
                "low_blocks": ", ".join(low_blocks),
                "reading": reading,
            }
        )
    return pd.DataFrame(
        out, columns=["variety", "year", "n_peers", "n_low", "low_blocks", "reading"]
    )


def write_alerts(df: pd.DataFrame, path) -> "Path":  # type: ignore[name-defined]
    from pathlib import Path

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return path
