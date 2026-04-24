from __future__ import annotations

import numpy as np


def compute_uv(
    vertices: np.ndarray,
    normal: np.ndarray,
    tile_scale: float = 1.0,
) -> np.ndarray:
    abs_normal = np.abs(normal)

    if abs_normal[2] >= abs_normal[0] and abs_normal[2] >= abs_normal[1]:
        u_axis, v_axis = 0, 1
    elif abs_normal[1] >= abs_normal[0]:
        u_axis, v_axis = 0, 2
    else:
        u_axis, v_axis = 1, 2

    scale = max(tile_scale, 1e-6)
    us = vertices[:, u_axis] / scale
    vs = vertices[:, v_axis] / scale

    return np.column_stack([us, vs]).astype(np.float32)
