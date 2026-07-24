"""Offline tests for the Phase 6 dashboards.

No Earth Engine, no network. Builds synthetic processed parquets in a tmp dir
and asserts a self-contained HTML file is produced. Covers both the interactive
builder (webdash, primary) and the static image builder (dashboard, fallback).
"""

import json
import re

import numpy as np
import pandas as pd

from vigor import dashboard, webdash


def _blocks_geojson(path):
    path.write_text(
        '{"type":"FeatureCollection","features":[{"type":"Feature",'
        '"properties":{"block_id":"b1","site":"oliver","variety":"merlot",'
        '"planting_year":2024,"baseline_start":2024},'
        '"geometry":{"type":"Polygon","coordinates":[[[-119.54,49.20],'
        '[-119.53,49.20],[-119.53,49.21],[-119.54,49.21],[-119.54,49.20]]]}}]}',
        encoding="utf-8",
    )


def _write_processed(processed, with_alerts=False, with_zones=False):
    processed.mkdir(parents=True, exist_ok=True)
    dates = pd.date_range("2023-04-05", "2023-10-25", periods=30)
    ndvi = np.linspace(0.3, 0.8, len(dates))
    ts = pd.DataFrame(
        {
            "block_id": "b1", "date": dates,
            "scene_id": [f"s{i}" for i in range(len(dates))],
            "ndvi_median": ndvi, "ndvi_p10": ndvi - 0.05, "ndvi_p90": ndvi + 0.05,
            "ndre_median": ndvi * 0.6, "valid_frac": 1.0,
        }
    )
    ts.to_parquet(processed / "block_timeseries.parquet", index=False)

    feats = pd.DataFrame(
        {"block_id": ["b1"], "year": [2023], "peak_ndvi": [0.8], "peak_doy": [270],
         "integral_may_sep": [95.0], "greenup_doy": [140], "greenup_date": ["2023-05-20"]}
    )
    feats.to_parquet(processed / "season_features.parquet", index=False)

    if with_alerts:
        al = pd.DataFrame(
            {
                "block_id": "b1", "date": dates, "year": 2023,
                "doy": dates.dayofyear, "ndvi": ndvi,
                "base_p10": ndvi - 0.1, "base_median": ndvi, "base_p25": ndvi - 0.05,
                "base_p75": ndvi + 0.05, "n_baseline": 10,
                "below_p10": False, "below_baseline": [True, True] + [False] * (len(dates) - 2),
            }
        )
        al.to_parquet(processed / "vigor_alerts.parquet", index=False)

    if with_zones:
        rng = np.random.default_rng(0)
        z = pd.DataFrame(
            {
                "block_id": "b1", "year": 2023,
                "m04": 0.3, "m05": 0.4, "m06": 0.5, "m07": 0.6, "m08": 0.6, "m09": 0.5, "m10": 0.4,
                "lon": rng.uniform(-119.54, -119.53, 20),
                "lat": rng.uniform(49.20, 49.21, 20),
                "zone": rng.integers(0, 3, 20),
                "mean_ndvi": rng.uniform(0.3, 0.7, 20),
            }
        )
        z.to_parquet(processed / "vigor_zones.parquet", index=False)


def _embedded_json(html: str) -> dict:
    m = re.search(r"const DATA = (\{.*?\});\nconst \$", html, re.DOTALL)
    assert m, "embedded DATA payload not found"
    return json.loads(m.group(1))


def test_interactive_dashboard_is_self_contained(tmp_path):
    processed = tmp_path / "processed"
    _write_processed(processed, with_alerts=True, with_zones=True)
    blocks_path = tmp_path / "blocks.geojson"
    _blocks_geojson(blocks_path)

    out = webdash.build_dashboard(processed, blocks_path, tmp_path / "dash")
    text = out.read_text(encoding="utf-8")

    assert out.name == "index.html"
    assert text.startswith("<!doctype html>")
    assert "Vineyard Vigor Dashboard" in text
    # Interactive, not static images: data embedded as JSON, no external hosts,
    # no leftover template tokens, no base64 PNGs.
    assert "const DATA = " in text
    assert 'src="http' not in text and "cdn" not in text.lower()
    assert "__DATA__" not in text and "__CSS__" not in text and "__JS__" not in text
    assert "data:image/png;base64," not in text


def test_interactive_payload_has_expected_shape(tmp_path):
    processed = tmp_path / "processed"
    _write_processed(processed, with_alerts=True, with_zones=True)
    blocks_path = tmp_path / "blocks.geojson"
    _blocks_geojson(blocks_path)

    out = webdash.build_dashboard(processed, blocks_path, tmp_path / "dash")
    data = _embedded_json(out.read_text(encoding="utf-8"))

    assert data["blocks"] == ["b1"]
    assert "2023" in data["timeseries"]["b1"]
    assert data["kpis"]["b1"]["latest_ndvi"] is not None
    assert data["kpis"]["b1"]["active_alerts"] == 2  # two below-baseline obs in the fixture
    assert data["zones"]["b1"]["2023"]  # pixel points present
    assert any(f["block_id"] == "b1" for f in data["features"])


def test_interactive_dashboard_without_optional_parquets(tmp_path):
    processed = tmp_path / "processed"
    _write_processed(processed)  # timeseries + features only
    blocks_path = tmp_path / "blocks.geojson"
    _blocks_geojson(blocks_path)

    out = webdash.build_dashboard(processed, blocks_path, tmp_path / "dash")
    data = _embedded_json(out.read_text(encoding="utf-8"))
    assert data["baseline"] == {} and data["zones"] == {}
    assert data["kpis"]["b1"]["active_alerts"] == 0


def test_static_dashboard_still_builds(tmp_path):
    processed = tmp_path / "processed"
    _write_processed(processed)
    blocks_path = tmp_path / "blocks.geojson"
    _blocks_geojson(blocks_path)

    out = dashboard.build_dashboard(processed, blocks_path, tmp_path / "static")
    text = out.read_text(encoding="utf-8")
    assert text.startswith("<!doctype html>")
    assert "data:image/png;base64," in text  # static builder embeds PNGs
