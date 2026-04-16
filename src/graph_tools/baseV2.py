from pathlib import Path
import json
import re

import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import networkx as nx


NODE_LINE_PATTERN = re.compile(
	r"^(?P<node_id>\d+): \((?P<x>-?\d+(?:\.\d+)?), (?P<y>-?\d+(?:\.\d+)?)\)$"
)
EDGE_LINE_PATTERN = re.compile(r"^(?P<source>\d+) -> (?P<target>\d+)$")
EDGE_WITH_METADATA_PATTERN = re.compile(
	r"^(?P<source>\d+) -> (?P<target>\d+)(?: \| (?P<metadata>\{.*\}))?$"
)

HIGHWAY_COLOR = "#d95f02"
RESIDENTIAL_COLOR = "#1b9e77"
OTHER_ROAD_COLOR = "#4a6c6f"
MAJOR_HIGHWAY_TYPES = {
	"motorway",
	"motorway_link",
	"trunk",
	"trunk_link",
	"primary",
	"primary_link",
	"secondary",
	"secondary_link",
}


def load_graph_from_export(export_path: Path) -> nx.MultiDiGraph:
	graph = nx.MultiDiGraph()
	section = None

	with export_path.open("r", encoding="utf-8") as export_file:
		for raw_line in export_file:
			line = raw_line.strip()
			if not line:
				continue

			if line == "NODE LOCATIONS":
				section = "nodes"
				continue
			if line == "NODE CONNECTIONS":
				section = "edges"
				continue

			if section == "nodes":
				match = NODE_LINE_PATTERN.match(line)
				if not match:
					raise ValueError(f"Invalid node line: {line}")

				node_id = int(match.group("node_id"))
				x_coord = float(match.group("x"))
				y_coord = float(match.group("y"))
				graph.add_node(node_id, pos=(x_coord, y_coord))
				continue

			if section == "edges":
				match = EDGE_WITH_METADATA_PATTERN.match(line)
				if not match:
					raise ValueError(f"Invalid edge line: {line}")

				source = int(match.group("source"))
				target = int(match.group("target"))
				metadata_text = match.group("metadata")
				edge_attributes = {}
				edge_key = None
				if metadata_text:
					edge_attributes = json.loads(metadata_text)
					edge_key = edge_attributes.pop("key", None)

				if edge_key is None:
					graph.add_edge(source, target, **edge_attributes)
				else:
					graph.add_edge(source, target, key=edge_key, **edge_attributes)

	if graph.number_of_nodes() == 0:
		raise ValueError(f"No nodes found in {export_path}")

	return graph


def edge_color_for_road_type(highway_value: object) -> str:
	if isinstance(highway_value, list):
		highway_types = {str(item).lower() for item in highway_value}
	elif highway_value is None:
		highway_types = set()
	else:
		highway_types = {str(highway_value).lower()}

	if highway_types & MAJOR_HIGHWAY_TYPES:
		return HIGHWAY_COLOR
	if "residential" in highway_types:
		return RESIDENTIAL_COLOR
	return OTHER_ROAD_COLOR


def plot_graph(graph: nx.DiGraph, title: str, output_path: Path | None = None) -> None:
	positions = nx.get_node_attributes(graph, "pos")
	if len(positions) != graph.number_of_nodes():
		raise ValueError("Every node must include a position before plotting")
	edgelist = list(graph.edges(keys=True, data=True))
	edge_colors = [edge_color_for_road_type(data.get("highway")) for _, _, _, data in edgelist]

	fig, axis = plt.subplots(figsize=(12, 10))
	nx.draw_networkx_edges(
		graph,
		pos=positions,
		ax=axis,
		edgelist=[(source, target, key) for source, target, key, _ in edgelist],
		edge_color=edge_colors,
		width=0.6,
		alpha=0.7,
		arrows=False,
	)
	nx.draw_networkx_nodes(
		graph,
		pos=positions,
		ax=axis,
		node_size=8,
		node_color="#c46b48",
		linewidths=0,
	)

	axis.set_title(title)
	axis.set_xlabel("Longitude")
	axis.set_ylabel("Latitude")
	axis.set_aspect("equal", adjustable="box")
	axis.margins(0.02)
	axis.legend(
		handles=[
			Patch(facecolor=HIGHWAY_COLOR, edgecolor=HIGHWAY_COLOR, label="Highway"),
			Patch(facecolor=RESIDENTIAL_COLOR, edgecolor=RESIDENTIAL_COLOR, label="Residential"),
			Patch(facecolor=OTHER_ROAD_COLOR, edgecolor=OTHER_ROAD_COLOR, label="Other Road"),
		],
		loc="upper right",
	)
	plt.tight_layout()

	backend = plt.get_backend().lower()
	if "agg" in backend and output_path is not None:
		fig.savefig(output_path, dpi=300, bbox_inches="tight")
		print(f"Saved plot to: {output_path}")
	else:
		plt.show()


def main() -> None:
	export_path = Path(__file__).resolve().parents[2] / "data" / "raw" / "lexington_graph_export_final.txt"
	output_path = Path(__file__).resolve().parents[2] / "data" / "raw" / "lexington_graph_plot.png"
	graph = load_graph_from_export(export_path)

	print(f"Loaded {graph.number_of_nodes()} nodes and {graph.number_of_edges()} edges")
	plot_graph(graph, "Road Network", output_path=output_path)


if __name__ == "__main__":
	main()
