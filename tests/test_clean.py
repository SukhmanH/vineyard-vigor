"""Offline tests for the Phase 3 cleaning pipeline (clean.py).

No Earth Engine. Uses synthetic seasons and the cached fixture; every test
runs offline.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from vigor import clean, ingest

FIXTURE = Path(__file__).parent / "fixtures" / "sample_extract.csv"

needs_fixture = pytest.mark.skipif(
    not FIXTURE.exists(),
    reason="tests/fixtures/sample_extract.csv not generated yet",
)


def _synthetic_season(year: int = 2023, block_id: str = "b1", n: int = 40, seed: int = 0):
    """A clean bell-shaped growing season with one deep smoke dropout in August."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range(f"{year}-04-05", f"{year}-10-25", periods=n)
    doy = dates.dayofyear.to_numpy()
    # Smooth arch peaking mid-August (doy ~225).
    ndvi = 0.25 + 0.55 * np.exp(-((doy - 225) ** 2) / (2 * 45.0**2))
    ndvi = ndvi + rng.normal(0, 0.01, n)
    smoke_i = int(np.argmin(np.abs(doy - 220)))
    ndvi[smoke_i] -= 0.30  # deep, isolated depression
    return pd.DataFrame(
        {
            "block_id": block_id,
            "date": dates,
            "ndvi_median": ndvi,
            "ndvi_p10": ndvi - 0.05,
            "ndvi_p90": ndvi + 0.05,
            "ndre_median": ndvi * 0.6,
            "valid_frac": 1.0,
        }
    ), smoke_i, dates[smoke_i]


def test_seasonal_observations_filters_window_and_quality():
    df = pd.DataFrame(
        {
            "block_id": ["b1", "b1", "b1", "b1"],
            "date": pd.to_datetime(["2023-01-15", "2023-07-01", "2023-07-05", "2023-07-10"]),
            "ndvi_median": [0.2, 0.7, 0.72, np.nan],
            "valid_frac": [1.0, 1.0, 0.5, 1.0],
        }
    )
    out = clean.seasonal_observations(df)
    # Dropped: January (out of season), the 0.5 valid_frac row, and the NaN NDVI.
    assert len(out) == 1
    assert out.iloc[0]["date"] == pd.Timestamp("2023-07-01")
    assert "ndvi" in out.columns and "year" in out.columns


def test_flag_outliers_catches_smoke_dropout():
    df, smoke_i, smoke_date = _synthetic_season()
    obs = clean.flag_outliers(clean.seasonal_observations(df))
    flagged = obs[obs["is_outlier"]]
    assert smoke_date in set(flagged["date"]), "deep August dropout should be flagged"
    # A clean bell curve should not shed many points.
    assert obs["is_outlier"].mean() < 0.15


def test_flag_outliers_is_downward_only():
    df, _, _ = _synthetic_season(seed=1)
    # Inject an upward spike; it must NOT be flagged (screen is downward-only).
    up_date = df["date"].iloc[10]
    df.loc[10, "ndvi_median"] += 0.30
    obs = clean.flag_outliers(clean.seasonal_observations(df))
    assert up_date not in set(obs[obs["is_outlier"]]["date"])


def test_smooth_series_daily_grid_within_observation_span():
    df, _, _ = _synthetic_season()
    obs = clean.flag_outliers(clean.seasonal_observations(df))
    sm = clean.smooth_series(obs)
    assert not sm.empty
    assert (sm["ndvi_smooth"].between(0, 1)).all()
    # Daily spacing.
    d = sm.sort_values("date")["date"].diff().dropna().dt.days
    assert (d == 1).all()
    # No extrapolation past the last real observation.
    assert sm["date"].max() <= df["date"].max()


def test_smooth_series_skips_sparse_seasons():
    df, _, _ = _synthetic_season(n=4)  # too few points
    obs = clean.flag_outliers(clean.seasonal_observations(df))
    sm = clean.smooth_series(obs)
    assert sm.empty


@needs_fixture
def test_clean_and_smooth_on_fixture_runs_offline():
    ts = ingest.raw_to_timeseries(pd.read_csv(FIXTURE))
    obs, sm = clean.clean_and_smooth(ts)
    assert not obs.empty and not sm.empty
    assert 0 < obs["is_outlier"].mean() < 0.20  # a sane smoke/haze rate
    assert sm["ndvi_smooth"].between(-0.1, 1.0).all()
