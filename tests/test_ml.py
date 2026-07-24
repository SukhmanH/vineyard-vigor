"""Offline tests for the ML layer (season outlook + analog seasons).

Synthetic contract timeseries only - no Earth Engine, no network.
"""

import numpy as np
import pandas as pd

from vigor import ml


def _season(block_id, year, peak=0.75, noise=0.0, end_doy=304, seed=0):
    """One synthetic block-season of contract rows: a smooth green-up arc."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range(f"{year}-04-05", f"{year}-12-31", freq="5D")
    dates = dates[dates.dayofyear <= end_doy]
    doy = dates.dayofyear.to_numpy()
    curve = 0.2 + (peak - 0.2) * np.sin(np.clip((doy - 95) / (250 - 95), 0, 1) * np.pi) ** 2
    curve = np.clip(curve + rng.normal(0, noise, len(doy)), 0, 1)
    return pd.DataFrame({
        "block_id": block_id, "date": dates,
        "scene_id": [f"{block_id}-{year}-{i}" for i in range(len(dates))],
        "ndvi_median": curve, "ndvi_p10": curve - 0.05, "ndvi_p90": curve + 0.05,
        "ndre_median": curve * 0.6, "valid_frac": 1.0,
    })


def _ts(partial_end=200):
    """Two full prior seasons plus a partial current season."""
    return pd.concat([
        _season("b1", 2024, peak=0.78, noise=0.01, seed=1),
        _season("b1", 2025, peak=0.72, noise=0.01, seed=2),
        _season("b1", 2026, peak=0.75, noise=0.01, end_doy=partial_end, seed=3),
    ], ignore_index=True)


def test_outlook_projects_rest_of_season():
    band, summary = ml.season_outlook(_ts(), baseline_start={"b1": 2024})
    assert not band.empty and not summary.empty
    b = band[band["block_id"] == "b1"]
    s = summary.iloc[0]
    # projection starts after the last observation and runs to season end
    assert b["doy"].min() > s["last_obs_doy"]
    assert b["doy"].max() >= ml.SEASON_END_DOY - ml.PRED_STEP
    # band ordering and range sanity
    assert (b["lo"] <= b["mu"]).all() and (b["mu"] <= b["hi"]).all()
    assert b[["lo", "mu", "hi"]].min().min() >= 0.0
    assert b[["lo", "mu", "hi"]].max().max() <= 1.0
    # trained on the two prior vine seasons; peak lands in a plausible range
    assert s["n_train_seasons"] == 2
    assert 0.5 < s["proj_peak"] < 0.95
    assert s["proj_peak_lo"] <= s["proj_peak"] <= s["proj_peak_hi"]
    assert s["proj_integral"] > 0


def test_outlook_respects_baseline_start():
    """Pre-planting seasons must not count as training seasons."""
    _, summary = ml.season_outlook(_ts(), baseline_start={"b1": 2025})
    assert summary.iloc[0]["n_train_seasons"] == 1


def test_outlook_skips_finished_seasons():
    ts = pd.concat([_season("b1", 2024), _season("b1", 2025)], ignore_index=True)
    band, summary = ml.season_outlook(ts, baseline_start={"b1": 2024})
    assert band.empty and summary.empty  # latest season already ran to Oct 31


def test_analogs_rank_the_lookalike_first():
    # 2025 is deliberately shaped like the 2026 partial season; 2024 is not.
    ts = pd.concat([
        _season("b1", 2024, peak=0.45, seed=4),
        _season("b1", 2025, peak=0.75, seed=5),
        _season("b1", 2026, peak=0.75, end_doy=200, seed=6),
    ], ignore_index=True)
    out = ml.analog_seasons(ts)
    top = out[(out["block_id"] == "b1") & (out["rank"] == 1)].iloc[0]
    assert top["analog_year"] == 2025
    assert top["n_days"] >= ml.MIN_OVERLAP_DAYS
    ranked = out[out["block_id"] == "b1"].sort_values("rank")
    assert ranked["mean_abs_diff"].is_monotonic_increasing


def test_ml_writers_roundtrip(tmp_path):
    band, summary = ml.season_outlook(_ts(), baseline_start={"b1": 2024})
    analogs = ml.analog_seasons(_ts())
    ml.write_outlook(band, summary, analogs, tmp_path)
    for name in ("season_outlook", "outlook_summary", "season_analogs"):
        assert (tmp_path / f"{name}.parquet").exists()
        assert len(pd.read_parquet(tmp_path / f"{name}.parquet")) >= 0
