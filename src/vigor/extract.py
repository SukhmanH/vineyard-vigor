"""All Google Earth Engine access for vineyard-vigor.

Every Earth Engine call in the project lives in this module and nowhere else;
everything downstream is pure pandas/sklearn and must run offline.

All reductions run at scale=10 in EPSG:32611 (scale=20 for NDRE bands), and
everything stays server-side: `ImageCollection.map` plus combined reducers,
never a Python loop over scenes.
"""

from __future__ import annotations

import datetime as _dt
import json
import warnings
from pathlib import Path
from typing import Any

import ee
import geopandas as gpd
import pandas as pd
from shapely.geometry import mapping

GEE_PROJECT_ID = "vineyard-vigor"
WORKING_CRS = "EPSG:32611"  # UTM 11N; never reproject silently

S2_COLLECTION = "COPERNICUS/S2_SR_HARMONIZED"
CSP_COLLECTION = "GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED"
CS_BAND = "cs_cdf"
CS_THRESHOLD = 0.60  # mask pixels with cs_cdf < 0.60

# Landsat 8/9 Collection 2 Level-2: the pre-Sentinel deep history (2013->).
# 30 m, so block-level medians only - never zoning, never mixed into the
# 10 m S2 analytics.
L8_COLLECTION = "LANDSAT/LC08/C02/T1_L2"
L9_COLLECTION = "LANDSAT/LC09/C02/T1_L2"
LANDSAT_SCALE = 30
LANDSAT_START_YEAR = 2014  # first full L8 year over the Okanagan

EDGE_BUFFER_M = -1.0  # trim the immediate polygon edge without losing block area
MIN_PIXELS = 10  # warn and skip blocks smaller than this after buffering
PIXEL_AREA_M2 = 100.0  # 10 m pixels

REQUIRED_PROPS = ("block_id", "site")


def init_ee(project: str = GEE_PROJECT_ID) -> None:
    """Initialize Earth Engine, running interactive auth once if needed."""
    try:
        ee.Initialize(project=project)
    except Exception:
        ee.Authenticate()
        ee.Initialize(project=project)


def load_blocks(path: str | Path) -> gpd.GeoDataFrame:
    """Load block polygons and apply the -1 m edge buffer in UTM 11N.

    Returns a GeoDataFrame in EPSG:32611 with the planted extent as the active
    geometry plus `geometry_buffered`, `area_ha`, and `n_pixels` columns.
    Blocks under MIN_PIXELS after buffering are dropped with a warning.
    """
    gdf = gpd.read_file(path)
    # Hand-drawn geojson properties sometimes carry stray whitespace in keys
    # (e.g. "block_id "); normalize before validating.
    gdf.columns = gdf.columns.str.strip()

    if "block_id" not in gdf.columns:
        warnings.warn(
            "blocks.geojson is missing the required 'block_id' property; "
            "using placeholder ids. Fix the file before Phase 2.",
            stacklevel=2,
        )
        gdf["block_id"] = [f"block-{i}" for i in range(len(gdf))]
    if "site" not in gdf.columns:
        warnings.warn(
            "blocks.geojson is missing the required 'site' property; "
            "using 'unknown'. Fix the file before Phase 2.",
            stacklevel=2,
        )
        gdf["site"] = "unknown"

    gdf = gdf.to_crs(WORKING_CRS)
    gdf["geometry_buffered"] = gdf.geometry.buffer(EDGE_BUFFER_M)
    gdf["area_ha"] = gdf.geometry.area / 10_000
    gdf["n_pixels"] = (gdf["geometry_buffered"].area / PIXEL_AREA_M2).astype(int)

    too_small = gdf["n_pixels"] < MIN_PIXELS
    if too_small.any():
        warnings.warn(
            f"Skipping blocks under {MIN_PIXELS} pixels after the "
            f"{EDGE_BUFFER_M} m buffer: {gdf.loc[too_small, 'block_id'].tolist()}",
            stacklevel=2,
        )
        gdf = gdf[~too_small].copy()

    return gdf


def to_ee_geometry(geom) -> ee.Geometry:
    """Shapely geometry in EPSG:32611 -> planar ee.Geometry, CRS stated explicitly."""
    geo_json = json.loads(json.dumps(mapping(geom)))
    return ee.Geometry(geo_json, proj=WORKING_CRS, geodesic=False)


def masked_ndvi_collection(
    region: ee.Geometry, start: str, end: str
) -> ee.ImageCollection:
    """Harmonized S2 SR over `region`, Cloud Score+ masked, NDVI/NDRE added.

    `end` is exclusive, per ee.ImageCollection.filterDate.
    """
    s2 = (
        ee.ImageCollection(S2_COLLECTION)
        .filterBounds(region)
        .filterDate(start, end)
        .linkCollection(ee.ImageCollection(CSP_COLLECTION), [CS_BAND])
    )
    return s2.map(_prepare)


def _prepare(img: ee.Image) -> ee.Image:
    """Scale DNs to reflectance, apply the Cloud Score+ mask, add NDVI and NDRE."""
    img = img.addBands(img.select("B.*").divide(10_000), None, True)
    img = img.updateMask(img.select(CS_BAND).gte(CS_THRESHOLD))
    return img.addBands(
        img.normalizedDifference(["B8", "B4"]).rename("NDVI")
    ).addBands(img.normalizedDifference(["B8A", "B5"]).rename("NDRE"))


def clearest_scene(collection: ee.ImageCollection, region: ee.Geometry) -> ee.Image:
    """Scene with the most unmasked NDVI pixels over `region` (server-side sort)."""

    def _count(img: ee.Image) -> ee.Image:
        n = img.select("NDVI").reduceRegion(
            reducer=ee.Reducer.count(),
            geometry=region,
            scale=10,
            crs=WORKING_CRS,
        ).get("NDVI")
        return img.set("valid_pixels", n)

    return ee.Image(collection.map(_count).sort("valid_pixels", False).first())


def latest_clear_scene(
    region: ee.Geometry,
    lookback_days: int = 120,
    min_clear_frac: float = 0.95,
    end_date: str | None = None,
) -> ee.Image:
    """Most recent scene at least `min_clear_frac` unmasked over `region`.

    Falls back to the clearest scene in the lookback window when nothing
    qualifies. Server-side throughout.
    """
    if end_date is None:
        end = _dt.date.today() + _dt.timedelta(days=1)
    else:
        end = _dt.date.fromisoformat(end_date)
    start = end - _dt.timedelta(days=lookback_days)

    col = masked_ndvi_collection(region, start.isoformat(), end.isoformat())
    total = ee.Image.constant(1).reduceRegion(
        reducer=ee.Reducer.count(), geometry=region, scale=10, crs=WORKING_CRS
    ).get("constant")

    def _clear_frac(img: ee.Image) -> ee.Image:
        n = img.select("NDVI").reduceRegion(
            reducer=ee.Reducer.count(), geometry=region, scale=10, crs=WORKING_CRS
        ).get("NDVI")
        return img.set("clear_frac", ee.Number(n).divide(ee.Number(total)))

    ranked = col.map(_clear_frac)
    clear = ranked.filter(ee.Filter.gte("clear_frac", min_clear_frac)).sort(
        "system:time_start", False
    )
    return ee.Image(
        ee.Algorithms.If(
            clear.size().gt(0), clear.first(), ranked.sort("clear_frac", False).first()
        )
    )


def count_scenes(collection: ee.ImageCollection) -> int:
    return collection.size().getInfo()


def scene_summary(img: ee.Image, region: ee.Geometry) -> dict[str, Any]:
    """Block-level NDVI stats and valid_frac for one scene; one getInfo round-trip.

    valid_frac = unmasked pixel count / total pixel count of the buffered block.
    """
    reducer = ee.Reducer.median().combine(
        ee.Reducer.percentile([10, 90]), sharedInputs=True
    )
    stats = img.select("NDVI").reduceRegion(
        reducer=reducer, geometry=region, scale=10, crs=WORKING_CRS
    )
    # Count valid and total pixels in one reduction so both bands share the
    # same grid and weighting; separate reductions can disagree at the edges.
    counts = (
        ee.Image.constant(1)
        .rename("total")
        .addBands(img.select(["NDVI"], ["valid"]))
        .reduceRegion(
            reducer=ee.Reducer.count(), geometry=region, scale=10, crs=WORKING_CRS
        )
    )

    return ee.Dictionary(
        {
            "scene_id": img.get("system:index"),
            "date": ee.Date(img.get("system:time_start")).format("YYYY-MM-dd"),
            "ndvi_median": stats.get("NDVI_median"),
            "ndvi_p10": stats.get("NDVI_p10"),
            "ndvi_p90": stats.get("NDVI_p90"),
            "valid_frac": ee.Number(counts.get("valid")).divide(
                ee.Number(counts.get("total"))
            ),
        }
    ).getInfo()


# Raw table schema exposed at the extract boundary. valid_frac is derived
# downstream (ingest.py) as valid_count / total_count.
_RAW_NAMES = [
    "block_id", "date", "scene_id",
    "ndvi_median", "ndvi_p10", "ndvi_p90", "ndre_median",
    "valid_count", "total_count",
]

SEASON_MONTH_START = 4  # April; growing-season start used by analysis, not extraction
SEASON_MONTH_END = 10  # October; growing-season end used by analysis, not extraction
BASELINE_START_YEAR = 2019  # the 2017-18 L2A archive is thin


def blocks_feature_collection(gdf: gpd.GeoDataFrame) -> ee.FeatureCollection:
    """Buffered block geometries as an ee.FeatureCollection keyed by block_id."""
    features = [
        ee.Feature(to_ee_geometry(geom), {"block_id": block_id})
        for block_id, geom in zip(gdf["block_id"], gdf["geometry_buffered"])
    ]
    return ee.FeatureCollection(features)


def timeseries_table(
    gdf: gpd.GeoDataFrame,
    start_year: int = BASELINE_START_YEAR,
    end_date: str | None = None,
    start_date: str | None = None,
) -> ee.FeatureCollection:
    """Lazy (scene x block) stats table, full calendar year (Jan-Dec).

    `start_date` (ISO) overrides the January 1 start for incremental pulls -
    keep the window short there: a year-wide interactive pull can trip EE's
    "Too many concurrent aggregations" limit.

    Entirely server-side: one reduceRegions per scene at 10 m for NDVI stats
    and pixel counts, chained into a second reduceRegions at 20 m for the NDRE
    median (the 10 m output collection is the input to the 20 m pass, so each
    feature accumulates all stats without a join). No Python loop over scenes,
    no getInfo. Rows where a block is fully outside a scene footprint are
    dropped server-side.

    Extraction is not restricted to the growing season - dormant-season scenes
    are pulled too, so downstream code can see the full annual curve. Analysis
    that only wants the season window filters on SEASON_MONTH_START/END itself.

    The same code path serves any number of blocks; pull results with
    fetch_table (small tables) or export_table_to_drive (large ones).
    """
    if end_date is None:
        end_date = (_dt.date.today() + _dt.timedelta(days=1)).isoformat()
    if start_date is None:
        start_date = f"{start_year}-01-01"

    blocks_fc = blocks_feature_collection(gdf)
    scenes = (
        ee.ImageCollection(S2_COLLECTION)
        .filterBounds(blocks_fc)
        .filterDate(start_date, end_date)
        .linkCollection(ee.ImageCollection(CSP_COLLECTION), [CS_BAND])
        .map(_prepare)
    )

    ndvi_reducer = (
        ee.Reducer.median()
        .combine(ee.Reducer.percentile([10, 90]), sharedInputs=True)
        .combine(ee.Reducer.count(), sharedInputs=True)
    )
    ndre_reducer = ee.Reducer.median().setOutputs(["ndre_median"])

    def _per_scene(img: ee.Image) -> ee.FeatureCollection:
        scene_id = img.get("system:index")
        date = ee.Date(img.get("system:time_start")).format("YYYY-MM-dd")
        # NDVI plus an unmasked constant band so valid and total pixel counts
        # share one grid and weighting (separate reductions disagree at edges).
        stack = img.select(["NDVI"]).addBands(ee.Image.constant(1).rename("total"))
        fc = stack.reduceRegions(
            collection=blocks_fc, reducer=ndvi_reducer, scale=10, crs=WORKING_CRS
        )
        fc = img.select(["NDRE"]).reduceRegions(
            collection=fc, reducer=ndre_reducer, scale=20, crs=WORKING_CRS
        )
        def _raw_properties(f: ee.Feature) -> ee.Feature:
            f = ee.Feature(f)
            # Reducers omit median/percentile properties when every pixel is
            # masked. Keep the raw names stable and explicitly make the valid
            # count zero for those observations.
            return f.set(
                {
                    "scene_id": scene_id,
                    "date": date,
                    "ndvi_median": f.get("NDVI_median"),
                    "ndvi_p10": f.get("NDVI_p10"),
                    "ndvi_p90": f.get("NDVI_p90"),
                    "ndre_median": f.get("ndre_median"),
                    "valid_count": ee.Algorithms.If(
                        f.propertyNames().contains("NDVI_count"),
                        f.get("NDVI_count"),
                        0,
                    ),
                    "total_count": f.get("total_count"),
                }
            )

        return fc.map(_raw_properties)

    # ImageCollection.map must return an Image, not a FeatureCollection. Map
    # its server-side list instead, then flatten the resulting collections.
    # This avoids a deeply nested sequential merge and lets EE schedule scene
    # reductions independently. Dropping geometries keeps the single getInfo
    # response compact; they have served their purpose as reduction regions.
    # size().max(1): toList(0) errors, but a count above the collection size
    # is fine, so an empty window yields an empty table instead of raising.
    scene_collections = ee.List(scenes.toList(scenes.size().max(1))).map(
        lambda img: _per_scene(ee.Image(img)).map(
            lambda f: ee.Feature(f).setGeometry(None)
        )
    )
    table = ee.FeatureCollection(scene_collections).flatten()
    return table.filter(ee.Filter.gt("total_count", 0))


def _prepare_landsat(img: ee.Image) -> ee.Image:
    """Scale L2 SR to reflectance, mask QA_PIXEL cloud bits, add NDVI.

    QA_PIXEL bits: 1 dilated cloud, 2 cirrus, 3 cloud, 4 cloud shadow.
    """
    qa = img.select("QA_PIXEL")
    clear = (
        qa.bitwiseAnd(1 << 1).eq(0)
        .And(qa.bitwiseAnd(1 << 2).eq(0))
        .And(qa.bitwiseAnd(1 << 3).eq(0))
        .And(qa.bitwiseAnd(1 << 4).eq(0))
    )
    sr = img.select(["SR_B5", "SR_B4"]).multiply(0.0000275).add(-0.2)
    ndvi = sr.normalizedDifference(["SR_B5", "SR_B4"]).rename("NDVI")
    return ee.Image(
        ndvi.updateMask(clear).copyProperties(img, ["system:time_start", "system:index"])
    )


def landsat_timeseries_table(
    gdf: gpd.GeoDataFrame,
    start_date: str,
    end_date: str | None = None,
) -> ee.FeatureCollection:
    """Lazy (scene x block) Landsat 8/9 NDVI stats table at 30 m.

    Emits the same raw property names as the S2 table (scene_id, date,
    ndvi_median/p10/p90, valid_count, total_count), so `fetch_table` and
    `ingest.raw_to_timeseries` serve both sensors; `ndre_median` has no
    Landsat red-edge equivalent and comes back NaN. Keep pull windows to a
    year or so - the same "Too many concurrent aggregations" limit applies.
    """
    if end_date is None:
        end_date = (_dt.date.today() + _dt.timedelta(days=1)).isoformat()

    blocks_fc = blocks_feature_collection(gdf)
    scenes = (
        ee.ImageCollection(L8_COLLECTION)
        .merge(ee.ImageCollection(L9_COLLECTION))
        .filterBounds(blocks_fc)
        .filterDate(start_date, end_date)
        .map(_prepare_landsat)
    )

    ndvi_reducer = (
        ee.Reducer.median()
        .combine(ee.Reducer.percentile([10, 90]), sharedInputs=True)
        .combine(ee.Reducer.count(), sharedInputs=True)
    )

    def _per_scene(img: ee.Image) -> ee.FeatureCollection:
        scene_id = img.get("system:index")
        date = ee.Date(img.get("system:time_start")).format("YYYY-MM-dd")
        stack = img.select(["NDVI"]).addBands(ee.Image.constant(1).rename("total"))
        fc = stack.reduceRegions(
            collection=blocks_fc, reducer=ndvi_reducer,
            scale=LANDSAT_SCALE, crs=WORKING_CRS,
        )

        def _raw_properties(f: ee.Feature) -> ee.Feature:
            f = ee.Feature(f)
            return f.set(
                {
                    "scene_id": scene_id,
                    "date": date,
                    "ndvi_median": f.get("NDVI_median"),
                    "ndvi_p10": f.get("NDVI_p10"),
                    "ndvi_p90": f.get("NDVI_p90"),
                    "valid_count": ee.Algorithms.If(
                        f.propertyNames().contains("NDVI_count"),
                        f.get("NDVI_count"),
                        0,
                    ),
                    "total_count": f.get("total_count"),
                }
            )

        return fc.map(_raw_properties)

    scene_collections = ee.List(scenes.toList(scenes.size().max(1))).map(
        lambda img: _per_scene(ee.Image(img)).map(
            lambda f: ee.Feature(f).setGeometry(None)
        )
    )
    table = ee.FeatureCollection(scene_collections).flatten()
    return table.filter(ee.Filter.gt("total_count", 0))


# Per-pixel seasonal profile (Phase 4). One band per growing-season month, so
# the profile vector is fixed-length and comparable across years and blocks.
_PROFILE_MONTHS = list(range(SEASON_MONTH_START, SEASON_MONTH_END + 1))  # Apr..Oct
PROFILE_BANDS = [f"m{m:02d}" for m in _PROFILE_MONTHS]


def seasonal_profile_image(region: ee.Geometry, year: int) -> ee.Image:
    """Per-pixel NDVI seasonal profile for one block-season, as a multi-band image.

    One band per growing-season month (Apr..Oct), each the Cloud Score+ masked
    NDVI median for that month, stacked with `toBands`. A pixel's band vector is
    its vigor "profile" over the season; k-means clusters pixels by that shape.
    Server-side; nothing is fetched here.
    """
    col = masked_ndvi_collection(region, f"{year}-01-01", f"{year + 1}-01-01")

    def _month(m) -> ee.Image:
        m = ee.Number(m)
        monthly = (
            col.select("NDVI")
            .filter(ee.Filter.calendarRange(m, m, "month"))
            .median()
        )
        return monthly.rename(ee.String("m").cat(m.format("%02d")))

    months = ee.ImageCollection(ee.List(_PROFILE_MONTHS).map(_month))
    # toBands prefixes band names with the image index; select back to clean names.
    stacked = months.toBands().rename(PROFILE_BANDS)
    return stacked.clip(region)


def sample_seasonal_profiles(
    gdf: gpd.GeoDataFrame, year: int
) -> ee.FeatureCollection:
    """Lazy per-pixel profile samples for every block in `gdf`, one season.

    One `sampleRegions` call per block-season at 10 m over the buffered block,
    with pixel geometries retained for mapping. Returns a FeatureCollection
    whose features each carry `block_id`, `year`, the profile bands, and a
    point geometry. Server-side; pull with `fetch_pixels`.
    """
    collections = []
    for block_id, geom in zip(gdf["block_id"], gdf["geometry_buffered"]):
        region = to_ee_geometry(geom)
        profile = seasonal_profile_image(region, year)
        samples = profile.sampleRegions(
            collection=ee.FeatureCollection([ee.Feature(region)]),
            scale=10,
            projection=WORKING_CRS,
            geometries=True,
        ).map(lambda f: ee.Feature(f).set({"block_id": block_id, "year": year}))
        collections.append(samples)
    return ee.FeatureCollection(collections).flatten()


def fetch_pixels(samples: ee.FeatureCollection) -> pd.DataFrame:
    """Pull per-pixel profile samples in one getInfo, with lon/lat columns.

    Columns: block_id, year, the PROFILE_BANDS, and lon/lat (pixel centroids in
    WGS84, for mapping). Fine for a few blocks; a block is ~100-300 pixels x 7
    bands, so this stays well within getInfo limits.
    """
    info = samples.getInfo()
    rows = []
    for feat in info["features"]:
        props = dict(feat["properties"])
        coords = feat.get("geometry", {}).get("coordinates")
        if coords:
            props["lon"], props["lat"] = coords[0], coords[1]
        rows.append(props)
    cols = ["block_id", "year", *PROFILE_BANDS, "lon", "lat"]
    return pd.DataFrame(rows).reindex(columns=cols)


def fetch_table(table: ee.FeatureCollection) -> pd.DataFrame:
    """Pull a results table in one getInfo. Fine below a few thousand rows;
    use export_table_to_drive when this starts timing out."""
    info = table.getInfo()
    # Fully cloud-masked scenes have no median/percentile property in EE. A
    # DataFrame reindex retains those observations while giving callers a
    # stable schema (their statistics are NaN and valid_count is zero).
    raw = pd.DataFrame([f["properties"] for f in info["features"]]).reindex(
        columns=_RAW_NAMES
    )
    raw["valid_count"] = raw["valid_count"].fillna(0)
    return raw


def export_table_to_drive(
    table: ee.FeatureCollection, description: str = "block_timeseries_raw"
) -> ee.batch.Task:
    """Escape hatch for tables too large for getInfo: CSV to Drive, then drop
    the file into data/raw/ by hand."""
    task = ee.batch.Export.table.toDrive(
        collection=table,
        description=description,
        fileNamePrefix=description,
        fileFormat="CSV",
        selectors=_RAW_NAMES,
    )
    task.start()
    return task


def download_latest_drive_csv(name: str, destination: str | Path) -> Path:
    """Download the most recent non-trashed Drive CSV with an exact name.

    Earth Engine authentication includes Drive scope, so a completed table
    export can be materialized locally without a browser download. This is an
    extraction-boundary convenience; all analysis code remains offline.
    """
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload

    destination = Path(destination)
    service = build(
        "drive",
        "v3",
        credentials=ee.data.get_persistent_credentials(),
        cache_discovery=False,
    )
    result = (
        service.files()
        .list(
            q=f"name = '{name}' and trashed = false",
            orderBy="createdTime desc",
            pageSize=1,
            fields="files(id,name,createdTime)",
        )
        .execute()
    )
    files = result.get("files", [])
    if not files:
        raise FileNotFoundError(f"No Drive export named {name!r} was found.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    request = service.files().get_media(fileId=files[0]["id"])
    with destination.open("wb") as handle:
        downloader = MediaIoBaseDownload(handle, request)
        complete = False
        while not complete:
            _, complete = downloader.next_chunk()
    return destination


def ndvi_layer(img: ee.Image, region: ee.Geometry | None = None) -> ee.Image:
    """NDVI band for display, clipped to `region` when one is given."""
    ndvi = img.select("NDVI")
    return ndvi.clip(region) if region is not None else ndvi


def outline_layer(geom, color: str = "white", width: int = 2) -> ee.Image:
    """Unfilled outline of a shapely EPSG:32611 geometry, for display."""
    fc = ee.FeatureCollection([ee.Feature(to_ee_geometry(geom))])
    return fc.style(color=color, width=width, fillColor="00000000")


def outlines_layer(gdf: gpd.GeoDataFrame, color: str = "white", width: int = 2) -> ee.Image:
    """Unfilled outlines of every planted extent in `gdf`, for display."""
    fc = ee.FeatureCollection([ee.Feature(to_ee_geometry(g)) for g in gdf.geometry])
    return fc.style(color=color, width=width, fillColor="00000000")
