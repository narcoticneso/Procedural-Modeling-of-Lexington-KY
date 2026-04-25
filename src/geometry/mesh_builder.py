from __future__ import annotations

import json
from pathlib import Path
from typing import List, Dict, Any, Tuple

import pyvista as pv

from geometry.roof_builder import make_roof_mesh, _triangulate_polygon

# Spread the city out horizontally
XY_SCALE = 15000.0


# Loads building data from the JSON output of the building stage
def load_buildings_json(path: str | Path) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# Computes a scene origin so coordinates can be centered near (0, 0)
def get_scene_origin(buildings: List[Dict[str, Any]]) -> Tuple[float, float]:
    xs = []
    ys = []

    for building in buildings:
        for x, y in building["footprint"]:
            xs.append(float(x))
            ys.append(float(y))

    if not xs or not ys:
        return 0.0, 0.0

    return sum(xs) / len(xs), sum(ys) / len(ys)


# Shifts footprint coordinates to the origin and scales them for display
def normalize_footprint(
    footprint: List[List[float]],
    origin_x: float,
    origin_y: float
) -> List[List[float]]:
    return [
        [
            (float(x) - origin_x) * XY_SCALE,
            (float(y) - origin_y) * XY_SCALE,
        ]
        for x, y in footprint
    ]


# Builds a filled polygon surface from a footprint
def footprint_to_surface(footprint: List[List[float]]) -> pv.PolyData:
    if len(footprint) < 3:
        return pv.PolyData()

    points = [[x, y, 0.0] for x, y in footprint]
    return _triangulate_polygon(points)


# Creates one building mesh by extruding a footprint upward and optionally adding a roof
def build_mesh_for_building(
    building: Dict[str, Any],
    origin_x: float = 0.0,
    origin_y: float = 0.0
) -> pv.PolyData:
    footprint = normalize_footprint(building["footprint"], origin_x, origin_y)
    height = float(building["height"])
    roof_type = building.get("roof_type", "flat")

    base = footprint_to_surface(footprint)
    if base.n_points == 0:
        return pv.PolyData()

    try:
        body = base.extrude([0, 0, height], capping=True)
    except TypeError:
        body = base.extrude([0, 0, height])

    roof_mesh = make_roof_mesh(
        roof_type,
        footprint,
        height,
        building_id=building.get("building_id")
    )

    if roof_mesh.n_points > 0:
        return body.merge(roof_mesh)

    return body


# Builds meshes for every building in the list
def build_all_meshes(
    buildings: List[Dict[str, Any]],
    limit: int | None = None
) -> tuple[List[tuple[pv.PolyData, Dict[str, Any]]], tuple[float, float]]:
    if limit is not None:
        buildings = buildings[:limit]

    origin_x, origin_y = get_scene_origin(buildings)
    meshes: List[tuple[pv.PolyData, Dict[str, Any]]] = []

    for building in buildings:
        try:
            mesh = build_mesh_for_building(building, origin_x, origin_y)
            if mesh.n_points > 0:
                meshes.append((mesh, building))
        except Exception as e:
            print(f"Skipping {building.get('building_id', 'unknown')}: {e}")

    return meshes, (origin_x, origin_y)


# Merges all meshes into one mesh
def merge_meshes(meshes: List[pv.PolyData]) -> pv.PolyData:
    if not meshes:
        return pv.PolyData()

    merged = meshes[0]
    for mesh in meshes[1:]:
        merged = merged.merge(mesh)

    return merged


# Saves the combined mesh to disk
def save_mesh(mesh: pv.PolyData, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    mesh.save(path)