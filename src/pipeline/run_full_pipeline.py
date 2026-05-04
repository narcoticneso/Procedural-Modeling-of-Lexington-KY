from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PYTHON = sys.executable


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the full city generation pipeline.")
    parser.add_argument(
        "--fetch-gis",
        action="store_true",
        help="Fetch Fayette GIS source data before running the pipeline.",
    )
    parser.add_argument(
        "--pure-lsystem",
        action="store_true",
        help="Use the pure L-system road generator instead of template matching.",
    )
    parser.add_argument(
        "--skip-visualization",
        action="store_true",
        help="Skip the final building visualization step.",
    )
    parser.add_argument(
        "--skip-textures",
        action="store_true",
        help="Skip the texture-engine rendering stage.",
    )
    parser.add_argument(
        "--plot-lots",
        action="store_true",
        help="Show the lot polygon plot during the lots stage.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=7,
        help="Random seed forwarded to the road generator.",
    )
    parser.add_argument(
        "--max-segments",
        type=int,
        default=2600,
        help="Segment budget for the pure L-system mode.",
    )
    return parser.parse_args()


def run_step(name: str, command: list[str]) -> None:
    print(f"\n=== {name} ===")
    print(" ".join(command))
    subprocess.run(command, cwd=PROJECT_ROOT, check=True)


def main() -> None:
    args = parse_args()

    raw_gis_dir = PROJECT_ROOT / "data" / "raw" / "gis"
    population = raw_gis_dir / "fayette_population.geojson"
    hydro = raw_gis_dir / "fayette_hydro.geojson"
    elevation = raw_gis_dir / "fayette_dem.asc"

    if args.fetch_gis:
        run_step(
            "Fetch GIS Data",
            [PYTHON, "src/graph_tools/fetch_fayette_gis.py"],
        )

    if not population.exists() or not hydro.exists() or not elevation.exists():
        raise FileNotFoundError(
            "Missing GIS inputs. Run with --fetch-gis first, or place Fayette GIS files in data/raw/gis/."
        )

    road_command = [
        PYTHON,
        "src/graph_tools/citygen_lsystem.py",
        "--population-data",
        str(population),
        "--population-field",
        "population_density",
        "--hydro-data",
        str(hydro),
        "--elevation-data",
        str(elevation),
        "--seed",
        str(args.seed),
    ]
    if args.pure_lsystem:
        road_command.extend(["--pure-lsystem", "--max-segments", str(args.max_segments)])

    run_step("Generate Roads", road_command)

    lots_command = [PYTHON, "src/lots/divison_lots.py", "--input", "data/raw/cityGen.txt"]
    if args.plot_lots:
        lots_command.append("--plot")
    run_step("Generate Lots", lots_command)

    run_step("Generate Buildings", [PYTHON, "src/pipeline/run_building_stage.py"])

    if not args.skip_textures:
        run_step("Run Texture Engine", [PYTHON, "src/pipeline/run_texture_stage.py"])

if __name__ == "__main__":
    main()
