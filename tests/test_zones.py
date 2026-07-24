"""Offline tests for Phase 4 vigor zoning (zones.py).

No Earth Engine. Synthetic per-pixel profiles with known vigor structure.
"""

import numpy as np
import pandas as pd

from vigor import zones

BANDS = [f"m{m:02d}" for m in range(4, 11)]


def _synthetic_pixels(block_id="b1", year=2023, seed=0):
    """Two clear vigor groups: a low-vigor patch and a high-vigor patch."""
    rng = np.random.default_rng(seed)
    low = 0.30 + rng.normal(0, 0.01, (40, len(BANDS)))
    high = 0.65 + rng.normal(0, 0.01, (60, len(BANDS)))
    X = np.vstack([low, high])
    df = pd.DataFrame(X, columns=BANDS)
    df["block_id"] = block_id
    df["year"] = year
    df["lon"] = rng.uniform(-119.57, -119.56, len(df))
    df["lat"] = rng.uniform(49.50, 49.51, len(df))
    return df


def test_zone_labels_ordered_low_to_high():
    zoned = zones.zone_block_season(_synthetic_pixels(), k=3)
    means = zoned.groupby("zone")["mean_ndvi"].mean()
    # Zone means must increase with zone id (0 = lowest vigor).
    assert list(means.index) == sorted(means.index)
    assert means.is_monotonic_increasing


def test_zone_separates_known_groups():
    zoned = zones.zone_block_season(_synthetic_pixels(), k=2)
    # The low patch (~0.30) and high patch (~0.65) should land in different zones.
    lo = zoned[zoned["mean_ndvi"] < 0.45]["zone"].unique()
    hi = zoned[zoned["mean_ndvi"] > 0.55]["zone"].unique()
    assert len(lo) == 1 and len(hi) == 1 and lo[0] != hi[0]


def test_too_few_pixels_returns_empty():
    tiny = _synthetic_pixels().head(5)
    assert zones.zone_block_season(tiny, k=3).empty


def test_pixels_with_missing_month_dropped():
    df = _synthetic_pixels()
    df.loc[0, "m07"] = np.nan
    zoned = zones.zone_block_season(df, k=3)
    assert len(zoned) == len(df) - 1


def test_zone_all_covers_every_block_season():
    a = _synthetic_pixels(block_id="a1", year=2023, seed=1)
    b = _synthetic_pixels(block_id="b1", year=2024, seed=2)
    zoned = zones.zone_all(pd.concat([a, b], ignore_index=True), k=3)
    got = set(map(tuple, zoned[["block_id", "year"]].drop_duplicates().to_numpy()))
    assert got == {("a1", 2023), ("b1", 2024)}


def test_zone_summary_shape():
    zoned = zones.zone_all(_synthetic_pixels(), k=3)
    summary = zones.zone_summary(zoned)
    assert list(summary.columns) == ["block_id", "year", "zone", "n_pixels", "mean_ndvi"]
    assert summary["n_pixels"].sum() == len(zoned)


def test_deterministic():
    px = _synthetic_pixels()
    a = zones.zone_block_season(px, k=3)
    b = zones.zone_block_season(px, k=3)
    pd.testing.assert_frame_equal(a, b)
