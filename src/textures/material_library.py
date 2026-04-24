from __future__ import annotations

from typing import Dict, Any, List

LABEL_IDS = {
    "wall":   0,
    "roof":   1,
    "window": 2,
    "door":   3,
    "ground": 4,
}

MATERIALS: Dict[str, Dict[str, Any]] = {
    "wall": {
        "color": [0.76, 0.70, 0.65, 1.0],
        "tile_scale": 2.0,
        "specular": 0.1,
        "texture_key": "brick",
    },
    "roof": {
        "color": [0.45, 0.35, 0.30, 1.0],
        "tile_scale": 1.5,
        "specular": 0.05,
        "texture_key": "roof_tiles",
    },
    "window": {
        "color": [0.6, 0.75, 0.85, 1.0],
        "tile_scale": 1.0,
        "specular": 0.8,
        "texture_key": None,
    },
    "door": {
        "color": [0.4, 0.25, 0.15, 1.0],
        "tile_scale": 1.0,
        "specular": 0.2,
        "texture_key": None,
    },
    "ground": {
        "color": [0.35, 0.45, 0.25, 1.0],
        "tile_scale": 5.0,
        "specular": 0.0,
        "texture_key": "concrete",
    },
}

_FALLBACK_MATERIAL: Dict[str, Any] = {
    "color": [1.0, 0.0, 1.0, 1.0],
    "tile_scale": 1.0,
    "specular": 0.0,
    "texture_key": None,
}


class MaterialLibrary:

    def __init__(self) -> None:
        self._materials: Dict[str, Dict[str, Any]] = dict(MATERIALS)

    def get_material(self, label: str) -> Dict[str, Any]:
        return self._materials.get(label, _FALLBACK_MATERIAL)

    def get_label_id(self, label: str) -> int:
        return LABEL_IDS.get(label, len(LABEL_IDS))

    def get_color(self, label: str) -> List[float]:
        return self.get_material(label)["color"]

    def get_tile_scale(self, label: str) -> float:
        return self.get_material(label)["tile_scale"]
