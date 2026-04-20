import json
import numpy as np
import osmnx as ox
import networkx as nx
import pyvista as pv
import json
from pathlib import Path

import shapely as shapely
import shapely.geometry as geom
import matplotlib.pyplot as pyplt
from shapely import LineString, polygonize
import geopandas as gpd

#Load GraphML file, returns MultiDiGraph of city
#A MultiDiGraph is from Network X. It is a directed graph
#Class that can store multiedges
#Objects: nodes, edges, and adj
#Documentation here:
#https://networkx.org/documentation/stable/reference/classes/multidigraph.html

city_graph = ox.io.load_graphml(filepath="C:\\Users\\natha\\code\\cs335\\Procedural-Modeling-of-Lexington-KY\\data\\raw\\lexington_graph.graphml")


#Documentation:
#https://geopandas.org/en/stable/docs/reference/api/geopandas.GeoDataFrame.html

roads = ox.graph_to_gdfs(city_graph, nodes = False, edges = True, fill_edge_geometry= True)

merged_roads = shapely.unary_union(roads["geometry"])
merged_roads = list(merged_roads.geoms)

#Polygonize Documentation: https://shapely.readthedocs.io/en/2.1.1/reference/shapely.polygonize.html
polygonized_roads = polygonize(merged_roads)

geoseries_roads = gpd.GeoSeries(polygonized_roads.geoms)

area_list = []
convexity_list = [ ]
rectangularity_list = []
indices_to_drop = []
index = 0
for geom in geoseries_roads:
    #convex_hull_list.append(geom.convex_hull)
    area = abs(geom.area)
    area_list.append(area)
    #For more on mabr see https://gis.stackexchange.com/questions/278428/quantifying-shape-of-polygon-using-arcgis-desktop?
    mabr = shapely.minimum_rotated_rectangle(geom).area
    convexity = (geom.convex_hull).area
    convexity_ratio = area/convexity
    rectangularity = area/mabr
    rectangularity_list.append(rectangularity)
    convexity_list.append(convexity_ratio)
    #Drop very large areas
    if area > (2.297e-4):
        indices_to_drop.append(index)
    #Drop very small areas
    if area < (3e-7):
        indices_to_drop.append(index)
    #Drop concave allotments
    #if convexity_ratio < .75:
        #indices_to_drop.append(index)
    if rectangularity < .5:
        indices_to_drop.append(index)
    index = index + 1

geoseries_roads = geoseries_roads.drop(indices_to_drop)

geoseries_roads_plot = geoseries_roads.plot()
pyplt.show()
print("Done")

# Export the resulting lots to a JSON file
def export_lots(geoseries):
    lots = []

    for i, poly in enumerate(geoseries, start=1):
        if poly.is_empty or poly.geom_type != "Polygon":
            continue

        coords = list(poly.exterior.coords)

        # remove duplicate closing point
        if coords[0] == coords[-1]:
            coords = coords[:-1]

        centroid = poly.centroid

        lots.append({
            "lot_id": f"lot_{i:05d}",
            "polygon": [[float(x), float(y)] for x, y in coords],
            "centroid": [float(centroid.x), float(centroid.y)],
            "area": float(abs(poly.area)),
            "road_access": True,
            "district": None
        })
    return lots


lots = export_lots(geoseries_roads)

output_path = Path(__file__).resolve().parents[2] / "data" / "processed" / "lots.json"
output_path.parent.mkdir(parents=True, exist_ok=True)

with open(output_path, "w") as f:
    json.dump(lots, f, indent=2)

print(f"Exported {len(lots)} lots to {output_path}")