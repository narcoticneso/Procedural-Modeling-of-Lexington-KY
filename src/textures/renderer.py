from __future__ import annotations

from pathlib import Path
from typing import Dict

import numpy as np
from vispy import app, gloo
from vispy.util.transforms import perspective


SHADER_DIR = Path(__file__).resolve().parents[2] / "shaders"


def _look_at(eye: np.ndarray, target: np.ndarray, up: np.ndarray) -> np.ndarray:
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


class CityRenderer(app.Canvas):

    def __init__(
        self,
        buffers: Dict[str, np.ndarray],
        textures: Dict[str, np.ndarray],
    ) -> None:
        super().__init__(
            title="Lexington, KY - Procedural City",
            size=(1400, 900),
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

        self.distance = 4000.0
        self.azimuth = 45.0
        self.elevation = 30.0
        self.target = np.array([0.0, 0.0, 0.0], dtype=np.float64)

        self.program["u_light_dir"] = np.array([0.5, 0.3, 1.0], dtype=np.float32)
        self.program["u_light_color"] = np.array([1.0, 0.95, 0.9], dtype=np.float32)
        self.program["u_ambient"] = np.array([0.25, 0.25, 0.3], dtype=np.float32)
        self.program["u_model"] = np.eye(4, dtype=np.float32)

        self._update_camera()

        gloo.set_state(depth_test=True, cull_face=False)
        gloo.set_clear_color((0.53, 0.81, 0.92, 1.0))

        self.show()

    def _update_camera(self) -> None:
        az = np.radians(self.azimuth)
        el = np.radians(self.elevation)

        eye = self.target + self.distance * np.array([
            np.cos(el) * np.sin(az),
            np.cos(el) * np.cos(az),
            np.sin(el),
        ])

        self.program["u_camera_pos"] = eye.astype(np.float32)
        self.program["u_view"] = _look_at(
            eye.astype(np.float32),
            self.target.astype(np.float32),
            np.array([0, 0, 1], dtype=np.float32),
        )

        aspect = self.size[0] / max(self.size[1], 1)
        self.program["u_projection"] = perspective(
            60.0, aspect, 1.0, 100000.0,
        )

    def on_draw(self, event) -> None:
        gloo.clear(color=True, depth=True)
        if self.n_vertices > 0:
            self.program.draw("triangles")

    def on_resize(self, event) -> None:
        gloo.set_viewport(0, 0, *event.physical_size)
        self._update_camera()

    def on_mouse_wheel(self, event) -> None:
        self.distance *= 0.9 if event.delta[1] > 0 else 1.1
        self.distance = max(100.0, min(50000.0, self.distance))
        self._update_camera()
        self.update()

    def on_mouse_move(self, event) -> None:
        if not event.is_dragging:
            return

        dx = event.pos[0] - event.last_event.pos[0]
        dy = event.pos[1] - event.last_event.pos[1]

        if 1 in event.buttons:
            self.azimuth += dx * 0.5
            self.elevation = np.clip(self.elevation + dy * 0.5, -89.0, 89.0)
        elif 2 in event.buttons:
            scale = self.distance * 0.001
            az = np.radians(self.azimuth)
            self.target[0] -= (dx * np.cos(az) + dy * np.sin(az)) * scale
            self.target[1] += (dx * np.sin(az) - dy * np.cos(az)) * scale

        self._update_camera()
        self.update()

    def on_key_press(self, event) -> None:
        if event.key == "R":
            self.distance = 4000.0
            self.azimuth = 45.0
            self.elevation = 30.0
            self.target = np.array([0.0, 0.0, 0.0], dtype=np.float64)
        elif event.key == "T":
            self.elevation = 89.0
            self.azimuth = 0.0
        elif event.key == "I":
            self.elevation = 35.0
            self.azimuth = 45.0
        else:
            return

        self._update_camera()
        self.update()
