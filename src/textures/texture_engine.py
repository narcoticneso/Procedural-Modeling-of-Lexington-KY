from __future__ import annotations

import numpy as np
import pyvista as pv
from typing import List, Dict, Any, Tuple, Optional

from textures.material_library import MaterialLibrary, LABEL_IDS, WALL_LABEL_BY_TYPE
from textures.uv_mapper import compute_uv

ROOF_Z_THRESHOLD = 0.7
GROUND_Z_THRESHOLD = 0.5


def classify_face(normal: np.ndarray, avg_z: float, building_type: str = "") -> str:
    if normal[2] > ROOF_Z_THRESHOLD:
        if avg_z < GROUND_Z_THRESHOLD:
            return "floor"
        return "roof"
    if normal[2] < -ROOF_Z_THRESHOLD:
        return "floor"
    return WALL_LABEL_BY_TYPE.get(building_type, "wall")


def _parse_triangles(faces_array: np.ndarray) -> List[np.ndarray]:
    triangles = []
    i = 0
    while i < len(faces_array):
        n = faces_array[i]
        if n == 3:
            triangles.append(faces_array[i + 1 : i + 4])
        i += 1 + n
    return triangles


class TextureEngine:

    def __init__(self) -> None:
        self.materials = MaterialLibrary()

    def process_building(
        self,
        mesh: pv.PolyData,
        building: Dict[str, Any],
    ) -> Optional[Dict[str, np.ndarray]]:
        if mesh.n_points == 0 or mesh.n_cells == 0:
            return None

        tri_mesh = mesh.triangulate()
        points = np.array(tri_mesh.points, dtype=np.float32)
        face_normals = np.array(tri_mesh.face_normals, dtype=np.float32)
        triangles = _parse_triangles(np.array(tri_mesh.faces))

        all_positions = []
        all_normals = []
        all_uvs = []
        all_labels = []

        for face_idx, indices in enumerate(triangles):
            if face_idx >= len(face_normals):
                break

            normal = face_normals[face_idx]
            verts = points[indices]
            avg_z = float(verts[:, 2].mean())
            building_type = building.get("building_type", "")
            label = classify_face(normal, avg_z, building_type)

            if label == "floor":
                continue
            tile_scale = self.materials.get_tile_scale(label)
            uvs = compute_uv(verts, normal, tile_scale)
            label_id = self.materials.get_label_id(label)

            all_positions.append(verts)
            all_normals.append(np.tile(normal, (3, 1)))
            all_uvs.append(uvs)
            all_labels.append(np.full(3, label_id, dtype=np.float32))

        if not all_positions:
            return None

        return {
            "positions": np.vstack(all_positions).astype(np.float32),
            "normals": np.vstack(all_normals).astype(np.float32),
            "uvs": np.vstack(all_uvs).astype(np.float32),
            "label_ids": np.concatenate(all_labels).astype(np.float32),
        }

    def process_all(
        self,
        mesh_building_pairs: List[Tuple[pv.PolyData, Dict[str, Any]]],
    ) -> Dict[str, np.ndarray]:
        all_positions = []
        all_normals = []
        all_uvs = []
        all_labels = []

        for mesh, building in mesh_building_pairs:
            result = self.process_building(mesh, building)
            if result is not None:
                all_positions.append(result["positions"])
                all_normals.append(result["normals"])
                all_uvs.append(result["uvs"])
                all_labels.append(result["label_ids"])

        if not all_positions:
            return {
                "positions": np.zeros((0, 3), dtype=np.float32),
                "normals": np.zeros((0, 3), dtype=np.float32),
                "uvs": np.zeros((0, 2), dtype=np.float32),
                "label_ids": np.zeros(0, dtype=np.float32),
            }

        return {
            "positions": np.vstack(all_positions),
            "normals": np.vstack(all_normals),
            "uvs": np.vstack(all_uvs),
            "label_ids": np.concatenate(all_labels),
        }

    def build_ground_quad(
        self,
        min_x: float,
        max_x: float,
        min_y: float,
        max_y: float,
    ) -> Dict[str, np.ndarray]:
        z = -0.02
        positions = np.array([
            [min_x, min_y, z],
            [max_x, min_y, z],
            [max_x, max_y, z],
            [min_x, min_y, z],
            [max_x, max_y, z],
            [min_x, max_y, z],
        ], dtype=np.float32)

        normals = np.tile([0.0, 0.0, 1.0], (6, 1)).astype(np.float32)

        span = max(max_x - min_x, max_y - min_y, 1.0)
        tile_count = span / self.materials.get_tile_scale("ground")
        uvs = np.array([
            [0, 0], [tile_count, 0], [tile_count, tile_count],
            [0, 0], [tile_count, tile_count], [0, tile_count],
        ], dtype=np.float32)

        label_ids = np.full(6, LABEL_IDS["ground"], dtype=np.float32)

        return {
            "positions": positions,
            "normals": normals,
            "uvs": uvs,
            "label_ids": label_ids,
        }
