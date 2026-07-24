"""Offline tests for Phase 3 seasonal features (features.py).

No Earth Engine. Builds a known smoothed curve and checks each feature, then
exercises the fixture end-to-end offline.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from vigor import clean, features, ingest

FIXTURE = Path(__file__).parent / "fixtures" / "sample_extract.csv"

needs_fixture = pytest.mark.skipif(
    not FIXTURE.exists(),
    reason="tests/fixtures/sample_extract.csv not generated yet",
)


def _known_curve(year: int = 2023, peak_doy: int = 213, peak: float = 0.85, base: float = 0.25):
    """A full April-October daily arch with a known peak and amplitude."""
    dates = pd.date_range(f"{year}-04-01", f"{year}-10-31", freq="D")
    doy = dates.dayofyear.to_numpy()
    ndvi = base + (peak - base) * np.exp(-((doy - peak_doy) ** 2) / (2 * 40.0**2))
    return pd.DataFrame(
        {"block_id": "b1", "year": year, "date": dates, "doy": doy, "ndvi_smooth": ndvi}
    )


def test_peak_matches_curve():
    feats = features.seasonal_features(_known_curve(peak_doy=213, peak=0.85))
    row = feats.iloc[0]
    assert abs(row["peak_ndvi"] - 0.85) < 1e-6
    assert abs(row["peak_doy"] - 213) <= 1


def test_greenup_precedes_peak_and_is_near_half_max():
    curve = _known_curve(peak_doy=213, peak=0.85, base=0.25)
    feats = features.seasonal_features(curve)
    row = feats.iloc[0]
    assert row["greenup_doy"] < row["peak_doy"]
    # At green-up the smoothed value should be ~halfway up the amplitude.
    gu = curve[curve["doy"] == row["greenup_doy"]]["ndvi_smooth"].iloc[0]
    assert abs(gu - (0.25 + 0.5 * (0.85 - 0.25))) < 0.05


def test_flat_curve_has_no_greenup():
    dates = pd.date_range("2023-04-01", "2023-10-31", freq="D")
    flat = pd.DataFrame(
        {"block_id": "b1", "year": 2023, "date": dates,
         "doy": dates.dayofyear, "ndvi_smooth": 0.30}
    )
    feats = features.seasonal_features(flat)
    assert pd.isna(feats.iloc[0]["greenup_doy"])


def test_integral_reported_for_full_season_and_positive():
    feats = features.seasonal_features(_known_curve())
    val = feats.iloc[0]["integral_may_sep"]
    assert np.isfinite(val) and val > 0


def test_integral_nan_for_partial_season():
    # Only May available -> below the coverage threshold.
    curve = _known_curve()
    partial = curve[curve["date"].dt.month == 5]
    feats = features.seasonal_features(partial)
    assert pd.isna(feats.iloc[0]["integral_may_sep"])


@needs_fixture
def test_features_on_fixture_offline():
    ts = ingest.raw_to_timeseries(pd.read_csv(FIXTURE))
    _, sm = clean.clean_and_smooth(ts)
    feats = features.seasonal_features(sm)
    assert not feats.empty
    assert feats["peak_ndvi"].between(0, 1).all()
    gu = feats.dropna(subset=["greenup_doy"])
    assert (gu["greenup_doy"].to_numpy() <= gu["peak_doy"].to_numpy()).all()
    assert set(["block_id", "year", "peak_ndvi", "peak_doy",
                "integral_may_sep", "greenup_doy", "greenup_date"]).issubset(feats.columns)
