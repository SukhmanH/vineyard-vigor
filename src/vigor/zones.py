"""Within-block vigor zoning by k-means on per-pixel seasonal profiles (Phase 4).

Pure numpy/pandas/sklearn; must run offline. Input is the per-pixel profile
table pulled through the extract.py boundary (extract.sample_seasonal_profiles
-> extract.fetch_pixels), so zoning is re-derivable from that cached table.

Each pixel is a vector of monthly NDVI medians (the growing-season profile).
k-means groups pixels into k vigor zones per block-season. Cluster labels are
reordered by mean seasonal NDVI so zone 0 is always the lowest-vigor zone and
zone k-1 the highest - making "the high-vigor zone" mean the same thing across
years, which is what lets stable-vs-transient zones be read off the maps.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans

DEFAULT_K = 3
_RANDOM_STATE = 0
_MIN_PIXELS = 10  # need at least this many valid pixels to zone a block-season


def _profile_columns(df: pd.DataFrame) -> list[str]:
    """Profile band columns (m04..m10), in order."""
    return sorted(c for c in df.columns if c.startswith("m") and c[1:].isdigit())


def zone_block_season(
    pixels: pd.DataFrame, k: int = DEFAULT_K, random_state: int = _RANDOM_STATE
) -> pd.DataFrame:
    """Assign a vigor zone to each pixel of a single block-season.

    `pixels` holds one block-season's per-pixel profile rows. Pixels with any
    missing month (persistent cloud/snow that season) are dropped. Returns the
    kept pixels with an integer `zone` column (0 = lowest vigor) and a
    `mean_ndvi` column (the pixel's season-mean profile value). Returns an
    empty frame when there are too few valid pixels to cluster.
    """
    band_cols = _profile_columns(pixels)
    df = pixels.dropna(subset=band_cols).copy()
    n = len(df)
    if n < max(_MIN_PIXELS, k):
        return df.assign(zone=pd.Series(dtype="int64"), mean_ndvi=pd.Series(dtype="float64")).iloc[0:0]

    X = df[band_cols].to_numpy(dtype=float)
    km = KMeans(n_clusters=k, random_state=random_state, n_init=10)
    raw_labels = km.fit_predict(X)

    # Reorder labels by cluster mean NDVI so 0 = lowest vigor, k-1 = highest.
    cluster_mean = {c: X[raw_labels == c].mean() for c in range(k)}
    order = sorted(cluster_mean, key=cluster_mean.get)
    remap = {old: new for new, old in enumerate(order)}

    df["zone"] = [remap[c] for c in raw_labels]
    df["mean_ndvi"] = X.mean(axis=1)
    return df


def zone_all(
    pixels: pd.DataFrame, k: int = DEFAULT_K, random_state: int = _RANDOM_STATE
) -> pd.DataFrame:
    """Zone every (block_id, year) group in a per-pixel profile table.

    Returns all kept pixels across block-seasons with `zone` and `mean_ndvi`
    columns added. Block-seasons with too few valid pixels are skipped (a
    warning is left to the caller, who can diff the input/output block-season
    sets).
    """
    out = []
    for (block_id, year), g in pixels.groupby(["block_id", "year"], sort=True):
        zoned = zone_block_season(g, k=k, random_state=random_state)
        if not zoned.empty:
            out.append(zoned)
    if not out:
        return pixels.iloc[0:0].assign(zone=pd.Series(dtype="int64"), mean_ndvi=pd.Series(dtype="float64"))
    return pd.concat(out, ignore_index=True)


def zone_summary(zoned: pd.DataFrame) -> pd.DataFrame:
    """Per (block_id, year, zone): pixel count and mean seasonal NDVI.

    A compact view for reading zone structure - how big each zone is and how
    its vigor compares - without opening the maps.
    """
    if zoned.empty:
        return pd.DataFrame(columns=["block_id", "year", "zone", "n_pixels", "mean_ndvi"])
    g = (
        zoned.groupby(["block_id", "year", "zone"])
        .agg(n_pixels=("mean_ndvi", "size"), mean_ndvi=("mean_ndvi", "mean"))
        .reset_index()
    )
    return g


def write_zones(df: pd.DataFrame, path) -> "Path":  # type: ignore[name-defined]
    from pathlib import Path

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return path
