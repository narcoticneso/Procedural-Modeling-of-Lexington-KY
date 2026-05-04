from __future__ import annotations

import numpy as np


def generate_brick(width: int = 256, height: int = 256) -> np.ndarray:
    img = np.zeros((height, width, 4), dtype=np.uint8)

    brick_r, brick_g, brick_b = 178, 120, 87
    img[:, :, 0] = brick_r
    img[:, :, 1] = brick_g
    img[:, :, 2] = brick_b
    img[:, :, 3] = 255

    mortar = np.array([200, 195, 185, 255], dtype=np.uint8)
    brick_h = height // 8
    brick_w = width // 4
    mortar_t = max(2, height // 64)

    for row in range(9):
        y = row * brick_h
        for t in range(mortar_t):
            if y + t < height:
                img[y + t, :] = mortar

    for row in range(8):
        y_start = row * brick_h + mortar_t
        y_end = (row + 1) * brick_h
        offset = (brick_w // 2) if row % 2 else 0

        for col in range(5):
            x = col * brick_w + offset
            for t in range(mortar_t):
                xp = (x + t) % width
                if y_start < y_end:
                    img[y_start:y_end, xp] = mortar

    noise = np.random.default_rng(0).integers(-15, 15, (height, width), dtype=np.int16)
    for c in range(3):
        channel = img[:, :, c].astype(np.int16) + noise
        img[:, :, c] = np.clip(channel, 0, 255).astype(np.uint8)

    return img


def generate_concrete(width: int = 256, height: int = 256) -> np.ndarray:
    img = np.zeros((height, width, 4), dtype=np.uint8)

    rng = np.random.default_rng(1)
    noise = rng.integers(-20, 20, (height, width), dtype=np.int16)

    img[:, :, 0] = np.clip(145 + noise, 0, 255).astype(np.uint8)
    img[:, :, 1] = np.clip(155 + noise, 0, 255).astype(np.uint8)
    img[:, :, 2] = np.clip(135 + noise, 0, 255).astype(np.uint8)
    img[:, :, 3] = 255
    return img


def generate_roof_tiles(width: int = 256, height: int = 256) -> np.ndarray:
    img = np.zeros((height, width, 4), dtype=np.uint8)

    img[:, :, 0] = 75
    img[:, :, 1] = 85
    img[:, :, 2] = 100
    img[:, :, 3] = 255

    tile_h = max(height // 6, 1)

    for row in range(7):
        y = row * tile_h
        line_t = max(1, tile_h // 8)
        for t in range(line_t):
            if y + t < height:
                img[y + t, :, 0] = 55
                img[y + t, :, 1] = 60
                img[y + t, :, 2] = 75

        for dy in range(tile_h):
            if y + dy < height:
                factor = 1.0 - 0.15 * (dy / tile_h)
                for c in range(3):
                    img[y + dy, :, c] = np.clip(
                        img[y + dy, :, c].astype(np.float32) * factor,
                        0, 255,
                    ).astype(np.uint8)

    rng = np.random.default_rng(2)
    noise = rng.integers(-8, 8, (height, width), dtype=np.int16)
    for c in range(3):
        channel = img[:, :, c].astype(np.int16) + noise
        img[:, :, c] = np.clip(channel, 0, 255).astype(np.uint8)

    return img


def generate_wall_concrete(width: int = 256, height: int = 256) -> np.ndarray:
    img = np.zeros((height, width, 4), dtype=np.uint8)

    rng = np.random.default_rng(3)
    noise = rng.integers(-12, 12, (height, width), dtype=np.int16)

    img[:, :, 0] = np.clip(175 + noise, 0, 255).astype(np.uint8)
    img[:, :, 1] = np.clip(170 + noise, 0, 255).astype(np.uint8)
    img[:, :, 2] = np.clip(165 + noise, 0, 255).astype(np.uint8)
    img[:, :, 3] = 255

    panel_h = height // 4
    seam_t = max(1, height // 128)
    for row in range(5):
        y = row * panel_h
        for t in range(seam_t):
            if y + t < height:
                img[y + t, :, 0] = 140
                img[y + t, :, 1] = 135
                img[y + t, :, 2] = 130

    return img


def generate_wall_glass(width: int = 256, height: int = 256) -> np.ndarray:
    img = np.zeros((height, width, 4), dtype=np.uint8)

    img[:, :, 0] = 100
    img[:, :, 1] = 130
    img[:, :, 2] = 160
    img[:, :, 3] = 255

    panel_h = height // 6
    panel_w = width // 4
    frame_t = max(2, height // 64)

    for row in range(7):
        y = row * panel_h
        for t in range(frame_t):
            if y + t < height:
                img[y + t, :, 0] = 60
                img[y + t, :, 1] = 65
                img[y + t, :, 2] = 75

    for col in range(5):
        x = col * panel_w
        for t in range(frame_t):
            if x + t < width:
                img[:, x + t, 0] = 60
                img[:, x + t, 1] = 65
                img[:, x + t, 2] = 75

    rng = np.random.default_rng(4)
    noise = rng.integers(-8, 8, (height, width), dtype=np.int16)
    for c in range(3):
        channel = img[:, :, c].astype(np.int16) + noise
        img[:, :, c] = np.clip(channel, 0, 255).astype(np.uint8)

    return img
