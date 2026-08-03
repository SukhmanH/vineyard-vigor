"""Offline tests for the single blocks.geojson reader (blocks.py).

The point of this module is that nothing else reads the file. Peer grouping
in vigor_alerts matches variety strings exactly, so a module that read the
geojson directly and saw a raw "mustek" would split a peer group without
raising anything - the failure mode is silent, hence the guard test at the
bottom.
"""

import json
from pathlib import Path

import pandas as pd
import pytest

from vigor import blocks

SRC = Path(blocks.__file__).resolve().parent
SCRIPTS = SRC.parents[1] / "scripts"


def _geojson(tmp_path: Path, features: list[dict]) -> Path:
    doc = {"type": "FeatureCollection", "features": []}
    for i, props in enumerate(features):
        doc["features"].append({
            "type": "Feature",
            "properties": props,
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-119.5 + i, 49.1], [-119.4 + i, 49.1],
                    [-119.4 + i, 49.2], [-119.5 + i, 49.2],
                    [-119.5 + i, 49.1],
                ]],
            },
        })
    p = tmp_path / "blocks.geojson"
    p.write_text(json.dumps(doc), encoding="utf-8")
    return p


def test_variety_spellings_are_merged(tmp_path):
    p = _geojson(tmp_path, [
        {"block_id": "a", "site": "Oliver", "variety": "Mustak"},
        {"block_id": "b", "site": "oliver", "variety": "mustak"},
        {"block_id": "c", "site": "OLIVER", "variety": "mustek"},
    ])
    meta = blocks.block_meta(p)
    assert set(meta["variety"]) == {"Mustak"}
    assert set(meta["site"]) == {"Oliver"}


def test_unknown_variety_is_title_cased_not_dropped(tmp_path):
    p = _geojson(tmp_path, [{"block_id": "a", "site": "Penticton", "variety": "mar"}])
    assert blocks.block_meta(p)["variety"].iloc[0] == "Mar"


def test_whitespace_in_property_keys_is_stripped(tmp_path):
    p = _geojson(tmp_path, [{"block_id ": "a", " site": "Oliver", "variety": "chard"}])
    meta = blocks.block_meta(p)
    assert "block_id" in meta.columns and "site" in meta.columns
    assert meta["variety"].iloc[0] == "Chardonnay"


def test_missing_variety_column_is_tolerated(tmp_path):
    p = _geojson(tmp_path, [{"block_id": "a", "site": "Oliver"}])
    meta = blocks.block_meta(p)
    assert "variety" not in meta.columns
    assert meta["block_id"].iloc[0] == "a"


def test_load_block_frame_stays_wgs84(tmp_path):
    p = _geojson(tmp_path, [{"block_id": "a", "site": "Oliver", "variety": "Mustak"}])
    gdf = blocks.load_block_frame(p)
    assert gdf.crs.to_epsg() == 4326
    assert gdf.geometry.iloc[0].geom_type == "Polygon"


def test_default_path_points_at_the_repo_data_file():
    assert blocks.DEFAULT_BLOCKS_PATH.name == "blocks.geojson"
    assert blocks.DEFAULT_BLOCKS_PATH.parent.name == "data"


def test_blocks_module_is_the_only_geojson_reader():
    """Guard the structural invariant: one reader, one canonicalisation.

    A module that calls gpd.read_file on the block polygons itself bypasses
    the alias map, and the resulting peer-group split is silent.
    """
    offenders = []
    for path in list(SRC.glob("*.py")) + list(SCRIPTS.glob("*.py")):
        if path.name == "blocks.py":
            continue
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), 1):
            if "read_file" in line and not line.lstrip().startswith("#"):
                offenders.append(f"{path.name}:{lineno}")
    assert not offenders, (
        "these read block polygons directly instead of via vigor.blocks: "
        + ", ".join(offenders)
    )
