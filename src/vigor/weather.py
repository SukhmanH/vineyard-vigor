"""Site weather: ERA5-Land daily records and the trailing windows built on them.

Pure pandas; must run offline. The raw table crosses the extract.py boundary
in ERA5 native units (Kelvin, metres) and is converted here, so the only
module that talks to Earth Engine stays extract.py.

Two layers:

- `raw_to_weather` enforces the site_weather contract: one row per site per
  CALENDAR day, not per satellite pass. The trailing windows below are
  backward-looking rolling sums over a date index, so a gap silently shortens
  every window that spans it.

- `trailing_features` turns the daily record into per-(site, date) covariates
  describing the weather a vine has actually experienced coming into that
  date. Season-level aggregates would give ~14 effective observations across
  2 sites x 7 seasons; trailing windows put the variation inside each season
  and keep the full observation table as the unit of analysis.

KNOWN LIMIT: at ~11 km resolution this is a per-site signal. It cannot explain
why two adjacent blocks diverge - by construction it assigns them identical
weather. That is the point rather than a defect: removing the common
site-level signal is what leaves block-specific anomalies visible.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

CONTRACT_COLUMNS = [
    "site", "date",
    "tmax_c", "tmin_c", "precip_mm", "dewpoint_c", "pet_mm", "soil_moisture_m3m3",
    "source",
]

_KELVIN = 273.15
_M_TO_MM = 1000.0

SEASON_START_MONTH = 4  # April 1, the accumulation origin for season-to-date features

GDD_BASE_C = 10.0  # Winkler index base
HEAT_THRESHOLD_C = 35.0  # vine shutdown territory in the South Okanagan
PRECIP_WINDOW_D = 30
BALANCE_WINDOW_D = 30
VPD_WINDOW_D = 14

FEATURE_COLUMNS = [
    "gdd_base10_since_apr1",
    "precip_30d_mm",
    "water_balance_30d_mm",
    "vpd_14d_mean_kpa",
    "days_above_35c_since_apr1",
    "soil_moisture_anomaly",
]


def raw_to_weather(raw: pd.DataFrame, source: str = "ERA5-Land") -> pd.DataFrame:
    """Enforce the site_weather contract on a raw ERA5-Land table.

    Converts Kelvin to Celsius and metres to millimetres. ERA5 accumulates
    potential evaporation as a NEGATIVE flux (energy leaving the surface), so
    it is sign-flipped to a positive water demand, which is how it is used in
    the water balance below.
    """
    df = raw.copy()
    df["date"] = pd.to_datetime(df["date"])

    df["tmax_c"] = df["temperature_2m_max"] - _KELVIN
    df["tmin_c"] = df["temperature_2m_min"] - _KELVIN
    df["dewpoint_c"] = df["dewpoint_temperature_2m"] - _KELVIN
    df["precip_mm"] = df["total_precipitation_sum"] * _M_TO_MM
    df["pet_mm"] = -df["potential_evaporation_sum"] * _M_TO_MM
    df["soil_moisture_m3m3"] = df["volumetric_soil_water_layer_1"]
    df["source"] = source

    return (
        df[CONTRACT_COLUMNS]
        .sort_values(["site", "date"])
        .reset_index(drop=True)
    )


def check_continuity(df: pd.DataFrame) -> pd.DataFrame:
    """Per site-year: day count, missing days, and the longest missing run.

    The trailing windows assume an unbroken daily index. Callers should look
    at this before trusting any window that could span a gap.
    """
    rows = []
    for (site, year), g in df.groupby([df["site"], df["date"].dt.year], sort=True):
        full = pd.date_range(f"{year}-01-01", f"{year}-12-31", freq="D")
        full = full[full <= df["date"].max()]
        missing = full.difference(g["date"])
        longest = 0
        if len(missing):
            breaks = (missing.to_series().diff().dt.days != 1).cumsum()
            longest = int(missing.to_series().groupby(breaks).size().max())
        rows.append({
            "site": site, "year": year, "days": len(g),
            "expected": len(full), "missing": len(missing),
            "longest_gap": longest,
        })
    return pd.DataFrame(rows)


def _vpd_kpa(tmax_c: pd.Series, dewpoint_c: pd.Series) -> pd.Series:
    """Vapour-pressure deficit from daily max temperature and dewpoint.

    Saturation vapour pressure via Magnus/Sonntag. Using tmax rather than a
    daily mean deliberately targets the afternoon demand peak, which is when
    stomatal closure actually happens. Clipped at zero: saturated air is a
    deficit of nothing, never a negative one.
    """
    def _es(t: pd.Series) -> pd.Series:
        return 0.6112 * np.exp((17.62 * t) / (243.12 + t))

    return (_es(tmax_c) - _es(dewpoint_c)).clip(lower=0)


def trailing_features(df: pd.DataFrame) -> pd.DataFrame:
    """Backward-looking weather covariates per (site, date).

    Everything here describes the window ENDING at each date, so a row never
    contains information from its own future. Season-to-date accumulations
    reset on April 1; rolling windows are time-based ("30D"), so they stay
    correct even if a day is missing - they shorten rather than silently
    reaching further back.
    """
    out = df.sort_values(["site", "date"]).copy()
    out["year"] = out["date"].dt.year
    out["vpd_kpa"] = _vpd_kpa(out["tmax_c"], out["dewpoint_c"])
    out["gdd"] = (((out["tmax_c"] + out["tmin_c"]) / 2) - GDD_BASE_C).clip(lower=0)
    out["hot_day"] = (out["tmax_c"] >= HEAT_THRESHOLD_C).astype(int)

    frames = []
    for _, g in out.groupby("site", sort=True):
        g = g.set_index("date").sort_index()

        g["precip_30d_mm"] = g["precip_mm"].rolling(f"{PRECIP_WINDOW_D}D").sum()
        balance = g["precip_mm"] - g["pet_mm"]
        g["water_balance_30d_mm"] = balance.rolling(f"{BALANCE_WINDOW_D}D").sum()
        g["vpd_14d_mean_kpa"] = g["vpd_kpa"].rolling(f"{VPD_WINDOW_D}D").mean()

        # Season-to-date accumulations: cumulative within the Apr-Dec block of
        # each year, and undefined (NaN) before April 1 rather than zero.
        season = g.index.month >= SEASON_START_MONTH
        by_year = g.index.year
        g["gdd_base10_since_apr1"] = (
            g["gdd"].where(season, 0).groupby(by_year).cumsum().where(season)
        )
        g["days_above_35c_since_apr1"] = (
            g["hot_day"].where(season, 0).groupby(by_year).cumsum().where(season)
        )

        # Soil-moisture anomaly against the same day-of-year in prior seasons,
        # so a dry year reads as dry rather than as "it is August".
        doy = g.index.dayofyear
        clim = g.groupby(doy)["soil_moisture_m3m3"].transform("mean")
        g["soil_moisture_anomaly"] = g["soil_moisture_m3m3"] - clim

        frames.append(g.reset_index())

    feats = pd.concat(frames, ignore_index=True)
    return (
        feats[["site", "date", *FEATURE_COLUMNS]]
        .sort_values(["site", "date"])
        .reset_index(drop=True)
    )


def join_to_observations(obs: pd.DataFrame, feats: pd.DataFrame,
                         blocks: pd.DataFrame) -> pd.DataFrame:
    """Attach site weather features to a block observation table.

    `blocks` supplies block_id -> site. Observations at a site/date with no
    weather row (notably the ~1 week ERA5-Land reanalysis lag at the head of
    the record) keep NaN features rather than being dropped.
    """
    site_of = dict(zip(blocks["block_id"], blocks["site"]))
    out = obs.copy()
    out["site"] = out["block_id"].map(site_of)
    out["date"] = pd.to_datetime(out["date"])
    return out.merge(feats, on=["site", "date"], how="left")


def write_weather(df: pd.DataFrame, path) -> "object":
    from pathlib import Path

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return path
