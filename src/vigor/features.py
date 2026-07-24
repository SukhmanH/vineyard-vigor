"""Per-season per-block phenology features (Phase 3).

Pure pandas/numpy; must run offline. Features are read off the daily smoothed
curve produced by clean.smooth_series, so they are re-derivable from the
parquet alone.

Features, one row per (block_id, year):
- peak_ndvi   : maximum of the smoothed curve over the season.
- peak_doy    : day of year at that maximum.
- integral_may_sep : area under the smoothed curve, May 1 - Sep 30, in
                     NDVI*days (trapezoidal, daily step).
- greenup_doy : day of year the curve first rises to the midpoint between its
                pre-peak seasonal base and the peak (amplitude half-max, a
                standard phenology threshold); NaN when the season has no real
                green-up amplitude (e.g. bare ground).
- greenup_date: the same instant as an ISO date.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Integral window (README: "May-September integral").
_INTEGRAL_START = (5, 1)   # May 1
_INTEGRAL_END = (9, 30)    # Sep 30

# Green-up amplitude threshold: fraction of the base->peak rise.
_GREENUP_FRACTION = 0.5
# Below this base->peak amplitude the season has no meaningful green-up.
_MIN_AMPLITUDE = 0.10
# Fraction of the May-Sep window the smoothed curve must cover to report the
# integral (guards partial/in-progress seasons).
_MIN_INTEGRAL_COVERAGE = 0.9


def _season_features(g: pd.DataFrame) -> pd.Series:
    g = g.sort_values("date").reset_index(drop=True)
    ndvi = g["ndvi_smooth"].to_numpy(dtype=float)
    doy = g["doy"].to_numpy()
    dates = g["date"]
    year = int(dates.iloc[0].year)

    peak_idx = int(np.argmax(ndvi))
    peak_ndvi = float(ndvi[peak_idx])
    peak_doy = int(doy[peak_idx])

    # Green-up: base is the pre-peak minimum; threshold is halfway to the peak.
    pre_peak = ndvi[: peak_idx + 1]
    base = float(pre_peak.min())
    amplitude = peak_ndvi - base
    if amplitude >= _MIN_AMPLITUDE:
        threshold = base + _GREENUP_FRACTION * amplitude
        crossed = np.nonzero(pre_peak >= threshold)[0]
        greenup_i = int(crossed[0]) if len(crossed) else peak_idx
        greenup_doy = int(doy[greenup_i])
        greenup_date = dates.iloc[greenup_i].date().isoformat()
    else:
        greenup_doy = np.nan
        greenup_date = None

    start = pd.Timestamp(year, *_INTEGRAL_START)
    end = pd.Timestamp(year, *_INTEGRAL_END)
    window = (dates >= start) & (dates <= end)
    expected_days = (end - start).days + 1
    # Only report the May-Sep integral when the smoothed curve actually spans
    # (almost) the whole window; a partial/in-progress season would otherwise
    # yield a truncated area that reads as a low integral.
    if window.sum() >= _MIN_INTEGRAL_COVERAGE * expected_days:
        # Daily grid -> trapezoid in NDVI*days.
        integral = float(np.trapezoid(ndvi[window.to_numpy()]))
    else:
        integral = np.nan

    return pd.Series(
        {
            "peak_ndvi": peak_ndvi,
            "peak_doy": peak_doy,
            "integral_may_sep": integral,
            "greenup_doy": greenup_doy,
            "greenup_date": greenup_date,
        }
    )


def seasonal_features(smoothed: pd.DataFrame) -> pd.DataFrame:
    """Compute per-(block_id, year) phenology features from the smoothed curve.

    `smoothed` is the output of clean.smooth_series (columns block_id, year,
    date, doy, ndvi_smooth). Returns one row per block-season, sorted by block
    then year.
    """
    if smoothed.empty:
        return pd.DataFrame(
            columns=[
                "block_id", "year", "peak_ndvi", "peak_doy",
                "integral_may_sep", "greenup_doy", "greenup_date",
            ]
        )
    feats = (
        smoothed.groupby(["block_id", "year"], sort=True)
        .apply(_season_features, include_groups=False)
        .reset_index()
    )
    return feats


def write_features(df: pd.DataFrame, path) -> "Path":  # type: ignore[name-defined]
    from pathlib import Path

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return path
