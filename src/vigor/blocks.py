"""The single reader for blocks.geojson.

Every consumer of block metadata goes through here, so the file path and the
spelling canonicalisation are defined exactly once. Peer grouping matches
variety strings exactly, so a module that read the geojson directly and saw a
raw "mustek" would silently split a peer group - which is what happened
before this module existed.

Deliberately geopandas-only, no Earth Engine import: the dashboard and the
offline analysis modules need block metadata but must stay runnable without
`ee` installed or authenticated. extract.py layers the projection, edge
buffer and pixel-count logic on top of `load_block_frame`.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd

# The repo-relative location of the block polygons. Callers pass a path only
# when they genuinely have a different file (tests, alternate vineyards);
# everything in the pipeline takes this default so no module hardcodes it.
DEFAULT_BLOCKS_PATH = Path(__file__).resolve().parents[2] / "data" / "blocks.geojson"

WGS84 = "EPSG:4326"

META_COLUMNS = ["block_id", "site", "variety", "planting_year", "baseline_start"]

# Hand-drawn geojson carries whatever the draw tool was handed, so one variety
# arrives spelled several ways. Keys are lowercased; anything absent is
# title-cased and otherwise left alone.
#
# NOTE: "mustek" is treated as a misspelling of "mustak". If they are in fact
# different varieties, remove that line - merging them would invent peers that
# do not exist.
VARIETY_ALIASES = {
    "mustak": "Mustak",
    "mustek": "Mustak",
    "chard": "Chardonnay",
}


def canonical_variety(value: object) -> object:
    """Collapse spelling and case variants of a variety name."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return value
    key = str(value).strip().lower()
    if not key:
        return value
    return VARIETY_ALIASES.get(key, str(value).strip().title())


def canonical_site(value: object) -> object:
    """Site names differ only by case and stray whitespace in practice."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return value
    return str(value).strip().title() or value


def load_block_frame(path: str | Path | None = None) -> gpd.GeoDataFrame:
    """Read blocks.geojson in WGS84 with names canonicalised.

    Column names are stripped first - hand-drawn properties sometimes arrive
    as "block_id " - then site and variety are normalised. No projection or
    buffering happens here; that is extract.load_blocks' job.
    """
    gdf = gpd.read_file(Path(path) if path is not None else DEFAULT_BLOCKS_PATH)
    gdf.columns = gdf.columns.str.strip()

    if "site" in gdf.columns:
        gdf["site"] = gdf["site"].map(canonical_site)
    if "variety" in gdf.columns:
        gdf["variety"] = gdf["variety"].map(canonical_variety)
    return gdf


def block_meta(path: str | Path | None = None) -> pd.DataFrame:
    """block_id -> site/variety/planting_year/baseline_start, canonicalised.

    Plain DataFrame, no geometry: for consumers that only need the labels.
    """
    gdf = load_block_frame(path)
    cols = [c for c in META_COLUMNS if c in gdf.columns]
    return pd.DataFrame(gdf[cols])
