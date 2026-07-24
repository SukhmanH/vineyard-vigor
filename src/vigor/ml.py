"""Machine-learning layer: season outlook + analog seasons (post-Phase-5).

The Phase 5 statistical alerts work, which is the README's gate for model
upgrades. Two small-data-honest models, pure sklearn/scipy/pandas, offline:

- season_outlook: a Gaussian-process regression per block over (day-of-year ->
  smoothed NDVI), trained on the block's prior VINE seasons (>= its
  baseline_start - pre-planting ground cover never informs a vine projection)
  plus the current season so far. The predictive band for the rest of the
  season is the product; uncertainty is carried to the dashboard, not hidden.
  With one or two prior seasons the band is provisional and says so.

- analog_seasons: nearest-neighbour matching of the current season's smoothed
  curve against every stored block-season on the overlapping day-of-year
  grid. "This season is tracking like 2021" is often the most useful thing a
  model can tell a grower. Pre-planting analogs are kept but flagged.

Everything is re-derivable from block_timeseries.parquet alone.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, ConstantKernel, WhiteKernel

from .clean import clean_and_smooth

SEASON_END_DOY = 304          # Oct 31
INTEGRAL_DOY = (121, 273)     # May 1 - Sep 30 (matches features.integral_may_sep)
BAND_Z = 1.28                 # ~80% central band
TRAIN_STEP = 3                # downsample daily curves for the GP fit
PRED_STEP = 2
MIN_OVERLAP_DAYS = 30         # analog comparisons need at least this much season


def _smoothed_by_season(ts: pd.DataFrame) -> pd.DataFrame:
    """block_id, year, doy, ndvi_smooth - the cleaned daily curves."""
    _, smoothed = clean_and_smooth(ts)
    return smoothed


def _gp() -> GaussianProcessRegressor:
    kernel = (
        ConstantKernel(0.05, (1e-4, 1.0))
        * RBF(length_scale=25.0, length_scale_bounds=(7.0, 90.0))
        + WhiteKernel(noise_level=2e-3, noise_level_bounds=(1e-6, 0.3))
    )
    return GaussianProcessRegressor(kernel=kernel, normalize_y=True, random_state=0)


def season_outlook(
    ts: pd.DataFrame,
    baseline_start: dict[str, int] | None = None,
    latest_year: int | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Project the rest of the current season per block.

    Returns (band, summary):
    band    - block_id, doy, mu, lo, hi for days after the last observation.
    summary - block_id, year, last_obs_doy, n_train_seasons, proj_peak,
              proj_peak_lo, proj_peak_hi, proj_integral, proj_integral_lo,
              proj_integral_hi. Peak combines the observed maximum so far with
              the projected remainder; the integral is May-Sep observed +
              projected (its band is an approximation, labeled as such).
    """
    baseline_start = baseline_start or {}
    sm = _smoothed_by_season(ts)
    if sm.empty:
        return _empty_band(), _empty_summary()
    if latest_year is None:
        latest_year = int(sm["year"].max())

    bands, summaries = [], []
    for block_id, g in sm.groupby("block_id"):
        cur = g[g["year"] == latest_year].sort_values("doy")
        if cur.empty:
            continue
        bstart = int(baseline_start.get(block_id, latest_year))
        prior = g[(g["year"] >= bstart) & (g["year"] < latest_year)]
        last_doy = int(cur["doy"].max())
        if last_doy >= SEASON_END_DOY - 7:
            continue  # season effectively over; nothing meaningful to project

        train = pd.concat([prior.iloc[::TRAIN_STEP], cur.iloc[::2]])
        X = train["doy"].to_numpy(dtype=float).reshape(-1, 1)
        y = train["ndvi_smooth"].to_numpy(dtype=float)
        gp = _gp().fit(X, y)

        doys = np.arange(last_doy + 1, SEASON_END_DOY + 1, PRED_STEP, dtype=float)
        mu, sigma = gp.predict(doys.reshape(-1, 1), return_std=True)
        mu = np.clip(mu, 0.0, 1.0)
        lo = np.clip(mu - BAND_Z * sigma, 0.0, 1.0)
        hi = np.clip(mu + BAND_Z * sigma, 0.0, 1.0)

        bands.append(pd.DataFrame({
            "block_id": block_id, "doy": doys.astype(int),
            "mu": mu, "lo": lo, "hi": hi,
        }))

        obs_peak = float(cur["ndvi_smooth"].max())
        k = int(np.argmax(mu))
        proj_peak = max(obs_peak, float(mu[k]))
        peak_sig = float(sigma[k]) if mu[k] >= obs_peak else 0.0

        i0, i1 = INTEGRAL_DOY
        obs_part = cur[(cur["doy"] >= i0) & (cur["doy"] <= i1)]
        obs_int = float(np.trapezoid(obs_part["ndvi_smooth"], obs_part["doy"])) if len(obs_part) > 1 else 0.0
        m = (doys >= i0) & (doys <= i1)
        proj_int = obs_int + (float(np.trapezoid(mu[m], doys[m])) if m.sum() > 1 else 0.0)
        int_sig = float(np.mean(sigma[m]) * (doys[m].max() - doys[m].min())) if m.sum() > 1 else 0.0

        summaries.append({
            "block_id": block_id, "year": latest_year, "last_obs_doy": last_doy,
            "n_train_seasons": int(prior["year"].nunique()),
            "proj_peak": round(proj_peak, 3),
            "proj_peak_lo": round(max(0.0, proj_peak - BAND_Z * peak_sig), 3),
            "proj_peak_hi": round(min(1.0, proj_peak + BAND_Z * peak_sig), 3),
            "proj_integral": round(proj_int, 1),
            "proj_integral_lo": round(proj_int - BAND_Z * int_sig, 1),
            "proj_integral_hi": round(proj_int + BAND_Z * int_sig, 1),
        })

    band = pd.concat(bands, ignore_index=True) if bands else _empty_band()
    summary = pd.DataFrame(summaries) if summaries else _empty_summary()
    return band, summary


def analog_seasons(
    ts: pd.DataFrame,
    latest_year: int | None = None,
    top_n: int = 5,
    min_overlap: int = MIN_OVERLAP_DAYS,
) -> pd.DataFrame:
    """Rank past block-seasons by similarity to each block's current season.

    Similarity is the mean absolute difference between smoothed curves on the
    overlapping day-of-year grid (>= min_overlap days). Lower is more similar.
    Columns: block_id, analog_block, analog_year, n_days, mean_abs_diff, rank.
    """
    sm = _smoothed_by_season(ts)
    if sm.empty:
        return pd.DataFrame(columns=["block_id", "analog_block", "analog_year",
                                     "n_days", "mean_abs_diff", "rank"])
    if latest_year is None:
        latest_year = int(sm["year"].max())

    curves = {
        (b, int(y)): g.set_index("doy")["ndvi_smooth"]
        for (b, y), g in sm.groupby(["block_id", "year"])
    }
    rows = []
    for block_id in sorted(sm["block_id"].unique()):
        cur = curves.get((block_id, latest_year))
        if cur is None:
            continue
        cands = []
        for (b, y), curve in curves.items():
            if (b, y) == (block_id, latest_year):
                continue
            if y == latest_year and b == block_id:
                continue
            common = cur.index.intersection(curve.index)
            if len(common) < min_overlap:
                continue
            diff = float((cur.loc[common] - curve.loc[common]).abs().mean())
            cands.append({"block_id": block_id, "analog_block": b, "analog_year": y,
                          "n_days": int(len(common)), "mean_abs_diff": round(diff, 4)})
        cands.sort(key=lambda r: r["mean_abs_diff"])
        for i, r in enumerate(cands[:top_n], start=1):
            r["rank"] = i
            rows.append(r)
    return pd.DataFrame(rows, columns=["block_id", "analog_block", "analog_year",
                                       "n_days", "mean_abs_diff", "rank"])


def _empty_band() -> pd.DataFrame:
    return pd.DataFrame(columns=["block_id", "doy", "mu", "lo", "hi"])


def _empty_summary() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "block_id", "year", "last_obs_doy", "n_train_seasons",
        "proj_peak", "proj_peak_lo", "proj_peak_hi",
        "proj_integral", "proj_integral_lo", "proj_integral_hi",
    ])


def write_outlook(band: pd.DataFrame, summary: pd.DataFrame,
                  analogs: pd.DataFrame, processed_dir) -> None:
    from pathlib import Path

    d = Path(processed_dir)
    d.mkdir(parents=True, exist_ok=True)
    band.to_parquet(d / "season_outlook.parquet", index=False)
    summary.to_parquet(d / "outlook_summary.parquet", index=False)
    analogs.to_parquet(d / "season_analogs.parquet", index=False)
