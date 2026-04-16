import numpy as np
import osmnx as ox
import networkx as nx
import pyvista as pv
from pathlib import Path

import shapely.geometry as geom
import geopandas as gpd

print("OSMnx version:", ox.__version__)

# Ensure OSMnx cache writes to a writable folder, even if launched from '/'.
cache_dir = Path(__file__).resolve().parent / "cache"
cache_dir.mkdir(parents=True, exist_ok=True)
ox.settings.use_cache = True
ox.settings.cache_folder = str(cache_dir)


def export_graph_to_txt(graph, output_path):
    with open(output_path, "w", encoding="utf-8") as output_file:
        output_file.write("NODE LOCATIONS\n")
        for node_id, data in graph.nodes(data=True):
            x_coord = data.get("x")
            y_coord = data.get("y")
            output_file.write(f"{node_id}: ({x_coord}, {y_coord})\n")

        output_file.write("\nNODE CONNECTIONS\n")
        for source, target in graph.edges():
            output_file.write(f"{source} -> {target}\n")

# Download street network for a specific place
G = ox.graph_from_place("Lexington, Kentucky", network_type="drive")

# print nodes and edges
print(f"Nodes: {len(G.nodes)}")
print(f"Edges: {len(G.edges)}")

txt_export_path = Path(__file__).resolve().parent / "lexington_graph_export.txt"
export_graph_to_txt(G, txt_export_path)
print(f"Text export written to: {txt_export_path}")

graphml_export_path = Path(__file__).resolve().parent / "lexington_graph.graphml"
ox.save_graphml(G, graphml_export_path)
print(f"GraphML export written to: {graphml_export_path}")

fig, ax = ox.plot_graph(G) 
