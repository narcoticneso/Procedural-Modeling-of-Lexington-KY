from __future__ import annotations

from typing import List, Tuple, Optional

import pyvista as pv

Point2D = List[float]


# Returns the min/max bounds of the footprint
def get_bounds(footprint: List[Point2D]) -> Tuple[float, float, float, float]:
    xs = [p[0] for p in footprint]
    ys = [p[1] for p in footprint]
    return min(xs), max(xs), min(ys), max(ys)


# Stable small hash from a building id string
def stable_direction_seed(building_id: Optional[str]) -> int:
    if not building_id:
        return 0
    return sum(ord(ch) for ch in building_id)


# Builds a flat roof directly from the top footprint
def make_flat_roof(
    footprint: List[Point2D],
    base_height: float
) -> pv.PolyData:
    if len(footprint) < 3:
        return pv.PolyData()

    points = [[x, y, base_height] for x, y in footprint]
    faces = [len(points)] + list(range(len(points)))
    return pv.PolyData(points, faces=faces).triangulate()


# Builds a simple gable roof from the actual top footprint
def make_gable_roof(
    footprint: List[Point2D],
    base_height: float,
    roof_height: float = 0.25
) -> pv.PolyData:
    if len(footprint) < 4:
        return make_flat_roof(footprint, base_height)

    min_x, max_x, min_y, max_y = get_bounds(footprint)
    width_x = max_x - min_x
    width_y = max_y - min_y

    # Ridge runs along the longer dimension, slope across the shorter one
    ridge_along_y = width_y >= width_x

    roof_points = []

    if ridge_along_y:
        mid_x = (min_x + max_x) / 2.0
        half_span = max((max_x - min_x) / 2.0, 1e-6)

        for x, y in footprint:
            dist = abs(x - mid_x)
            factor = max(0.0, 1.0 - dist / half_span)
            z = base_height + roof_height * factor
            roof_points.append([x, y, z])
    else:
        mid_y = (min_y + max_y) / 2.0
        half_span = max((max_y - min_y) / 2.0, 1e-6)

        for x, y in footprint:
            dist = abs(y - mid_y)
            factor = max(0.0, 1.0 - dist / half_span)
            z = base_height + roof_height * factor
            roof_points.append([x, y, z])

    faces = [len(roof_points)] + list(range(len(roof_points)))
    return pv.PolyData(roof_points, faces=faces).triangulate()


# Builds a shed roof from the actual top footprint
def make_shed_roof(
    footprint: List[Point2D],
    base_height: float,
    building_id: Optional[str] = None,
    roof_height: float = 0.18
) -> pv.PolyData:
    if len(footprint) < 4:
        return make_flat_roof(footprint, base_height)

    min_x, max_x, min_y, max_y = get_bounds(footprint)
    width_x = max_x - min_x
    width_y = max_y - min_y

    seed = stable_direction_seed(building_id)
    roof_points = []

    # Slope across the SHORTER dimension
    if width_x <= width_y:
        span = max(width_x, 1e-6)

        # flip direction based on building id
        rise_toward_positive = (seed % 2 == 0)

        for x, y in footprint:
            if rise_toward_positive:
                factor = (x - min_x) / span
            else:
                factor = (max_x - x) / span

            z = base_height + roof_height * factor
            roof_points.append([x, y, z])

    else:
        span = max(width_y, 1e-6)

        rise_toward_positive = (seed % 2 == 0)

        for x, y in footprint:
            if rise_toward_positive:
                factor = (y - min_y) / span
            else:
                factor = (max_y - y) / span

            z = base_height + roof_height * factor
            roof_points.append([x, y, z])

    faces = [len(roof_points)] + list(range(len(roof_points)))
    return pv.PolyData(roof_points, faces=faces).triangulate()


# Returns the proper roof mesh based on roof type
def make_roof_mesh(
    roof_type: str,
    footprint: List[Point2D],
    base_height: float,
    building_id: Optional[str] = None
) -> pv.PolyData:
    roof_type = (roof_type or "flat").lower()

    if roof_type == "gable":
        return make_gable_roof(footprint, base_height)

    if roof_type == "shed":
        return make_shed_roof(footprint, base_height, building_id=building_id)

    return make_flat_roof(footprint, base_height)