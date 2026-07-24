from pathlib import Path

import pandas as pd
import pytest

from vigor.ingest import (
    CONTRACT_COLUMNS,
    MIN_VALID_FRAC,
    analysis_view,
    load_timeseries,
    raw_to_timeseries,
    write_timeseries,
)


FIXTURE = Path(__file__).parent / "fixtures" / "sample_extract.csv"


def test_raw_fixture_converts_to_contract() -> None:
    raw = pd.read_csv(FIXTURE)

    actual = raw_to_timeseries(raw)

    assert actual.columns.tolist() == CONTRACT_COLUMNS
    assert pd.api.types.is_datetime64_any_dtype(actual["date"])
    assert actual["valid_frac"].between(0, 1).all()
    assert actual.equals(actual.sort_values(["block_id", "date", "scene_id"]).reset_index(drop=True))


def test_low_quality_rows_are_stored_but_excluded_from_analysis() -> None:
    timeseries = raw_to_timeseries(pd.read_csv(FIXTURE))

    assert (timeseries["valid_frac"] < MIN_VALID_FRAC).any()
    usable = analysis_view(timeseries)
    assert len(usable) < len(timeseries)
    assert (usable["valid_frac"] >= MIN_VALID_FRAC).all()


def test_parquet_round_trip(tmp_path: Path) -> None:
    expected = raw_to_timeseries(pd.read_csv(FIXTURE))
    path = write_timeseries(expected, tmp_path / "block_timeseries.parquet")

    actual = load_timeseries(path)

    pd.testing.assert_frame_equal(actual, expected)


def test_missing_raw_columns_are_rejected() -> None:
    raw = pd.read_csv(FIXTURE).drop(columns=["scene_id"])

    with pytest.raises(ValueError, match="scene_id"):
        raw_to_timeseries(raw)
