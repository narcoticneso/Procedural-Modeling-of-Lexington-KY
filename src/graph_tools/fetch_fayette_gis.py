from __future__ import annotations

import argparse
import io
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
from osgeo import gdal
from shapely.ops import unary_union


KENTUCKY_FIPS = "21"
FAYETTE_COUNTY_FIPS = "067"
ACS_YEAR = "2024"
TIGER_YEAR = "2024"
WGS84_CRS = "EPSG:4326"
AREA_CRS = "EPSG:5070"
POPULATION_FIELD = "population_density"
ELEVATION_RESOLUTION_METERS = 10

CENSUS_ACS_URL = f"https://api.census.gov/data/{ACS_YEAR}/acs/acs5"
TIGER_BG_URL = f"https://www2.census.gov/geo/tiger/TIGER{TIGER_YEAR}/BG/tl_{TIGER_YEAR}_{KENTUCKY_FIPS}_bg.zip"
USGS_NHD_FLOWLINE_URL = "https://hydro.nationalmap.gov/arcgis/rest/services/nhd/MapServer/6/query"
USGS_NHD_WATERBODY_URL = "https://hydro.nationalmap.gov/arcgis/rest/services/nhd/MapServer/12/query"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download Fayette County GIS inputs for city generation.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "data" / "raw" / "gis",
        help="Directory to write the prepared GIS files.",
    )
    parser.add_argument(
        "--census-api-key",
        type=str,
        default=None,
        help="Optional Census API key. Unauthenticated requests usually work for this small query.",
    )
    parser.add_argument(
        "--dem-resolution",
        type=int,
        default=ELEVATION_RESOLUTION_METERS,
        choices=(10, 30, 60),
        help="3DEP DEM resolution in meters.",
    )
    return parser.parse_args()


def require_success(response: requests.Response, context: str) -> None:
    try:
        response.raise_for_status()
    except requests.HTTPError as error:
        raise RuntimeError(f"{context} failed with {response.status_code}: {response.text[:500]}") from error


def download_block_groups() -> gpd.GeoDataFrame:
    response = requests.get(TIGER_BG_URL, timeout=120)
    require_success(response, "Downloading TIGER block groups")

    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        with tempfile.TemporaryDirectory() as temp_dir:
            archive.extractall(temp_dir)
            shapefiles = sorted(Path(temp_dir).glob("*.shp"))
            if not shapefiles:
                raise RuntimeError("Downloaded TIGER archive did not contain a shapefile")
            block_groups = gpd.read_file(shapefiles[0], engine="pyogrio")

    fayette = block_groups.loc[block_groups["COUNTYFP"] == FAYETTE_COUNTY_FIPS].copy()
    if fayette.empty:
        raise RuntimeError("No Fayette County block groups were found in the TIGER download")
    return fayette.to_crs(WGS84_CRS)


def download_acs_population(census_api_key: str | None) -> pd.DataFrame:
    params = {
        "get": "NAME,B01003_001E",
        "for": "block group:*",
        "in": f"state:{KENTUCKY_FIPS} county:{FAYETTE_COUNTY_FIPS} tract:*",
    }
    if census_api_key:
        params["key"] = census_api_key

    response = requests.get(CENSUS_ACS_URL, params=params, timeout=120)
    require_success(response, "Downloading ACS population")
    rows = response.json()
    frame = pd.DataFrame(rows[1:], columns=rows[0])
    frame["population"] = pd.to_numeric(frame["B01003_001E"], errors="coerce")
    frame["GEOID"] = frame["state"] + frame["county"] + frame["tract"] + frame["block group"]
    return frame[["GEOID", "population"]]


def build_population_surface(output_dir: Path, census_api_key: str | None) -> Path:
    block_groups = download_block_groups()
    acs = download_acs_population(census_api_key)

    population = block_groups.merge(acs, on="GEOID", how="left")
    if population["population"].isna().all():
        raise RuntimeError("ACS population join returned no usable values")

    projected = population.to_crs(AREA_CRS)
    area_sq_km = projected.geometry.area / 1_000_000.0
    population[POPULATION_FIELD] = population["population"] / area_sq_km
    population[POPULATION_FIELD] = population[POPULATION_FIELD].replace([np.inf, -np.inf], np.nan).fillna(0.0)

    output_path = output_dir / "fayette_population.geojson"
    population[["GEOID", "population", POPULATION_FIELD, "geometry"]].to_file(output_path, driver="GeoJSON")
    return output_path


def query_usgs_layer(url: str, bbox: tuple[float, float, float, float], out_fields: list[str]) -> dict[str, Any]:
    all_features: list[dict[str, Any]] = []
    page_size = 2000
    offset = 0

    while True:
        params = {
            "f": "geojson",
            "where": "1=1",
            "geometry": f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}",
            "geometryType": "esriGeometryEnvelope",
            "inSR": 4326,
            "outSR": 4326,
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": ",".join(out_fields),
            "returnGeometry": "true",
            "resultOffset": offset,
            "resultRecordCount": page_size,
        }
        response = requests.get(url, params=params, timeout=120)
        require_success(response, f"Querying USGS layer {url}")
        payload = response.json()
        features = payload.get("features", [])
        all_features.extend(features)

        exceeded = payload.get("properties", {}).get("exceededTransferLimit") or payload.get("exceededTransferLimit")
        if not exceeded or len(features) < page_size:
            break
        offset += page_size

    return {"type": "FeatureCollection", "features": all_features}


def build_hydro_surface(output_dir: Path, county_geometry) -> Path:
    bbox = county_geometry.bounds
    flowlines = query_usgs_layer(
        USGS_NHD_FLOWLINE_URL,
        bbox,
        ["GNIS_NAME", "FCode", "FType", "ReachCode"],
    )
    waterbodies = query_usgs_layer(
        USGS_NHD_WATERBODY_URL,
        bbox,
        ["GNIS_NAME", "FCode", "FType", "ReachCode"],
    )

    features = flowlines["features"] + waterbodies["features"]
    if not features:
        raise RuntimeError("USGS hydrography query returned no features for Fayette County")

    hydro = gpd.GeoDataFrame.from_features(features, crs=WGS84_CRS)
    hydro = hydro.clip(county_geometry)
    if hydro.empty:
        raise RuntimeError("Hydrography features did not overlap Fayette County after clipping")

    output_path = output_dir / "fayette_hydro.geojson"
    hydro.to_file(output_path, driver="GeoJSON")
    return output_path


def import_seamless_3dep():
    try:
        import seamless_3dep as s3dep  # type: ignore
    except ImportError as error:
        raise RuntimeError(
            "Elevation download requires the 'seamless-3dep' package. Install it with "
            "'pip install seamless-3dep'."
        ) from error
    return s3dep


def build_elevation_surface(output_dir: Path, county_geometry, resolution: int) -> Path:
    s3dep = import_seamless_3dep()
    bbox = county_geometry.bounds

    with tempfile.TemporaryDirectory() as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        tiff_files = s3dep.get_dem(bbox, temp_dir, res=resolution)
        output_path = output_dir / "fayette_dem.asc"
        write_tiffs_to_ascii_grid(tiff_files, output_path)
    return output_path


def write_tiffs_to_ascii_grid(tiff_files: list[Path], output_path: Path) -> None:
    if not tiff_files:
        raise RuntimeError("No DEM tiles were downloaded from 3DEP")

    vrt_path = output_path.with_suffix(".vrt")
    vrt = gdal.BuildVRT(str(vrt_path), [str(path) for path in tiff_files])
    if vrt is None:
        raise RuntimeError("GDAL failed to build a DEM mosaic VRT")
    vrt.FlushCache()
    vrt = None

    translated = gdal.Translate(
        str(output_path),
        str(vrt_path),
        format="AAIGrid",
        outputType=gdal.GDT_Float32,
        noData=-9999.0,
    )
    if translated is None:
        raise RuntimeError("GDAL failed to translate the DEM mosaic into ASCII grid format")
    translated.FlushCache()
    translated = None

    validate_ascii_grid(output_path)
    vrt_path.unlink(missing_ok=True)


def validate_ascii_grid(path: Path) -> None:
    with path.open("r", encoding="utf-8") as input_file:
        for _ in range(6):
            next(input_file)
        grid = np.loadtxt(input_file)

    valid = grid[grid != -9999.0]
    if valid.size == 0:
        raise RuntimeError(
            f"{path} contains only NODATA values. The DEM download likely failed or the geospatial "
            "library stack returned empty raster data."
        )


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    population_path = build_population_surface(output_dir, args.census_api_key)
    county_geometry = unary_union(gpd.read_file(population_path, engine="pyogrio").geometry)
    hydro_path = build_hydro_surface(output_dir, county_geometry)
    elevation_path = build_elevation_surface(output_dir, county_geometry, args.dem_resolution)

    print(f"Population surface written to: {population_path}")
    print(f"Hydro surface written to: {hydro_path}")
    print(f"Elevation surface written to: {elevation_path}")
    print(f"Use --population-field {POPULATION_FIELD} with citygen_lsystem.py")


if __name__ == "__main__":
    main()
