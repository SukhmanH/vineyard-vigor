"""Raw extracted tables -> the analysis-ready parquet.

Pure pandas; must run offline. The raw table comes across the extract.py
boundary (getInfo or a Drive CSV in data/raw/) with columns:

    block_id, date, scene_id, ndvi_median, ndvi_p10, ndvi_p90, ndre_median,
    valid_count, total_count
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

RAW_COLUMNS = [
    "block_id", "date", "scene_id",
    "ndvi_median", "ndvi_p10", "ndvi_p90", "ndre_median",
    "valid_count", "total_count",
]

CONTRACT_COLUMNS = [
    "block_id", "date", "scene_id",
    "ndvi_median", "ndvi_p10", "ndvi_p90", "ndre_median",
    "valid_frac",
]

_FLOAT_COLUMNS = ["ndvi_median", "ndvi_p10", "ndvi_p90", "ndre_median", "valid_frac"]

MIN_VALID_FRAC = 0.8  # analysis threshold; every row is still stored


def raw_to_timeseries(raw: pd.DataFrame) -> pd.DataFrame:
    """Enforce the data contract on a raw extracted table.

    Keeps every row (including fully masked scenes with valid_frac 0);
    dropping rows below MIN_VALID_FRAC is the analysis step's job.
    """
    missing = [c for c in RAW_COLUMNS if c not in raw.columns]
    if missing:
        raise ValueError(f"raw table is missing columns: {missing}")

    df = raw.copy()
    df["valid_frac"] = df["valid_count"] / df["total_count"]
    df["date"] = pd.to_datetime(df["date"])  # ISO, tz-naive, sensing date
    df = df[CONTRACT_COLUMNS]
    df[_FLOAT_COLUMNS] = df[_FLOAT_COLUMNS].astype("float64")
    return df.sort_values(["block_id", "date", "scene_id"]).reset_index(drop=True)


def write_timeseries(df: pd.DataFrame, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return path


def load_timeseries(path: str | Path) -> pd.DataFrame:
    return pd.read_parquet(path)


def analysis_view(df: pd.DataFrame, min_valid_frac: float = MIN_VALID_FRAC) -> pd.DataFrame:
    """The rows analysis is allowed to use."""
    return df[df["valid_frac"] >= min_valid_frac].copy()
