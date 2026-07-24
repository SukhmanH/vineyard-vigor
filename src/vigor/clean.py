"""Cleaning and smoothing of the block NDVI time series (Phase 3).

Pure pandas/numpy/scipy; must run offline. Everything here is re-derivable
from the parquet alone.

Pipeline, per block per season:
1. Keep only rows with `valid_frac >= MIN_VALID_FRAC` and a real NDVI, inside
   the April-October growing-season window.
2. Rolling-median outlier screen. Wildfire smoke depresses NDVI without being
   caught by the cloud mask (expect it around August 2018/2021/2023); such
   points sit far below their local rolling median and are dropped.
3. Interpolate the survivors onto a daily grid and Savitzky-Golay smooth it,
   giving one continuous curve per block per season to read features off.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.signal import savgol_filter

from .ingest import MIN_VALID_FRAC

# Growing-season window (README: April 1 to October 31). Feature extraction and
# smoothing operate inside this window; dormant/winter scenes (snow, cover crop)
# are excluded so they don't corrupt the phenology curve.
SEASON_START_MONTH = 4
SEASON_END_MONTH = 10

# Rolling-median screen. A centered window over ordered observations is robust
# to irregular spacing. The screen is DOWNWARD-ONLY: smoke, haze and thin cloud
# depress NDVI but never inflate it in-season, and the residual distribution
# bears this out (heavy negative tail, tight positive side). A point is dropped
# only when it sits below its local median by more than both a robust multiple
# (n_mad x MAD sigma) AND an absolute floor - the floor is what actually bites,
# since the clean series hugs its rolling median so tightly (sigma ~ 0.015)
# that a pure MAD rule would flag ordinary canopy/inter-row scatter the
# Savitzky-Golay step is meant to absorb.
_SCREEN_WINDOW = 7  # observations
_SCREEN_MIN_PERIODS = 3
_SCREEN_N_MAD = 3.5
_SCREEN_ABS_FLOOR = 0.15  # NDVI units below the local median
_MAD_TO_SIGMA = 1.4826

# Daily Savitzky-Golay smoothing.
_SMOOTH_WINDOW_DAYS = 31  # odd; ~one month
_SMOOTH_POLYORDER = 3


def seasonal_observations(
    df: pd.DataFrame, min_valid_frac: float = MIN_VALID_FRAC
) -> pd.DataFrame:
    """Analysis-quality NDVI observations inside the growing-season window.

    Returns columns block_id, date, year, ndvi (block median), sorted by
    block then date. Rows below the quality threshold, without an NDVI, or
    outside April-October are dropped.
    """
    out = df.dropna(subset=["ndvi_median"]).copy()
    out = out[out["valid_frac"] >= min_valid_frac]
    month = out["date"].dt.month
    out = out[(month >= SEASON_START_MONTH) & (month <= SEASON_END_MONTH)]
    out = out.rename(columns={"ndvi_median": "ndvi"})
    out["year"] = out["date"].dt.year
    return (
        out[["block_id", "date", "year", "ndvi"]]
        .sort_values(["block_id", "date"])
        .reset_index(drop=True)
    )


def flag_outliers(
    df: pd.DataFrame,
    window: int = _SCREEN_WINDOW,
    n_mad: float = _SCREEN_N_MAD,
    abs_floor: float = _SCREEN_ABS_FLOOR,
) -> pd.DataFrame:
    """Add an `is_outlier` column marking smoke/haze depressions per season.

    A point is marked only when it falls below its centered rolling median by
    more than both `n_mad` robust sigma and `abs_floor` NDVI units. The screen
    runs per block-season so a window never straddles the winter gap, and is
    downward-only so genuine green-up and plateau structure - which never spikes
    upward relative to its neighborhood - is preserved.
    """
    out = df.sort_values(["block_id", "date"]).copy()

    def _flag(g: pd.DataFrame) -> pd.Series:
        med = g["ndvi"].rolling(window, center=True, min_periods=_SCREEN_MIN_PERIODS).median()
        resid = g["ndvi"] - med
        sigma = _MAD_TO_SIGMA * resid.abs().median()
        threshold = max(n_mad * sigma, abs_floor) if np.isfinite(sigma) else abs_floor
        return resid < -threshold

    flags = [
        _flag(g) for _, g in out.groupby(["block_id", out["date"].dt.year], sort=False)
    ]
    out["is_outlier"] = pd.concat(flags).reindex(out.index).fillna(False)
    return out.reset_index(drop=True)


def _season_bounds(year: int) -> tuple[pd.Timestamp, pd.Timestamp]:
    return (
        pd.Timestamp(year, SEASON_START_MONTH, 1),
        pd.Timestamp(year, SEASON_END_MONTH, 31),
    )


def smooth_series(
    observations: pd.DataFrame,
    window_days: int = _SMOOTH_WINDOW_DAYS,
    polyorder: int = _SMOOTH_POLYORDER,
) -> pd.DataFrame:
    """Daily Savitzky-Golay curve per block per season from screened points.

    `observations` must have block_id, date, ndvi and (from flag_outliers) an
    `is_outlier` column; marked points are dropped before interpolation.
    Season windows with too few clean points to smooth are skipped.

    Returns long columns block_id, year, date, doy, ndvi_smooth (one row per
    day of each block-season).
    """
    kept = observations[~observations.get("is_outlier", False)]
    frames = []
    for (block_id, year), g in kept.groupby(["block_id", observations["date"].dt.year]):
        g = g.sort_values("date")
        season_start, season_end = _season_bounds(int(year))
        # Collapse same-day scenes (adjacent tiles) to their mean before gridding.
        daily = g.groupby("date")["ndvi"].mean()
        if len(daily) < 5:
            continue
        # Clip the grid to the span of real observations so an in-progress or
        # short season is not extrapolated flat to the season boundary (which
        # would fabricate a peak/integral). Leading/trailing fill within this
        # span only bridges the small gap to the first/last real scene.
        start = max(season_start, daily.index.min())
        end = min(season_end, daily.index.max())
        grid = pd.date_range(start, end, freq="D")
        if len(grid) < 5:
            continue
        series = (
            daily.reindex(daily.index.union(grid))
            .interpolate(method="time")
            .reindex(grid)
            .interpolate(method="time", limit_direction="both")
        )
        win = min(window_days, len(series))
        if win % 2 == 0:
            win -= 1
        if win <= polyorder:
            smooth = series.to_numpy(dtype=float)
        else:
            smooth = savgol_filter(series.to_numpy(dtype=float), win, polyorder, mode="interp")
        frames.append(
            pd.DataFrame(
                {
                    "block_id": block_id,
                    "year": int(year),
                    "date": grid,
                    "doy": grid.dayofyear,
                    "ndvi_smooth": smooth,
                }
            )
        )

    if not frames:
        return pd.DataFrame(columns=["block_id", "year", "date", "doy", "ndvi_smooth"])
    return pd.concat(frames, ignore_index=True)


def clean_and_smooth(
    df: pd.DataFrame, min_valid_frac: float = MIN_VALID_FRAC
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run the full Phase 3 cleaning pipeline on a contract timeseries.

    Returns (observations, smoothed): the screened observations with an
    `is_outlier` flag (for plotting what was removed) and the daily smoothed
    curve. Both are re-derivable from the parquet alone.
    """
    observations = flag_outliers(seasonal_observations(df, min_valid_frac))
    smoothed = smooth_series(observations)
    return observations, smoothed
