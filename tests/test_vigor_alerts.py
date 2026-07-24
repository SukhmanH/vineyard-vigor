"""Offline tests for Phase 5 low-vigor alerts (vigor_alerts.py).

No Earth Engine. Synthetic multi-year seasons with a controlled low-vigor
year, plus a multi-block/variety set for the same-variety comparison.
"""

import numpy as np
import pandas as pd

from vigor import vigor_alerts


def _season(block_id, year, level, n=24, seed=0, noise=0.04):
    """An in-season NDVI series around `level` with realistic scatter, valid,
    inside the window. Real 10 m block-median NDVI carries ~0.04 season noise;
    a near-flat synthetic season would give a degenerate p10 baseline."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range(f"{year}-04-10", f"{year}-10-20", periods=n)
    return pd.DataFrame(
        {
            "block_id": block_id,
            "date": dates,
            "ndvi_median": level + rng.normal(0, noise, n),
            "valid_frac": 1.0,
        }
    )


def _history(block_id, normal_level=0.6, years=range(2019, 2024), seed=0):
    return pd.concat(
        [_season(block_id, y, normal_level, seed=seed + y) for y in years],
        ignore_index=True,
    )


def test_flat_healthy_season_not_marked():
    # Five normal baseline years, then another normal year.
    df = pd.concat([_history("b1"), _season("b1", 2024, 0.60, seed=99)], ignore_index=True)
    al = vigor_alerts.below_baseline_seasons(df)
    current = al[al["year"] == 2024]
    assert not current["below_baseline"].any()


def test_depressed_season_is_marked():
    # A clearly depressed 2024 season should trip the two-consecutive rule.
    df = pd.concat([_history("b1"), _season("b1", 2024, 0.30, seed=7)], ignore_index=True)
    al = vigor_alerts.below_baseline_seasons(df)
    current = al[al["year"] == 2024]
    assert current["below_baseline"].any()
    # Essentially the whole depressed season is below p10.
    assert current["below_p10"].fillna(False).mean() > 0.8


def test_no_baseline_years_are_not_judged():
    # 2019 is the floor; it has no prior seasons, so nothing is judgeable.
    df = pd.concat([_history("b1"), _season("b1", 2024, 0.30)], ignore_index=True)
    al = vigor_alerts.below_baseline_seasons(df)
    first = al[al["year"] == 2019]
    assert first["below_p10"].isna().all()
    assert not first["below_baseline"].any()


def test_single_dip_not_marked_needs_two_consecutive():
    # Season sits well above baseline (noise won't cross p10) except one deep dip.
    df = _history("b1", normal_level=0.6)
    season = _season("b1", 2024, 0.75, seed=5, noise=0.01).sort_values("date").reset_index(drop=True)
    season.loc[5, "ndvi_median"] = 0.10  # one isolated deep dip
    df = pd.concat([df, season], ignore_index=True)
    al = vigor_alerts.below_baseline_seasons(df)
    current = al[al["year"] == 2024].sort_values("date").reset_index(drop=True)
    # Exactly one point below p10, and with no below-neighbor it isn't marked.
    assert current["below_p10"].fillna(False).sum() == 1
    assert not current["below_baseline"].any()


def test_baseline_start_suppresses_early_baseline():
    df = pd.concat([_history("b1"), _season("b1", 2024, 0.30, seed=7)], ignore_index=True)
    al = vigor_alerts.below_baseline_seasons(df, baseline_start={"b1": 2024})
    # With the floor at 2024 there is no admissible prior season for 2024.
    assert al[al["year"] == 2024]["below_p10"].isna().all()


def test_compare_weather_vs_single_block():
    blocks = pd.DataFrame(
        {"block_id": ["m1", "m2"], "variety": ["merlot", "merlot"]}
    )
    # Both merlot blocks healthy through 2023; in 2024 only m1 is depressed.
    df = pd.concat(
        [
            _history("m1", seed=1), _history("m2", seed=2),
            _season("m1", 2024, 0.30, seed=3),   # m1 down
            _season("m2", 2024, 0.60, seed=4),   # m2 fine
        ],
        ignore_index=True,
    )
    al = vigor_alerts.below_baseline_seasons(df)
    cc = vigor_alerts.compare_same_variety(al, blocks)
    row = cc[(cc["year"] == 2024)].iloc[0]
    assert row["reading"] == "single-block"  # one of two down

    # Now both down in 2024 => weather.
    df2 = pd.concat(
        [
            _history("m1", seed=1), _history("m2", seed=2),
            _season("m1", 2024, 0.30, seed=3),
            _season("m2", 2024, 0.30, seed=4),
        ],
        ignore_index=True,
    )
    cc2 = vigor_alerts.compare_same_variety(vigor_alerts.below_baseline_seasons(df2), blocks)
    assert cc2[cc2["year"] == 2024].iloc[0]["reading"] == "weather"


def test_compare_no_peers_for_lone_variety():
    blocks = pd.DataFrame({"block_id": ["b1"], "variety": ["chardonnay"]})
    df = pd.concat([_history("b1"), _season("b1", 2024, 0.30, seed=7)], ignore_index=True)
    cc = vigor_alerts.compare_same_variety(vigor_alerts.below_baseline_seasons(df), blocks)
    assert (cc["reading"] == "no peers").all()


def test_stress_events_shape():
    df = pd.concat([_history("b1"), _season("b1", 2024, 0.30, seed=7)], ignore_index=True)
    ev = vigor_alerts.stress_events(vigor_alerts.below_baseline_seasons(df))
    assert list(ev.columns) == ["block_id", "year", "n_low", "first_low", "last_low", "min_ndvi"]
    # The deeply depressed 2024 season must appear (other noisy years may too).
    row = ev[ev["year"] == 2024]
    assert len(row) == 1
    assert row["min_ndvi"].iloc[0] < 0.4
