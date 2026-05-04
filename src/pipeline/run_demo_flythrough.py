import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import numpy as np
from vispy import app, gloo
from vispy.util.transforms import perspective

from geometry.mesh_builder import load_buildings_json, build_all_meshes, XY_SCALE
from textures.texture_engine import TextureEngine
from textures.procedural import (
    generate_brick, generate_concrete, generate_roof_tiles,
    generate_wall_concrete, generate_wall_glass,
)

SHADER_DIR = Path(__file__).resolve().parents[2] / "shaders"


def _look_at(eye, target, up):
    f = target - eye
    f = f / np.linalg.norm(f)
    s = np.cross(f, up)
    s = s / np.linalg.norm(s)
    u = np.cross(s, f)

    M = np.eye(4, dtype=np.float32)
    M[0, 0] = s[0];  M[0, 1] = u[0];  M[0, 2] = -f[0]
    M[1, 0] = s[1];  M[1, 1] = u[1];  M[1, 2] = -f[1]
    M[2, 0] = s[2];  M[2, 1] = u[2];  M[2, 2] = -f[2]
    M[3, 0] = -np.dot(s, eye)
    M[3, 1] = -np.dot(u, eye)
    M[3, 2] = np.dot(f, eye)
    return M


def _compute_bounds(positions):
    if len(positions) == 0:
        return -1000.0, 1000.0, -1000.0, 1000.0
    return (
        float(positions[:, 0].min()),
        float(positions[:, 0].max()),
        float(positions[:, 1].min()),
        float(positions[:, 1].max()),
    )


KEYFRAMES = [
    # (time_sec, distance, azimuth, elevation, target_x, target_y, target_z)

    # 1. Opening: medium overview, slow orbit
    (0.0,   3000.0,   0.0,  40.0,   0.0,   0.0,  0.0),
    (6.0,   2800.0,  60.0,  35.0,   0.0,   0.0,  0.0),

    # 2. Orbit closer, dropping elevation
    (12.0,  2000.0, 150.0,  28.0,   0.0,   0.0,  0.0),

    # 3. Swoop toward city center (downtown towers)
    (18.0,  1200.0, 210.0,  18.0,   0.0,   0.0,  0.0),

    # 4. Low street-level pass
    (24.0,   600.0, 270.0,   8.0,   0.0,   0.0,  0.0),

    # 5. Pull back up and orbit
    (30.0,  1500.0, 330.0,  22.0,   0.0,   0.0,  0.0),

    # 6. Final wide shot
    (36.0,  3000.0, 405.0,  38.0,   0.0,   0.0,  0.0),

    # 7. Hold ending
    (42.0,  3000.0, 430.0,  38.0,   0.0,   0.0,  0.0),
]


def _lerp(a, b, t):
    return a + (b - a) * t


def _smooth(t):
    return t * t * (3.0 - 2.0 * t)


def _interpolate_keyframes(elapsed):
    if elapsed <= KEYFRAMES[0][0]:
        kf = KEYFRAMES[0]
        return kf[1], kf[2], kf[3], np.array([kf[4], kf[5], kf[6]])
    if elapsed >= KEYFRAMES[-1][0]:
        kf = KEYFRAMES[-1]
        return kf[1], kf[2], kf[3], np.array([kf[4], kf[5], kf[6]])

    for i in range(len(KEYFRAMES) - 1):
        t0 = KEYFRAMES[i][0]
        t1 = KEYFRAMES[i + 1][0]
        if t0 <= elapsed < t1:
            raw_t = (elapsed - t0) / (t1 - t0)
            t = _smooth(raw_t)
            a = KEYFRAMES[i]
            b = KEYFRAMES[i + 1]
            return (
                _lerp(a[1], b[1], t),
                _lerp(a[2], b[2], t),
                _lerp(a[3], b[3], t),
                np.array([
                    _lerp(a[4], b[4], t),
                    _lerp(a[5], b[5], t),
                    _lerp(a[6], b[6], t),
                ]),
            )

    kf = KEYFRAMES[-1]
    return kf[1], kf[2], kf[3], np.array([kf[4], kf[5], kf[6]])


class FlyThroughRenderer(app.Canvas):

    def __init__(self, buffers, textures):
        super().__init__(
            title="Lexington, KY - Demo Flythrough",
            size=(1920, 1080),
            keys="interactive",
        )

        vert_src = (SHADER_DIR / "vertex.glsl").read_text()
        frag_src = (SHADER_DIR / "fragment.glsl").read_text()

        self.program = gloo.Program(vert_src, frag_src)

        self.program["a_position"] = gloo.VertexBuffer(buffers["positions"])
        self.program["a_normal"] = gloo.VertexBuffer(buffers["normals"])
        self.program["a_texcoord"] = gloo.VertexBuffer(buffers["uvs"])
        self.program["a_face_label"] = gloo.VertexBuffer(
            buffers["label_ids"].reshape(-1, 1)
        )

        for name, tex_data in textures.items():
            tex = gloo.Texture2D(tex_data, interpolation="linear", wrapping="repeat")
            self.program[f"u_tex_{name}"] = tex

        self.n_vertices = len(buffers["positions"])

        self.program["u_light_dir"] = np.array([0.5, 0.3, 1.0], dtype=np.float32)
        self.program["u_light_color"] = np.array([1.0, 0.95, 0.9], dtype=np.float32)
        self.program["u_ambient"] = np.array([0.25, 0.25, 0.3], dtype=np.float32)
        self.program["u_model"] = np.eye(4, dtype=np.float32)

        self._elapsed = 0.0
        self._paused = False
        self._timer = app.Timer(1 / 60, connect=self._on_tick, start=True)

        self._set_camera(6000.0, 0.0, 50.0, np.array([0.0, 0.0, 0.0]))

        gloo.set_state(depth_test=True, cull_face=False)
        gloo.set_clear_color((0.53, 0.81, 0.92, 1.0))

        self.show()

    def _set_camera(self, distance, azimuth, elevation, target):
        az = np.radians(azimuth)
        el = np.radians(elevation)

        eye = target + distance * np.array([
            np.cos(el) * np.sin(az),
            np.cos(el) * np.cos(az),
            np.sin(el),
        ])

        self.program["u_camera_pos"] = eye.astype(np.float32)
        self.program["u_view"] = _look_at(
            eye.astype(np.float32),
            target.astype(np.float32),
            np.array([0, 0, 1], dtype=np.float32),
        )

        aspect = self.size[0] / max(self.size[1], 1)
        self.program["u_projection"] = perspective(60.0, aspect, 1.0, 100000.0)

    def _on_tick(self, event):
        if self._paused:
            return
        self._elapsed += 1.0 / 60.0
        distance, azimuth, elevation, target = _interpolate_keyframes(self._elapsed)
        self._set_camera(distance, azimuth, elevation, target)
        self.update()

    def on_draw(self, event):
        gloo.clear(color=True, depth=True)
        if self.n_vertices > 0:
            self.program.draw("triangles")

    def on_resize(self, event):
        gloo.set_viewport(0, 0, *event.physical_size)

    def on_key_press(self, event):
        if event.key == "Space":
            self._paused = not self._paused
            print("Paused" if self._paused else "Resumed")
        elif event.key == "R":
            self._elapsed = 0.0
            self._paused = False
            print("Restarted flythrough")
        elif event.key == "Escape":
            self.close()


def main():
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
        "wall_concrete": generate_wall_concrete(),
        "wall_glass": generate_wall_glass(),
    }

    print(f"Processed {len(mesh_pairs)} buildings")
    print(f"Total vertices: {len(buffers['positions'])}")
    print()
    print("Flythrough controls:")
    print("  Space  -> pause / resume")
    print("  R      -> restart from beginning")
    print("  Escape -> quit")
    print()
    print("Starting flythrough (~42 seconds)...")

    renderer = FlyThroughRenderer(buffers, textures)
    app.run()


if __name__ == "__main__":
    main()
