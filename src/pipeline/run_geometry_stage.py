import sys
import json
from pathlib import Path

import pyvista as pv
import osmnx as ox
import matplotlib.pyplot as plt

# Add src/ to the Python path so imports work
sys.path.append(str(Path(__file__).resolve().parents[1]))

from geometry.mesh_builder import (
    load_buildings_json,
    build_all_meshes,
    merge_meshes,
    save_mesh,
    XY_SCALE,
)


# Returns a display color based on building type
def get_building_color(building_type: str) -> str:
    color_map = {
        "house": "lightblue",
        "duplex": "cornflowerblue",
        "apartment": "mediumpurple",
        "storefront": "orange",
        "office": "gold",
        "mixed_use": "salmon",
        "warehouse": "darkgray",
        "factory": "slategray",
        "generic_building": "tan",
    }
    return color_map.get(building_type, "tan")


# Loads road geometry from Lucy's graphml file
def load_road_geometries(graphml_path: Path):
    graph = ox.load_graphml(graphml_path)
    roads_gdf = ox.graph_to_gdfs(graph, nodes=False, edges=True, fill_edge_geometry=True)
    return roads_gdf


# Computes scene bounds from lots
def get_lot_bounds(lots, origin_x: float, origin_y: float):
    xs = []
    ys = []

    for lot in lots:
        for x, y in lot["polygon"]:
            xs.append((float(x) - origin_x) * XY_SCALE)
            ys.append((float(y) - origin_y) * XY_SCALE)

    if not xs or not ys:
        return -1000, 1000, -1000, 1000

    return min(xs), max(xs), min(ys), max(ys)


# Creates a single PNG that contains all roads and lot outlines
def generate_ground_texture(
    roads_gdf,
    lots,
    origin_x: float,
    origin_y: float,
    output_path: Path
):
    min_x, max_x, min_y, max_y = get_lot_bounds(lots, origin_x, origin_y)

    fig, ax = plt.subplots(figsize=(12, 12), dpi=300)
    ax.set_facecolor("white")

    # draw roads
    for _, row in roads_gdf.iterrows():
        geometry = row.geometry

        try:
            if geometry.geom_type == "LineString":
                coords = list(geometry.coords)
                xs = [(float(x) - origin_x) * XY_SCALE for x, _ in coords]
                ys = [(float(y) - origin_y) * XY_SCALE for _, y in coords]
                ax.plot(xs, ys, color="dimgray", linewidth=0.35, alpha=0.9)

            elif geometry.geom_type == "MultiLineString":
                for line in geometry.geoms:
                    coords = list(line.coords)
                    xs = [(float(x) - origin_x) * XY_SCALE for x, _ in coords]
                    ys = [(float(y) - origin_y) * XY_SCALE for _, y in coords]
                    ax.plot(xs, ys, color="dimgray", linewidth=0.35, alpha=0.9)
        except Exception:
            pass

    # draw lot outlines
    for lot in lots:
        try:
            poly = lot["polygon"]
            xs = [(float(x) - origin_x) * XY_SCALE for x, _ in poly]
            ys = [(float(y) - origin_y) * XY_SCALE for _, y in poly]

            if xs and ys:
                xs.append(xs[0])
                ys.append(ys[0])
                ax.plot(xs, ys, color="lightgray", linewidth=0.25, alpha=0.7)
        except Exception:
            pass

    ax.set_xlim(min_x, max_x)
    ax.set_ylim(min_y, max_y)
    ax.set_aspect("equal", adjustable="box")
    ax.axis("off")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout(pad=0)
    plt.savefig(output_path, bbox_inches="tight", pad_inches=0)
    plt.close(fig)

    return min_x, max_x, min_y, max_y


# Builds a textured ground plane matching the city bounds
def build_textured_ground(texture_path: Path, min_x, max_x, min_y, max_y):
    center = ((min_x + max_x) / 2.0, (min_y + max_y) / 2.0, -0.02)
    i_size = max_x - min_x
    j_size = max_y - min_y

    ground = pv.Plane(
        center=center,
        direction=(0, 0, 1),
        i_size=i_size,
        j_size=j_size,
        i_resolution=1,
        j_resolution=1,
    )

    texture = pv.read_texture(str(texture_path))
    return ground, texture


# Runs the geometry stage of the pipeline
def main() -> None:
    project_root = Path(__file__).resolve().parents[2]

    buildings_path = project_root / "data" / "processed" / "buildings.json"
    lots_path = project_root / "data" / "processed" / "lots.json"
    graphml_path = project_root / "data" / "raw" / "lexington_graph.graphml"
    output_mesh_path = project_root / "data" / "processed" / "buildings_mesh.vtp"
    screenshot_path = project_root / "data" / "processed" / "city_view.png"
    texture_path = project_root / "data" / "processed" / "ground_texture.png"

    buildings = load_buildings_json(buildings_path)

    with open(lots_path, "r", encoding="utf-8") as f:
        lots = json.load(f)

    # Build all buildings
    building_mesh_pairs, (origin_x, origin_y) = build_all_meshes(buildings, limit=None)
    building_meshes_only = [mesh for mesh, _ in building_mesh_pairs]
    merged_buildings = merge_meshes(building_meshes_only)

    save_mesh(merged_buildings, output_mesh_path)

    print(f"Loaded {len(buildings)} buildings")
    print(f"Built {len(building_mesh_pairs)} building meshes")
    print(f"Using origin: ({origin_x}, {origin_y})")
    print(f"Saved mesh to {output_mesh_path}")

    print("Loading road geometry...")
    roads_gdf = load_road_geometries(graphml_path)

    print("Generating ground texture...")
    min_x, max_x, min_y, max_y = generate_ground_texture(
        roads_gdf=roads_gdf,
        lots=lots,
        origin_x=origin_x,
        origin_y=origin_y,
        output_path=texture_path,
    )
    print(f"Saved ground texture to {texture_path}")

    ground, ground_texture = build_textured_ground(
        texture_path=texture_path,
        min_x=min_x,
        max_x=max_x,
        min_y=min_y,
        max_y=max_y,
    )

    plotter = pv.Plotter(window_size=[1400, 900])

    # Better navigation style for ground-based viewing
    try:
        plotter.enable_terrain_style()
    except Exception:
        pass

    # Add textured ground plane
    plotter.add_mesh(ground, texture=ground_texture, opacity=1.0)

    # Draw buildings one-by-one so they can be colored by type
    for mesh, building in building_mesh_pairs:
        color = get_building_color(building["building_type"])
        plotter.add_mesh(mesh, color=color, smooth_shading=False, show_edges=False)

    plotter.add_axes()
    plotter.show_grid()

    # Camera helpers
    def reset_camera():
        plotter.camera_position = [
            (3500, 3500, 2200),
            (0, 0, 0),
            (0, 0, 1),
        ]
        plotter.reset_camera()

    def top_view():
        plotter.view_xy()
        plotter.camera.up = (0, 1, 0)
        plotter.reset_camera()

    def iso_view():
        plotter.view_isometric()
        plotter.camera.up = (0, 0, 1)
        plotter.reset_camera()

    plotter.add_key_event("r", reset_camera)
    plotter.add_key_event("t", top_view)
    plotter.add_key_event("i", iso_view)

    reset_camera()

    plotter.show(screenshot=str(screenshot_path))
    print(f"Saved screenshot to {screenshot_path}")


if __name__ == "__main__":
    main()