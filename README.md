# vineyard-vigor

Satellite vigor mapping for vineyard blocks. Builds per-block Sentinel-2
NDVI/NDRE time series from 2019 to present, then flags seasons that fall below
each block's own multi-year baseline.

The goal is to surface irrigation failures, virus decline, and nutrient stress
early enough to act on, and to map within-block vigor variation for management
zoning.

## How it works

Imagery extraction runs through Google Earth Engine. Everything downstream is
pure pandas/scikit-learn operating on a local parquet table, so the analysis can
be iterated offline without re-hitting Earth Engine.

```
GEE ──► extract ──► block_timeseries.parquet ──► clean ──► features ──► zones
                                                     │
                                                     └──► alerts ──► dashboard
```

| Module | Role |
|---|---|
| `extract.py` | The only module that touches Earth Engine. Cloud-masked NDVI/NDRE reductions per block. |
| `ingest.py` | Loads extraction output into the canonical parquet table. |
| `clean.py` | Rolling-median outlier screen, then Savitzky-Golay smoothing. |
| `features.py` | Per-season per-block features: peak NDVI, seasonal integral, green-up date. |
| `zones.py` | k-means over per-pixel seasonal profiles to produce within-block vigor zones. |
| `vigor_alerts.py` | Day-of-year baseline comparison; raises below-baseline alerts. |
| `ml.py` | Gaussian-process season outlook and analog-season matching. |
| `dashboard.py` / `webdash.py` | Static HTML dashboard generation. |

## Design decisions worth knowing

**Reductions run in a projected UTM CRS, not WGS84.** Computing spatial
statistics on a geographic grid distorts them, so reprojection happens only for
display.

**Cloud masking uses Cloud Score+** (`GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED`)
rather than the QA60 band, attached via `linkCollection` and thresholded at
`cs_cdf < 0.60`. QA60 misses haze and thin cirrus that measurably depress NDVI.

**Wildfire smoke is screened separately.** Smoke suppresses NDVI without being
flagged by any cloud mask, so a rolling-median outlier pass runs before
smoothing.

**Block geometries are buffered inward by 1 m** before reduction, trimming edge
pixels that blend canopy with adjacent road or cover crop. Blocks smaller than
10 pixels after buffering are skipped rather than reported as noise.

**NDRE is a block-level statistic only.** It is computed at 20 m and never used
for within-block zoning, where the coarser pixel would smear zone boundaries.

**Alerts are relative, never absolute.** A block is flagged when it sits below
the 10th percentile of its own prior-season distribution within a ±10 day
window, for two consecutive observations. Comparing against same-variety blocks
in the same season separates weather (all blocks down together) from a
single-block cause such as a failed emitter.

## Data contract

The canonical table is `data/processed/block_timeseries.parquet`:

```
block_id, date, scene_id, ndvi_median, ndvi_p10, ndvi_p90, ndre_median, valid_frac
```

`valid_frac` is the unmasked pixel fraction of the buffered block. Every row is
stored; analysis drops rows below `0.8`.

Block polygons live in `data/blocks.geojson` (WGS84) with properties:

```
block_id (required), site (required), variety, planting_year, baseline_start
```

See [`data/blocks.geojson.example`](data/blocks.geojson.example) for the shape.

## Setup

Requires Python 3.12+ and a Google Earth Engine account.

```bash
uv sync
uv run earthengine authenticate
```

Supply your own `data/blocks.geojson`. Real block polygons are gitignored and
not distributed with this repo.

```bash
uv run python scripts/smoke_test.py      # verify GEE auth against a single scene
uv run python scripts/backfill_s2.py     # full Sentinel-2 backfill
uv run python scripts/weekly_update.py   # incremental refresh + dashboard
```

The `notebooks/` directory walks the pipeline stage by stage, from drawing block
polygons through to the generated dashboard.

## Tests

```bash
uv run pytest
```

40 tests, no network required. The Earth Engine layer is isolated behind
`extract.py`, so the whole analysis stack is testable offline against
`tests/fixtures/`.

## A note on data

Real block polygons, processed parquet tables, and generated dashboards are all
gitignored. The generated dashboard embeds site coordinates, so it is not
published here.

## License

Copyright (C) 2026 Sukhman Herr

Licensed under the GNU Affero General Public License v3.0. You may use, modify,
and redistribute this software, but derivative works must also be released under
the AGPL-3.0 - including works made available over a network. See
[LICENSE](LICENSE).

For commercial licensing outside these terms, contact the author.
