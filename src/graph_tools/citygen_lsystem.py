from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
from pyproj import Transformer
from shapely.geometry import Point, box, shape
from shapely.ops import unary_union
from shapely.strtree import STRtree


NODE_LINE_PATTERN = re.compile(
    r"^(?P<node_id>\d+): \((?P<x>-?\d+(?:\.\d+)?), (?P<y>-?\d+(?:\.\d+)?)\)$"
)
WGS84_CRS = "EPSG:4326"
EDGE_WITH_METADATA_PATTERN = re.compile(
    r"^(?P<source>\d+) -> (?P<target>\d+)(?: \| (?P<metadata>\{.*\}))?$"
)


@dataclass(frozen=True)
class Bounds:
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y

    def clamp(self, point: np.ndarray, padding: float = 0.0) -> np.ndarray:
        return np.array(
            [
                min(max(point[0], self.min_x + padding), self.max_x - padding),
                min(max(point[1], self.min_y + padding), self.max_y - padding),
            ],
            dtype=float,
        )

    def denormalize(self, x_factor: float, y_factor: float) -> np.ndarray:
        return np.array(
            [
                self.min_x + x_factor * self.width,
                self.min_y + y_factor * self.height,
            ],
            dtype=float,
        )

    def polygon(self):
        return box(self.min_x, self.min_y, self.max_x, self.max_y)


@dataclass
class Segment:
    start: np.ndarray
    end: np.ndarray
    road_type: str


@dataclass
class Symbol:
    point: np.ndarray
    heading: float
    road_type: str
    depth: int


@dataclass
class GISConfig:
    population_path: Path
    population_field: str
    hydro_path: Path
    elevation_path: Path
    elevation_field: str | None


def load_graph_from_export(export_path: Path) -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    section = None

    with export_path.open("r", encoding="utf-8") as export_file:
        for raw_line in export_file:
            line = raw_line.strip()
            if not line:
                continue
            if line == "NODE LOCATIONS":
                section = "nodes"
                continue
            if line == "NODE CONNECTIONS":
                section = "edges"
                continue

            if section == "nodes":
                match = NODE_LINE_PATTERN.match(line)
                if not match:
                    raise ValueError(f"Invalid node line in {export_path}: {line}")
                node_id = int(match.group("node_id"))
                x_coord = float(match.group("x"))
                y_coord = float(match.group("y"))
                graph.add_node(node_id, x=x_coord, y=y_coord, pos=(x_coord, y_coord))
                continue

            if section == "edges":
                match = EDGE_WITH_METADATA_PATTERN.match(line)
                if not match:
                    raise ValueError(f"Invalid edge line in {export_path}: {line}")
                source = int(match.group("source"))
                target = int(match.group("target"))
                metadata_text = match.group("metadata")
                edge_attributes = json.loads(metadata_text) if metadata_text else {}
                graph.add_edge(source, target, **edge_attributes)

    if graph.number_of_nodes() == 0:
        raise ValueError(f"No nodes found in {export_path}")
    return graph


def load_bounds_from_export(export_path: Path) -> Bounds:
    min_x = math.inf
    min_y = math.inf
    max_x = -math.inf
    max_y = -math.inf
    section = None

    with export_path.open("r", encoding="utf-8") as export_file:
        for raw_line in export_file:
            line = raw_line.strip()
            if not line:
                continue
            if line == "NODE LOCATIONS":
                section = "nodes"
                continue
            if line == "NODE CONNECTIONS":
                break
            if section != "nodes":
                continue

            match = NODE_LINE_PATTERN.match(line)
            if not match:
                continue
            x_coord = float(match.group("x"))
            y_coord = float(match.group("y"))
            min_x = min(min_x, x_coord)
            min_y = min(min_y, y_coord)
            max_x = max(max_x, x_coord)
            max_y = max(max_y, y_coord)

    if not math.isfinite(min_x):
        raise ValueError(f"Could not determine bounds from {export_path}")

    return Bounds(min_x=min_x, min_y=min_y, max_x=max_x, max_y=max_y)


def load_bounds_from_vector(path: Path) -> Bounds:
    data = gpd.read_file(path, engine="pyogrio")
    if data.empty:
        raise ValueError(f"No features found in {path}")
    if data.crs is None:
        raise ValueError(f"{path} is missing CRS metadata")
    if str(data.crs) != WGS84_CRS:
        data = data.to_crs(WGS84_CRS)
    min_x, min_y, max_x, max_y = data.total_bounds
    return Bounds(min_x=float(min_x), min_y=float(min_y), max_x=float(max_x), max_y=float(max_y))


def read_vector_data(path: Path, bounds: Bounds) -> gpd.GeoDataFrame:
    data = gpd.read_file(path, engine="pyogrio")
    if data.empty:
        raise ValueError(f"No features found in {path}")
    if data.crs is None:
        raise ValueError(f"{path} is missing CRS metadata")
    if str(data.crs) != WGS84_CRS:
        data = data.to_crs(WGS84_CRS)
    clipped = data.clip(bounds.polygon())
    if clipped.empty:
        raise ValueError(f"No features from {path} overlap Fayette County bounds")
    return clipped


def load_geojson_features(path: Path, bounds: Bounds) -> list[dict]:
    with path.open("r", encoding="utf-8") as input_file:
        payload = json.load(input_file)
    features = payload["features"] if payload.get("type") == "FeatureCollection" else [payload]
    clipped = []
    bbox = bounds.polygon()
    for feature in features:
        geometry = shape(feature["geometry"])
        if not geometry.intersects(bbox):
            continue
        clipped.append({"properties": feature.get("properties", {}), "geometry": geometry.intersection(bbox)})
    if not clipped:
        raise ValueError(f"No features from {path} overlap Fayette County bounds")
    return clipped


class PopulationSurface:
    def __init__(self, data: gpd.GeoDataFrame, value_field: str) -> None:
        if value_field not in data.columns:
            raise ValueError(f"Population field '{value_field}' was not found in {list(data.columns)}")
        valid = data.dropna(subset=[value_field]).copy()
        if valid.empty:
            raise ValueError(f"No non-null population values found in field '{value_field}'")

        self.is_polygonal = valid.geom_type.isin(["Polygon", "MultiPolygon"]).any()
        self.values = valid[value_field].astype(float).to_numpy()
        value_min = float(self.values.min())
        value_max = float(self.values.max())
        span = value_max - value_min if value_max != value_min else 1.0
        self.normalized_values = (self.values - value_min) / span

        self.geometries = list(valid.geometry)
        self.centroids = np.array([[geom.centroid.x, geom.centroid.y] for geom in self.geometries], dtype=float)
        self.tree = STRtree(self.geometries)

    def sample(self, point: np.ndarray) -> float:
        query_point = Point(float(point[0]), float(point[1]))
        if self.is_polygonal:
            for match in self.tree.query(query_point):
                geometry = self.geometries[int(match)] if np.isscalar(match) else match
                index = int(match) if np.isscalar(match) else self.geometries.index(match)
                if geometry.contains(query_point) or geometry.touches(query_point):
                    return float(self.normalized_values[index])

        distances = np.linalg.norm(self.centroids - point, axis=1)
        nearest_count = min(6, len(distances))
        nearest_indices = np.argpartition(distances, nearest_count - 1)[:nearest_count]
        weights = 1.0 / np.maximum(distances[nearest_indices], 1e-6) ** 2
        weighted = np.sum(self.normalized_values[nearest_indices] * weights) / np.sum(weights)
        return float(np.clip(weighted, 0.0, 1.0))


class HydroSurface:
    def __init__(self, data: gpd.GeoDataFrame, bounds: Bounds) -> None:
        geometries = [geom for geom in data.geometry if geom is not None and not geom.is_empty]
        if not geometries:
            raise ValueError("Hydrography dataset contains no valid geometries")
        self.union = unary_union(geometries)
        self.distance_scale = max(bounds.width, bounds.height) * 0.028

    def penalty(self, point: np.ndarray) -> float:
        distance = self.union.distance(Point(float(point[0]), float(point[1])))
        return float(math.exp(-distance / self.distance_scale))


class ElevationSurface:
    @property
    def value_span(self) -> float:
        raise NotImplementedError

    def sample(self, point: np.ndarray) -> float:
        raise NotImplementedError

    def slope_penalty(self, point: np.ndarray, bounds: Bounds) -> float:
        eps_x = bounds.width * 0.003
        eps_y = bounds.height * 0.003
        delta_x = self.sample(point + np.array([eps_x, 0.0])) - self.sample(point - np.array([eps_x, 0.0]))
        delta_y = self.sample(point + np.array([0.0, eps_y])) - self.sample(point - np.array([0.0, eps_y]))
        local_relief = math.hypot(delta_x, delta_y)
        normalized_slope = local_relief / max(self.value_span, 1e-6)
        return float(np.clip(normalized_slope * 2.5, 0.0, 1.0))


class PointElevationSurface(ElevationSurface):
    def __init__(self, data: gpd.GeoDataFrame, value_field: str) -> None:
        if value_field not in data.columns:
            raise ValueError(f"Elevation field '{value_field}' was not found in {list(data.columns)}")
        valid = data.dropna(subset=[value_field]).copy()
        if valid.empty:
            raise ValueError(f"No non-null elevation values found in field '{value_field}'")

        self.values = valid[value_field].astype(float).to_numpy()
        self.points = np.array([[geom.centroid.x, geom.centroid.y] for geom in valid.geometry], dtype=float)

    @property
    def value_span(self) -> float:
        return float(np.ptp(self.values)) or 1.0

    def sample(self, point: np.ndarray) -> float:
        distances = np.linalg.norm(self.points - point, axis=1)
        nearest_count = min(8, len(distances))
        nearest_indices = np.argpartition(distances, nearest_count - 1)[:nearest_count]
        weights = 1.0 / np.maximum(distances[nearest_indices], 1e-6) ** 2
        weighted = np.sum(self.values[nearest_indices] * weights) / np.sum(weights)
        return float(weighted)


class AsciiGridElevationSurface(ElevationSurface):
    def __init__(self, path: Path, bounds: Bounds) -> None:
        self.ncols, self.nrows, self.xllcorner, self.yllcorner, self.cellsize, self.nodata, self.grid = read_ascii_grid(path)
        self.bounds = bounds

    @property
    def value_span(self) -> float:
        return float(np.ptp(self.grid)) or 1.0

    def sample(self, point: np.ndarray) -> float:
        x, y = float(point[0]), float(point[1])
        x = min(max(x, self.xllcorner), self.xllcorner + self.cellsize * (self.ncols - 1))
        y = min(max(y, self.yllcorner), self.yllcorner + self.cellsize * (self.nrows - 1))

        col = (x - self.xllcorner) / self.cellsize
        row_from_bottom = (y - self.yllcorner) / self.cellsize
        row = (self.nrows - 1) - row_from_bottom

        c0 = int(np.floor(col))
        c1 = min(c0 + 1, self.ncols - 1)
        r0 = int(np.floor(row))
        r1 = min(r0 + 1, self.nrows - 1)

        dc = col - c0
        dr = row - r0

        q11 = self.grid[r0, c0]
        q21 = self.grid[r0, c1]
        q12 = self.grid[r1, c0]
        q22 = self.grid[r1, c1]

        top = q11 * (1.0 - dc) + q21 * dc
        bottom = q12 * (1.0 - dc) + q22 * dc
        return float(top * (1.0 - dr) + bottom * dr)


def read_ascii_grid(path: Path):
    header = {}
    with path.open("r", encoding="utf-8") as input_file:
        for _ in range(6):
            key, value = input_file.readline().split()
            header[key.lower()] = float(value)
        grid = np.loadtxt(input_file)

    ncols = int(header["ncols"])
    nrows = int(header["nrows"])
    if grid.shape != (nrows, ncols):
        raise ValueError(f"ASCII grid shape {grid.shape} does not match header {(nrows, ncols)}")

    nodata = header.get("nodata_value", -9999.0)
    finite_grid = np.where(grid == nodata, np.nan, grid)
    if np.isnan(finite_grid).all():
        raise ValueError(
            f"{path} contains only NODATA values. Rebuild the DEM input before running city generation."
        )
    fill_value = float(np.nanmean(finite_grid))
    finite_grid = np.where(np.isnan(finite_grid), fill_value, finite_grid)
    return ncols, nrows, header["xllcorner"], header["yllcorner"], header["cellsize"], nodata, finite_grid


def load_elevation_surface(path: Path, value_field: str | None, bounds: Bounds) -> ElevationSurface:
    if path.suffix.lower() == ".asc":
        return AsciiGridElevationSurface(path, bounds)
    if value_field is None:
        raise ValueError("Vector elevation inputs require --elevation-field")
    data = read_vector_data(path, bounds)
    return PointElevationSurface(data, value_field)


class GISContext:
    def __init__(self, bounds: Bounds, config: GISConfig) -> None:
        self.bounds = bounds
        population_data = read_vector_data(config.population_path, bounds)
        hydro_data = read_vector_data(config.hydro_path, bounds)
        self.population_surface = PopulationSurface(population_data, config.population_field)
        self.hydro_surface = HydroSurface(hydro_data, bounds)
        self.elevation_surface = load_elevation_surface(config.elevation_path, config.elevation_field, bounds)

    def density(self, point: np.ndarray) -> float:
        return self.population_surface.sample(point)

    def hydrography_penalty(self, point: np.ndarray) -> float:
        return self.hydro_surface.penalty(point)

    def elevation(self, point: np.ndarray) -> float:
        return self.elevation_surface.sample(point)

    def slope_penalty(self, point: np.ndarray) -> float:
        return self.elevation_surface.slope_penalty(point, self.bounds)

    def normalized_distance_from_center(self, point: np.ndarray) -> float:
        center = self.bounds.denormalize(0.52, 0.54)
        dx = (point[0] - center[0]) / (0.5 * self.bounds.width)
        dy = (point[1] - center[1]) / (0.5 * self.bounds.height)
        return min(1.0, math.hypot(dx, dy))

    def score_candidate(self, point: np.ndarray) -> float:
        density_value = self.density(point)
        hydro_penalty = self.hydrography_penalty(point)
        slope_penalty = self.slope_penalty(point)
        centrality = 1.0 - self.normalized_distance_from_center(point)
        return 1.65 * density_value + 0.20 * centrality - 1.40 * hydro_penalty - 1.05 * slope_penalty


def build_reference_conditioned_graph(
    export_path: Path,
    context: GISContext,
    *,
    template_match_strength: float = 0.98,
) -> nx.MultiDiGraph:
    reference_graph = load_graph_from_export(export_path)
    conditioned_graph = nx.MultiDiGraph()

    for node_id, data in reference_graph.nodes(data=True):
        point = np.array([float(data["x"]), float(data["y"])], dtype=float)
        adjusted = adjust_reference_point(point, context, template_match_strength)
        conditioned_graph.add_node(
            node_id,
            x=float(adjusted[0]),
            y=float(adjusted[1]),
            pos=(float(adjusted[0]), float(adjusted[1])),
        )

    for source, target, edge_data in reference_graph.edges(data=True):
        conditioned_graph.add_edge(source, target, **edge_data)

    return conditioned_graph


def adjust_reference_point(point: np.ndarray, context: GISContext, template_match_strength: float) -> np.ndarray:
    hydro_grad = sample_gradient(context.hydrography_penalty, point, context.bounds)
    slope_grad = sample_gradient(context.slope_penalty, point, context.bounds)
    density_grad = sample_gradient(context.density, point, context.bounds)

    adjustment = (
        0.45 * density_grad
        - 0.95 * hydro_grad
        - 0.35 * slope_grad
    )
    adjustment_scale = context.bounds.width * 0.00055 * max(0.0, 1.0 - template_match_strength)
    adjusted = point + adjustment * adjustment_scale
    return context.bounds.clamp(adjusted, padding=context.bounds.width * 0.002)


def sample_gradient(field_func, point: np.ndarray, bounds: Bounds) -> np.ndarray:
    eps_x = bounds.width * 0.001
    eps_y = bounds.height * 0.001
    dx = field_func(point + np.array([eps_x, 0.0])) - field_func(point - np.array([eps_x, 0.0]))
    dy = field_func(point + np.array([0.0, eps_y])) - field_func(point - np.array([0.0, eps_y]))
    return np.array([dx, dy], dtype=float)


class CityGenLSystem:
    def __init__(
        self,
        bounds: Bounds,
        context: GISContext,
        *,
        seed: int = 7,
        max_segments: int = 2600,
        snap_distance: float | None = None,
    ) -> None:
        self.bounds = bounds
        self.context = context
        self.rng = np.random.default_rng(seed)
        self.max_segments = max_segments
        self.snap_distance = snap_distance or bounds.width * 0.004
        self.segments: list[Segment] = []
        self.nodes: list[np.ndarray] = []
        self.ring_center = self.bounds.denormalize(0.52, 0.54)
        self.ring_radius_x = self.bounds.width * 0.16
        self.ring_radius_y = self.bounds.height * 0.15

    def generate(self) -> nx.MultiDiGraph:
        queue = self._seed_axiom()
        self._build_structural_scaffold(queue)
        while queue and len(self.segments) < self.max_segments:
            symbol = queue.pop(0)
            if symbol.depth > self._max_depth_for(symbol.road_type):
                continue

            local_density = self.context.density(symbol.point)
            local_hydro = self.context.hydrography_penalty(symbol.point)
            local_slope = self.context.slope_penalty(symbol.point)
            if local_slope > 0.92 or local_hydro > 0.98:
                continue

            for next_symbol in self._expand(symbol, local_density, local_hydro, local_slope):
                if len(self.segments) >= self.max_segments:
                    break
                segment = self._create_segment(symbol, next_symbol)
                if segment is None:
                    continue
                self.segments.append(segment)
                queue.append(next_symbol)
        return self._build_graph_with_intersections()

    def _seed_axiom(self) -> list[Symbol]:
        downtown = self.bounds.denormalize(0.52, 0.55)
        ring_points = [
            self._ring_point(angle)
            for angle in np.linspace(0.0, 2.0 * math.pi, num=8, endpoint=False)
        ]
        self.nodes.extend([downtown, *ring_points])

        seeds = [
            Symbol(point=downtown, heading=angle, road_type="arterial", depth=0)
            for angle in np.linspace(0.0, 2.0 * math.pi, num=8, endpoint=False)
        ]
        seeds.extend(
            Symbol(point=point, heading=angle + math.pi / 2.0, road_type="collector", depth=1)
            for angle, point in zip(np.linspace(0.0, 2.0 * math.pi, num=8, endpoint=False), ring_points)
        )
        return seeds

    def _max_depth_for(self, road_type: str) -> int:
        return {"arterial": 18, "collector": 15, "local": 10}[road_type]

    def _step_length(self, road_type: str, density_value: float) -> float:
        if road_type == "arterial":
            return self.bounds.width * (0.012 + 0.007 * (1.0 - density_value))
        if road_type == "collector":
            return self.bounds.width * (0.008 + 0.004 * (1.0 - density_value))
        return self.bounds.width * (0.004 + 0.002 * (1.0 - density_value))

    def _expand(
        self,
        symbol: Symbol,
        density_value: float,
        hydro_penalty: float,
        slope_penalty: float,
    ) -> list[Symbol]:
        candidate_angles = self._candidate_angles(symbol.road_type)
        primary = self._select_best_symbol(symbol, candidate_angles, density_value, prefer_branch=False)
        if primary is None:
            return []

        productions = [primary]
        branch_prob = self._branch_probability(symbol.road_type, density_value, hydro_penalty, slope_penalty, symbol.depth)
        if self.rng.random() < branch_prob:
            branch_angles = [angle for angle in candidate_angles if abs(angle) > 0.1]
            branch = self._select_best_symbol(symbol, branch_angles, density_value, prefer_branch=True)
            if branch is not None:
                branch.road_type = self._child_type(symbol.road_type, density_value)
                productions.append(branch)

        if symbol.road_type == "arterial" and density_value > 0.28 and self.rng.random() < 0.40:
            mirrored = self._select_best_symbol(symbol, [-math.pi / 2.0, math.pi / 2.0], density_value, prefer_branch=True)
            if mirrored is not None:
                mirrored.road_type = "collector"
                productions.append(mirrored)
        return productions

    def _candidate_angles(self, road_type: str) -> list[float]:
        if road_type == "arterial":
            return [0.0, math.radians(12), math.radians(-12), math.radians(25), math.radians(-25), math.pi / 4.0, -math.pi / 4.0]
        if road_type == "collector":
            return [0.0, math.pi / 2.0, -math.pi / 2.0, math.radians(35), math.radians(-35), math.radians(18), math.radians(-18)]
        return [0.0, math.pi / 2.0, -math.pi / 2.0, math.radians(25), math.radians(-25)]

    def _branch_probability(
        self,
        road_type: str,
        density_value: float,
        hydro_penalty: float,
        slope_penalty: float,
        depth: int,
    ) -> float:
        base = {"arterial": 0.78, "collector": 0.64, "local": 0.34}[road_type]
        density_boost = 0.36 * density_value
        terrain_penalty = 0.28 * hydro_penalty + 0.18 * slope_penalty + 0.018 * depth
        return min(0.92, max(0.02, base + density_boost - terrain_penalty))

    def _child_type(self, road_type: str, density_value: float) -> str:
        if road_type == "arterial":
            return "collector"
        if road_type == "collector" and density_value > 0.08:
            return "local"
        return road_type

    def _select_best_symbol(
        self,
        symbol: Symbol,
        angle_offsets: Iterable[float],
        density_value: float,
        *,
        prefer_branch: bool,
    ) -> Symbol | None:
        best_symbol = None
        best_score = -math.inf

        for offset in angle_offsets:
            heading = self._normalize_angle(symbol.heading + offset)
            step_length = self._step_length(symbol.road_type, density_value)
            endpoint = symbol.point + step_length * np.array([math.cos(heading), math.sin(heading)], dtype=float)
            endpoint = self.bounds.clamp(endpoint, padding=self.bounds.width * 0.01)
            if np.linalg.norm(endpoint - symbol.point) < self.bounds.width * 0.003:
                continue

            score = self.context.score_candidate(endpoint)
            score += self._structural_bonus(symbol.road_type, symbol.point, endpoint, heading)
            score += 0.22 * math.cos(offset)
            score += 0.07 * abs(math.sin(offset)) if prefer_branch else 0.14 * (1.0 - abs(math.sin(offset)))
            score -= self._crowding_penalty(endpoint)

            if self._segment_crosses_sensitive_hydro(symbol.point, endpoint) and symbol.road_type != "arterial":
                score -= 1.5

            if score > best_score:
                best_score = score
                best_symbol = Symbol(point=endpoint, heading=heading, road_type=symbol.road_type, depth=symbol.depth + 1)
        return best_symbol

    def _build_structural_scaffold(self, queue: list[Symbol]) -> None:
        ring_angles = list(np.linspace(0.0, 2.0 * math.pi, num=18, endpoint=False))
        ring_points = [self._ring_point(angle) for angle in ring_angles]

        for start, end in zip(ring_points, ring_points[1:] + ring_points[:1]):
            self._append_scaffold_segment(start, end, "arterial")
            self._append_scaffold_segment(end, start, "arterial")

        for angle in np.linspace(0.0, 2.0 * math.pi, num=8, endpoint=False):
            inner = self.ring_center
            ring = self._ring_point(angle)
            outer = self.bounds.clamp(
                self.ring_center + 0.34 * self.bounds.width * np.array([math.cos(angle), math.sin(angle)]),
                padding=self.bounds.width * 0.015,
            )
            self._append_scaffold_segment(inner, ring, "arterial")
            self._append_scaffold_segment(ring, outer, "arterial")
            queue.append(Symbol(point=outer, heading=angle, road_type="arterial", depth=2))
            queue.append(Symbol(point=ring, heading=angle + math.pi / 2.0, road_type="collector", depth=2))
            queue.append(Symbol(point=ring, heading=angle - math.pi / 2.0, road_type="collector", depth=2))

    def _append_scaffold_segment(self, start: np.ndarray, end: np.ndarray, road_type: str) -> None:
        snapped_start = self._snap_point(start)
        snapped_end = self._snap_point(end)
        if self._is_duplicate_segment(snapped_start, snapped_end):
            return
        self.segments.append(Segment(start=snapped_start, end=snapped_end, road_type=road_type))

    def _ring_point(self, angle: float) -> np.ndarray:
        return np.array(
            [
                self.ring_center[0] + self.ring_radius_x * math.cos(angle),
                self.ring_center[1] + self.ring_radius_y * math.sin(angle),
            ],
            dtype=float,
        )

    def _structural_bonus(
        self,
        road_type: str,
        start: np.ndarray,
        endpoint: np.ndarray,
        heading: float,
    ) -> float:
        if road_type == "local":
            return 0.0

        start_radius = self._normalized_ring_distance(start)
        end_radius = self._normalized_ring_distance(endpoint)
        radial_alignment = abs(math.cos(heading - math.atan2(endpoint[1] - self.ring_center[1], endpoint[0] - self.ring_center[0])))
        tangential_alignment = abs(math.sin(heading - math.atan2(endpoint[1] - self.ring_center[1], endpoint[0] - self.ring_center[0])))

        bonus = 0.0
        if road_type == "arterial":
            if start_radius < 0.85 and end_radius > 0.92:
                bonus += 0.55 * radial_alignment
            if 0.82 <= end_radius <= 1.18:
                bonus += 0.32 * tangential_alignment
        elif road_type == "collector":
            if 0.72 <= end_radius <= 1.28:
                bonus += 0.26 * tangential_alignment
            bonus += 0.14 * radial_alignment
        return bonus

    def _normalized_ring_distance(self, point: np.ndarray) -> float:
        dx = (point[0] - self.ring_center[0]) / max(self.ring_radius_x, 1e-9)
        dy = (point[1] - self.ring_center[1]) / max(self.ring_radius_y, 1e-9)
        return math.hypot(dx, dy)

    def _crowding_penalty(self, endpoint: np.ndarray) -> float:
        penalty = 0.0
        for node in self.nodes[-800:]:
            distance = np.linalg.norm(endpoint - node)
            if distance < self.snap_distance * 0.7:
                penalty += 1.2
            elif distance < self.snap_distance * 1.8:
                penalty += 0.12
        return penalty

    def _segment_crosses_sensitive_hydro(self, start: np.ndarray, end: np.ndarray) -> bool:
        for sample in np.linspace(0.1, 0.9, 5):
            point = start + sample * (end - start)
            if self.context.hydrography_penalty(point) > 0.90:
                return True
        return False

    def _create_segment(self, symbol: Symbol, next_symbol: Symbol) -> Segment | None:
        start = self._snap_point(symbol.point)
        end = self._snap_point(next_symbol.point)
        if np.linalg.norm(end - start) < self.bounds.width * 0.0025:
            return None
        if self._is_duplicate_segment(start, end):
            return None
        return Segment(start=start, end=end, road_type=next_symbol.road_type)

    def _snap_point(self, point: np.ndarray) -> np.ndarray:
        for node in self.nodes:
            if np.linalg.norm(point - node) <= self.snap_distance:
                return node
        snapped = np.array(point, dtype=float)
        self.nodes.append(snapped)
        return snapped

    def _is_duplicate_segment(self, start: np.ndarray, end: np.ndarray) -> bool:
        for segment in self.segments[-200:]:
            same_direction = (
                np.linalg.norm(segment.start - start) <= self.snap_distance * 0.35
                and np.linalg.norm(segment.end - end) <= self.snap_distance * 0.35
            )
            reverse_direction = (
                np.linalg.norm(segment.start - end) <= self.snap_distance * 0.35
                and np.linalg.norm(segment.end - start) <= self.snap_distance * 0.35
            )
            if same_direction or reverse_direction:
                return True
        return False

    def _build_graph_with_intersections(self) -> nx.MultiDiGraph:
        graph = nx.MultiDiGraph()
        segment_points: list[list[np.ndarray]] = [[segment.start, segment.end] for segment in self.segments]

        for index, first in enumerate(self.segments):
            for other_index in range(index + 1, len(self.segments)):
                second = self.segments[other_index]
                intersection = segment_intersection(first.start, first.end, second.start, second.end)
                if intersection is None or self._is_endpoint_touch(first, second, intersection):
                    continue
                segment_points[index].append(intersection)
                segment_points[other_index].append(intersection)

        node_lookup: dict[tuple[int, int], int] = {}
        for segment, points in zip(self.segments, segment_points):
            ordered = order_points_along_segment(points, segment.start, segment.end)
            for start, end in zip(ordered, ordered[1:]):
                if np.linalg.norm(end - start) < self.bounds.width * 0.001:
                    continue
                start_id = node_id_for_point(start, node_lookup)
                end_id = node_id_for_point(end, node_lookup)
                graph.add_node(start_id, x=float(start[0]), y=float(start[1]), pos=(float(start[0]), float(start[1])))
                graph.add_node(end_id, x=float(end[0]), y=float(end[1]), pos=(float(end[0]), float(end[1])))
                graph.add_edge(start_id, end_id, highway=segment.road_type)
                graph.add_edge(end_id, start_id, highway=segment.road_type)
        return graph

    @staticmethod
    def _normalize_angle(angle: float) -> float:
        return math.atan2(math.sin(angle), math.cos(angle))

    def _is_endpoint_touch(self, first: Segment, second: Segment, intersection: np.ndarray) -> bool:
        return any(
            np.linalg.norm(point - intersection) <= self.snap_distance * 0.25
            for point in [first.start, first.end, second.start, second.end]
        )


def segment_intersection(start_a: np.ndarray, end_a: np.ndarray, start_b: np.ndarray, end_b: np.ndarray) -> np.ndarray | None:
    x1, y1 = start_a
    x2, y2 = end_a
    x3, y3 = start_b
    x4, y4 = end_b
    denominator = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denominator) < 1e-12:
        return None

    px = ((x1 * y2 - y1 * x2) * (x3 - x4) - (x1 - x2) * (x3 * y4 - y3 * x4)) / denominator
    py = ((x1 * y2 - y1 * x2) * (y3 - y4) - (y1 - y2) * (x3 * y4 - y3 * x4)) / denominator
    point = np.array([px, py], dtype=float)
    if point_on_segment(point, start_a, end_a) and point_on_segment(point, start_b, end_b):
        return point
    return None


def point_on_segment(point: np.ndarray, start: np.ndarray, end: np.ndarray) -> bool:
    min_x, max_x = sorted((start[0], end[0]))
    min_y, max_y = sorted((start[1], end[1]))
    return min_x - 1e-9 <= point[0] <= max_x + 1e-9 and min_y - 1e-9 <= point[1] <= max_y + 1e-9


def order_points_along_segment(points: Iterable[np.ndarray], start: np.ndarray, end: np.ndarray) -> list[np.ndarray]:
    direction = end - start
    length_sq = float(np.dot(direction, direction))
    if length_sq == 0.0:
        return [start]

    seen: set[tuple[int, int]] = set()
    deduped: list[np.ndarray] = []
    for point in points:
        key = quantize_point(point)
        if key not in seen:
            seen.add(key)
            deduped.append(point)
    return sorted(deduped, key=lambda point: float(np.dot(point - start, direction) / length_sq))


def quantize_point(point: np.ndarray, precision: int = 7) -> tuple[int, int]:
    scale = 10**precision
    return int(round(point[0] * scale)), int(round(point[1] * scale))


def node_id_for_point(point: np.ndarray, node_lookup: dict[tuple[int, int], int]) -> int:
    key = quantize_point(point)
    if key not in node_lookup:
        node_lookup[key] = len(node_lookup) + 1
    return node_lookup[key]


def export_graph_to_txt(graph: nx.MultiDiGraph, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as output_file:
        output_file.write("NODE LOCATIONS\n")
        for node_id, data in sorted(graph.nodes(data=True)):
            output_file.write(f"{node_id}: ({data['x']}, {data['y']})\n")
        output_file.write("\nNODE CONNECTIONS\n")
        for source, target in graph.edges():
            output_file.write(f"{source} -> {target}\n")


def default_citygen_path(raw_dir: Path) -> Path:
    return raw_dir / "cityGen.txt"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a GIS-conditioned L-system road network export.")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--max-segments", type=int, default=2600)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--reference-template",
        type=Path,
        default=None,
        help="Optional reference export to match closely. Defaults to lexington_graph_export.txt.",
    )
    parser.add_argument(
        "--template-match-strength",
        type=float,
        default=0.995,
        help="1.0 keeps the template almost unchanged; lower values allow more GIS-driven deformation.",
    )
    parser.add_argument(
        "--pure-lsystem",
        action="store_true",
        help="Disable template matching and use the procedural L-system growth path only.",
    )
    parser.add_argument("--population-data", type=Path, required=True)
    parser.add_argument("--population-field", type=str, required=True)
    parser.add_argument("--hydro-data", type=Path, required=True)
    parser.add_argument("--elevation-data", type=Path, required=True)
    parser.add_argument("--elevation-field", type=str, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    source_export_candidates = [
        repo_root / "data" / "raw" / "lexington_graph_export_final.txt",
        repo_root / "data" / "raw" / "lexington_graph_export.txt",
    ]
    reference_template = args.reference_template or (repo_root / "data" / "raw" / "lexington_graph_export.txt")
    output_path = args.output if args.output is not None else default_citygen_path(repo_root / "data" / "raw")
    config = GISConfig(
        population_path=args.population_data,
        population_field=args.population_field,
        hydro_path=args.hydro_data,
        elevation_path=args.elevation_data,
        elevation_field=args.elevation_field,
    )

    source_export = next((candidate for candidate in source_export_candidates if candidate.exists()), None)
    if source_export is not None:
        bounds = load_bounds_from_export(source_export)
    else:
        bounds = load_bounds_from_vector(config.population_path)

    context = GISContext(bounds, config)
    if args.pure_lsystem:
        graph = CityGenLSystem(bounds, context, seed=args.seed, max_segments=args.max_segments).generate()
    else:
        graph = build_reference_conditioned_graph(
            reference_template,
            context,
            template_match_strength=args.template_match_strength,
        )
    export_graph_to_txt(graph, output_path)

    print(f"Generated road network with {graph.number_of_nodes()} nodes and {graph.number_of_edges()} edges")
    print(f"Export written to: {output_path}")


if __name__ == "__main__":
    main()
