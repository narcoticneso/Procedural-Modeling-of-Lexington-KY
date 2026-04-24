import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
import pytest


def test_imports():
    from textures.material_library import MaterialLibrary, LABEL_IDS
    from textures.uv_mapper import compute_uv
    from textures.procedural import generate_brick, generate_concrete, generate_roof_tiles
    from textures.texture_engine import TextureEngine, classify_face


def test_label_ids():
    from textures.material_library import LABEL_IDS

    assert LABEL_IDS["wall"] == 0
    assert LABEL_IDS["roof"] == 1
    assert LABEL_IDS["window"] == 2
    assert LABEL_IDS["door"] == 3
    assert LABEL_IDS["ground"] == 4


def test_material_lookup():
    from textures.material_library import MaterialLibrary

    lib = MaterialLibrary()

    wall = lib.get_material("wall")
    assert wall["tile_scale"] == 2.0
    assert wall["texture_key"] == "brick"

    fallback = lib.get_material("unknown_label")
    assert fallback["color"] == [1.0, 0.0, 1.0, 1.0]


def test_classify_face():
    from textures.texture_engine import classify_face

    assert classify_face(np.array([0.0, 0.0, 1.0])) == "roof"
    assert classify_face(np.array([0.0, 0.0, -1.0])) == "floor"
    assert classify_face(np.array([1.0, 0.0, 0.0])) == "wall"
    assert classify_face(np.array([0.0, 1.0, 0.0])) == "wall"
    assert classify_face(np.array([0.7, 0.0, 0.5])) == "wall"


def test_uv_mapping_quad():
    from textures.uv_mapper import compute_uv

    verts = np.array([
        [0.0, 0.0, 0.0],
        [2.0, 0.0, 0.0],
        [2.0, 0.0, 3.0],
        [0.0, 0.0, 3.0],
    ], dtype=np.float32)

    normal = np.array([0.0, -1.0, 0.0])
    uvs = compute_uv(verts, normal, tile_scale=1.0)

    assert uvs.shape == (4, 2)
    assert uvs.dtype == np.float32


def test_procedural_textures():
    from textures.procedural import generate_brick, generate_concrete, generate_roof_tiles

    for gen in [generate_brick, generate_concrete, generate_roof_tiles]:
        img = gen(128, 128)
        assert img.shape == (128, 128, 4)
        assert img.dtype == np.uint8
        assert img[:, :, 3].min() == 255


def test_ground_quad():
    from textures.texture_engine import TextureEngine

    engine = TextureEngine()
    ground = engine.build_ground_quad(-100, 100, -100, 100)

    assert ground["positions"].shape == (6, 3)
    assert ground["normals"].shape == (6, 3)
    assert ground["uvs"].shape == (6, 2)
    assert ground["label_ids"].shape == (6,)
    assert np.all(ground["label_ids"] == 4)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
