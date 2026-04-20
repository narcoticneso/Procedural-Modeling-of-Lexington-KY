import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BUILDINGS_SRC = PROJECT_ROOT / "src" / "buildings"
if str(BUILDINGS_SRC) not in sys.path:
    sys.path.insert(0, str(BUILDINGS_SRC))

from building_generator import BuildingGenerator, lots_from_dicts, buildings_to_dicts  # noqa: E402


def main() -> None:
    lots_path = PROJECT_ROOT / "data" / "processed" / "lots.json"
    buildings_path = PROJECT_ROOT / "data" / "processed" / "buildings.json"

    with open(lots_path, "r", encoding="utf-8") as f:
        raw_lots = json.load(f)

    lots = lots_from_dicts(raw_lots)

    generator = BuildingGenerator(seed=42)
    buildings = generator.generate_buildings(lots)

    with open(buildings_path, "w", encoding="utf-8") as f:
        json.dump(buildings_to_dicts(buildings), f, indent=2)

    print(f"Loaded {len(lots)} lots")
    print(f"Generated {len(buildings)} buildings")
    print(f"Saved to {buildings_path}")


if __name__ == "__main__":
    main()
