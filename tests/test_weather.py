"""Offline tests for the ERA5-Land site weather layer (weather.py).

No Earth Engine. tests/fixtures/sample_era5.csv holds a week of raw ERA5
records for two sites in native units (Kelvin, metres, negative evaporation
flux); everything else here is synthesised so window arithmetic can be
checked against a value worked out by hand.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from vigor import extract, weather

FIXTURE = Path(__file__).parent / "fixtures" / "sample_era5.csv"


@pytest.fixture
def raw() -> pd.DataFrame:
    return pd.read_csv(FIXTURE)


def _daily(site="Oliver", start="2024-04-01", days=120, tmax=25.0, tmin=10.0,
           precip=0.0, dew=5.0, pet=5.0, soil=0.2):
    """A continuous daily record with constant weather, so a rolling window
    has an arithmetically obvious answer."""
    dates = pd.date_range(start, periods=days, freq="D")
    return pd.DataFrame({
        "site": site, "date": dates,
        "tmax_c": tmax, "tmin_c": tmin, "precip_mm": precip,
        "dewpoint_c": dew, "pet_mm": pet, "soil_moisture_m3m3": soil,
        "source": "synthetic",
    })


# --- contract / unit conversion -------------------------------------------

def test_raw_to_weather_matches_contract(raw):
    out = weather.raw_to_weather(raw)
    assert list(out.columns) == weather.CONTRACT_COLUMNS
    assert len(out) == len(raw)
    assert out["date"].dtype.kind == "M"


def test_kelvin_and_metres_are_converted(raw):
    out = weather.raw_to_weather(raw)
    row = out[(out["site"] == "Oliver") & (out["date"] == "2024-07-03")].iloc[0]
    assert row["tmax_c"] == pytest.approx(37.0, abs=1e-6)   # 310.15 K
    assert row["tmin_c"] == pytest.approx(17.0, abs=1e-6)   # 290.15 K
    assert row["dewpoint_c"] == pytest.approx(2.0, abs=1e-6)


def test_precipitation_metres_become_millimetres(raw):
    out = weather.raw_to_weather(raw)
    row = out[(out["site"] == "Oliver") & (out["date"] == "2024-06-28")].iloc[0]
    assert row["precip_mm"] == pytest.approx(2.0)  # 0.002 m


def test_pet_sign_is_flipped_to_positive_demand(raw):
    """ERA5 reports potential evaporation as a negative flux; a negative water
    demand would invert the water balance."""
    assert (raw["potential_evaporation_sum"] <= 0).all()
    out = weather.raw_to_weather(raw)
    assert (out["pet_mm"] >= 0).all()
    row = out[(out["site"] == "Oliver") & (out["date"] == "2024-07-03")].iloc[0]
    assert row["pet_mm"] == pytest.approx(10.0)  # -(-0.010 m) * 1000


def test_sites_stay_separate(raw):
    out = weather.raw_to_weather(raw)
    assert set(out["site"]) == {"Oliver", "Penticton"}
    o = out[out["site"] == "Oliver"].set_index("date")["tmax_c"]
    p = out[out["site"] == "Penticton"].set_index("date")["tmax_c"]
    assert not np.allclose(o.to_numpy(), p.to_numpy())


# --- continuity ------------------------------------------------------------

def test_continuity_reports_a_clean_record():
    df = _daily(days=60, start="2024-01-01")
    rep = weather.check_continuity(df)
    assert rep["missing"].sum() == 0
    assert rep["longest_gap"].max() == 0


def test_continuity_finds_a_gap():
    df = _daily(days=60, start="2024-01-01")
    df = df[~df["date"].between("2024-01-10", "2024-01-14")]
    rep = weather.check_continuity(df)
    assert rep["missing"].iloc[0] >= 5
    assert rep["longest_gap"].iloc[0] == 5


# --- trailing windows ------------------------------------------------------

def test_precip_30d_sums_the_trailing_window():
    df = _daily(days=90, precip=2.0)
    f = weather.trailing_features(df)
    late = f[f["date"] == "2024-06-01"].iloc[0]
    assert late["precip_30d_mm"] == pytest.approx(60.0)  # 30 days x 2 mm


def test_windows_are_backward_looking_only():
    """A spike must not appear in a window that ends before it."""
    df = _daily(days=90, precip=0.0)
    df.loc[df["date"] == "2024-06-15", "precip_mm"] = 50.0
    f = weather.trailing_features(df).set_index("date")
    assert f.loc["2024-06-14", "precip_30d_mm"] == pytest.approx(0.0)
    assert f.loc["2024-06-15", "precip_30d_mm"] == pytest.approx(50.0)


def test_gdd_accumulates_from_april_and_resets_each_year():
    df = pd.concat([
        _daily(start="2024-04-01", days=120, tmax=30.0, tmin=10.0),
        _daily(start="2025-04-01", days=120, tmax=30.0, tmin=10.0),
    ], ignore_index=True)
    f = weather.trailing_features(df).set_index("date")
    # mean 20C, base 10 -> 10 GDD/day; April 10 is the 10th day
    assert f.loc["2024-04-10", "gdd_base10_since_apr1"] == pytest.approx(100.0)
    assert f.loc["2025-04-10", "gdd_base10_since_apr1"] == pytest.approx(100.0)


def test_gdd_is_undefined_before_april():
    df = _daily(start="2024-01-01", days=200, tmax=30.0, tmin=10.0)
    f = weather.trailing_features(df).set_index("date")
    assert pd.isna(f.loc["2024-03-15", "gdd_base10_since_apr1"])
    assert f.loc["2024-04-02", "gdd_base10_since_apr1"] > 0


def test_days_above_35c_counts_only_hot_days():
    df = _daily(start="2024-04-01", days=60, tmax=20.0)
    df.loc[df["date"].isin(pd.to_datetime(["2024-04-05", "2024-04-06"])), "tmax_c"] = 38.0
    f = weather.trailing_features(df).set_index("date")
    assert f.loc["2024-04-30", "days_above_35c_since_apr1"] == 2


def test_water_balance_is_precip_minus_pet():
    df = _daily(days=90, precip=1.0, pet=3.0)
    f = weather.trailing_features(df).set_index("date")
    assert f.loc["2024-06-01", "water_balance_30d_mm"] == pytest.approx(-60.0)


def test_vpd_is_zero_when_saturated_and_positive_when_dry():
    sat = weather._vpd_kpa(pd.Series([20.0]), pd.Series([20.0]))
    dry = weather._vpd_kpa(pd.Series([35.0]), pd.Series([0.0]))
    assert sat.iloc[0] == pytest.approx(0.0, abs=1e-9)
    assert dry.iloc[0] > 3.0


def test_vpd_never_negative_when_dewpoint_exceeds_tmax():
    v = weather._vpd_kpa(pd.Series([10.0]), pd.Series([15.0]))
    assert v.iloc[0] == pytest.approx(0.0)


def test_features_are_computed_per_site_independently():
    df = pd.concat([
        _daily(site="A", days=60, precip=1.0),
        _daily(site="B", days=60, precip=5.0),
    ], ignore_index=True)
    f = weather.trailing_features(df)
    a = f[(f["site"] == "A") & (f["date"] == "2024-05-15")].iloc[0]
    b = f[(f["site"] == "B") & (f["date"] == "2024-05-15")].iloc[0]
    assert b["precip_30d_mm"] == pytest.approx(5 * a["precip_30d_mm"])


# --- join ------------------------------------------------------------------

def test_join_maps_blocks_to_their_site():
    obs = pd.DataFrame({
        "block_id": ["b1", "b2"],
        "date": pd.to_datetime(["2024-06-01", "2024-06-01"]),
        "ndvi": [0.7, 0.6],
    })
    blocks = pd.DataFrame({"block_id": ["b1", "b2"], "site": ["A", "B"]})
    feats = weather.trailing_features(pd.concat([
        _daily(site="A", days=90, precip=1.0),
        _daily(site="B", days=90, precip=4.0),
    ], ignore_index=True))
    out = weather.join_to_observations(obs, feats, blocks)
    assert out.loc[out["block_id"] == "b1", "precip_30d_mm"].iloc[0] == pytest.approx(30.0)
    assert out.loc[out["block_id"] == "b2", "precip_30d_mm"].iloc[0] == pytest.approx(120.0)


def test_join_keeps_observations_without_weather():
    """ERA5-Land lags real time by about a week; those rows must survive."""
    obs = pd.DataFrame({
        "block_id": ["b1"],
        "date": pd.to_datetime(["2030-06-01"]),
        "ndvi": [0.7],
    })
    blocks = pd.DataFrame({"block_id": ["b1"], "site": ["A"]})
    feats = weather.trailing_features(_daily(site="A", days=90))
    out = weather.join_to_observations(obs, feats, blocks)
    assert len(out) == 1
    assert pd.isna(out["precip_30d_mm"].iloc[0])


# --- variety canonicalisation (peer grouping depends on it) ----------------

@pytest.mark.parametrize("given,expected", [
    ("Mustak", "Mustak"),
    ("mustak", "Mustak"),
    ("mustek", "Mustak"),
    ("  MUSTAK  ", "Mustak"),
    ("chard", "Chardonnay"),
    ("Mar", "Mar"),
])
def test_variety_aliases_collapse(given, expected):
    assert extract.canonical_variety(given) == expected


def test_canonical_site_normalises_case_and_whitespace():
    assert extract.canonical_site(" oliver ") == "Oliver"
    assert extract.canonical_site("PENTICTON") == "Penticton"


def test_canonical_helpers_pass_through_missing():
    assert extract.canonical_variety(None) is None
    assert pd.isna(extract.canonical_variety(float("nan")))
