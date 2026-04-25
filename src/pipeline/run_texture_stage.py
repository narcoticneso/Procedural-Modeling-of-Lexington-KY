import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import numpy as np
from vispy import app

from geometry.mesh_builder import load_buildings_json, build_all_meshes, XY_SCALE
from textures.texture_engine import TextureEngine
from textures.procedural import generate_brick, generate_concrete, generate_roof_tiles
from textures.renderer import CityRenderer


def _compute_bounds(positions: np.ndarray):
    if len(positions) == 0:
        return -1000.0, 1000.0, -1000.0, 1000.0
    return (
        float(positions[:, 0].min()),
        float(positions[:, 0].max()),
        float(positions[:, 1].min()),
        float(positions[:, 1].max()),
    )


def main() -> None:
    project_root = Path(__file__).resolve().parents[2]
    buildings_path = project_root / "data" / "processed" / "buildings.json"

    print("Loading buildings...")
    buildings = load_buildings_json(buildings_path)

    print("Building meshes...")
    mesh_pairs, (origin_x, origin_y) = build_all_meshes(buildings)

    print("Running texture engine...")
    engine = TextureEngine()
    buffers = engine.process_all(mesh_pairs)

    min_x, max_x, min_y, max_y = _compute_bounds(buffers["positions"])
    padding = max(max_x - min_x, max_y - min_y) * 0.1
    ground = engine.build_ground_quad(
        min_x - padding, max_x + padding,
        min_y - padding, max_y + padding,
    )

    buffers = {
        "positions": np.vstack([buffers["positions"], ground["positions"]]),
        "normals": np.vstack([buffers["normals"], ground["normals"]]),
        "uvs": np.vstack([buffers["uvs"], ground["uvs"]]),
        "label_ids": np.concatenate([buffers["label_ids"], ground["label_ids"]]),
    }

    textures = {
        "wall": generate_brick(),
        "roof": generate_roof_tiles(),
        "window": generate_concrete(256, 256),
        "door": generate_concrete(256, 256),
        "ground": generate_concrete(),
    }

    print(f"Processed {len(mesh_pairs)} buildings")
    print(f"Total vertices: {len(buffers['positions'])}")
    print()
    print("Controls:")
    print("  WASD       -> move camera")
    print("  Q/E        -> move up/down")
    print("  Left-drag  -> orbit camera")
    print("  Right-drag -> pan camera")
    print("  Scroll     -> zoom")
    print("  R          -> reset camera")
    print("  T          -> top-down view")
    print("  I          -> isometric view")

    renderer = CityRenderer(buffers, textures)
    app.run()


if __name__ == "__main__":
    main()
