from typing import List, Dict, Any, Optional

from shapely.geometry import Polygon


def shapely_polygon_to_lot(
    polygon: Polygon,
    lot_id: str,
    district: Optional[str] = None
) -> Dict[str, Any]:
    """
    Convert a Shapely polygon into the lot format expected by the building generator.
    """
    exterior_coords = list(polygon.exterior.coords)

    # Drop repeated final closing coordinate if present
    if len(exterior_coords) > 1 and exterior_coords[0] == exterior_coords[-1]:
        exterior_coords = exterior_coords[:-1]

    centroid = polygon.centroid

    return {
        "lot_id": lot_id,
        "polygon": [[float(x), float(y)] for x, y in exterior_coords],
        "centroid": [float(centroid.x), float(centroid.y)],
        "area": float(abs(polygon.area)),
        "road_access": True,
        "district": district,
        "metadata": {
            "source": "kaitlyn_polygonize"
        }
    }


def geoseries_to_lots(geoseries, default_district: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Convert a GeoSeries of Shapely polygons into a JSON-serializable lot list.
    """
    lots: List[Dict[str, Any]] = []

    for idx, polygon in enumerate(geoseries, start=1):
        if polygon.is_empty:
            continue
        if polygon.geom_type != "Polygon":
            continue

        lot = shapely_polygon_to_lot(
            polygon=polygon,
            lot_id=f"lot_{idx:05d}",
            district=default_district
        )
        lots.append(lot)

    return lots