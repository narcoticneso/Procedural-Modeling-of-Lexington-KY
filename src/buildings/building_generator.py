import json
import math
import random
from pathlib import Path
from typing import Iterable, List, Dict, Any

from building_types import Lot, Building, BUILDING_TYPE_RULES

# Approximate center of downtown Lexington (Main St / Vine St area)
DOWNTOWN_CENTER = (-84.4956, 38.0406)

# Distance thresholds in approximate kilometers
DOWNTOWN_RADIUS_KM = 0.8
COMMERCIAL_RADIUS_KM = 2.5

# Max number of towers allowed in downtown (Lexington has ~4-5 tall buildings)
MAX_DOWNTOWN_TOWERS = 4


def _haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# Assigns a district based on distance from downtown Lexington
def assign_district(centroid) -> str:
    dist = _haversine_km(centroid[0], centroid[1],
                         DOWNTOWN_CENTER[0], DOWNTOWN_CENTER[1])
    if dist < DOWNTOWN_RADIUS_KM:
        return "downtown"
    if dist < COMMERCIAL_RADIUS_KM:
        return "commercial"
    return "residential"


class BuildingGenerator:

    # Initialize  generator with a random seed and a building counter
    def __init__(self, seed: int = 42) -> None:
        self.rng = random.Random(seed)
        self._building_counter = 1

    # Take a list of lots and generate a building for each
    def generate_buildings(self, lots: Iterable[Lot]) -> List[Building]:
        buildings: List[Building] = []

        for lot in lots:
            building = self.generate_building_for_lot(lot)
            if building is not None:
                buildings.append(building)

        self._enforce_downtown_limits(buildings)
        return buildings

    # Cap the number of towers in downtown to match Lexington's skyline
    def _enforce_downtown_limits(self, buildings: List[Building]) -> None:
        downtown_towers = [
            b for b in buildings
            if b.building_type == "tower"
            and (b.district == "downtown"
                 or assign_district(b.footprint[0]) == "downtown")
        ]

        if len(downtown_towers) <= MAX_DOWNTOWN_TOWERS:
            return

        # Keep the tallest towers, demote the rest to office buildings
        downtown_towers.sort(key=lambda b: b.height, reverse=True)
        for b in downtown_towers[MAX_DOWNTOWN_TOWERS:]:
            b.building_type = "office"
            b.floors = self.rng.randint(3, 8)
            b.height = round(b.floors * self._height_per_floor("office"), 2)
            b.geometry_tags["extrude_height"] = b.height
            b.geometry_tags["floors"] = b.floors

    # Generate single building based on one lot's data
    def generate_building_for_lot(self, lot: Lot) -> Building | None:
        # Skip lots that cannot be accessed from a road
        if not lot.road_access:
            return None

        # Use district-based rules, assign from geo-position if not already set
        district = lot.district or assign_district(lot.centroid)
        rules = BUILDING_TYPE_RULES.get(district, BUILDING_TYPE_RULES["default"])

        # Randomly choose building characteristics from rules
        building_type = self.rng.choice(rules["types"])
        style = self.rng.choice(rules["styles"])
        roof_type = self.rng.choice(rules["roofs"])
        age = self.rng.choice(rules["ages"])

        # Determine building size
        floors = self._choose_floors(building_type)
        height = round(floors * self._height_per_floor(building_type), 2)

        # Create and return a Building object
        building = Building(
            building_id=self._next_building_id(),
            lot_id=lot.lot_id,
            building_type=building_type,
            style=style,
            age=age,
            floors=floors,
            height=height,
            roof_type=roof_type,
            footprint=self._create_placeholder_footprint(lot, building_type),
            district=district,
            geometry_tags={
                "extrude_height": height,
                "floors": floors,
                "roof_type": roof_type,
                "source_stage": "building_generation",
            },
            texture_tags=[district, building_type, style, age],
            metadata={
                "input_area": lot.area,
                "road_access": lot.road_access,
            },
        )

        return building

    # Chooses a random number of floors based on building type
    def _choose_floors(self, building_type: str) -> int:
        floor_ranges = {
            "house": (1, 3),
            "duplex": (2, 3),
            "apartment": (3, 6),
            "storefront": (1, 2),
            "office": (3, 8),
            "tower": (10, 30),
            "mixed_use": (2, 5),
            "warehouse": (1, 2),
            "factory": (1, 3),
            "generic_building": (1, 4),
        }
        low, high = floor_ranges.get(building_type, (1, 3))
        return self.rng.randint(low, high)

    # Returns height per floor depending on building type
    def _height_per_floor(self, building_type: str) -> float:
        return {
            "house": 3.0,
            "duplex": 3.0,
            "apartment": 3.1,
            "storefront": 4.0,
            "office": 3.8,
            "tower": 3.8,
            "mixed_use": 3.5,
            "warehouse": 5.0,
            "factory": 4.5,
            "generic_building": 3.2,
        }.get(building_type, 3.0)
    
    # Creates building footprint by shrinking the lot polygon inward
    def _create_placeholder_footprint(self, lot, building_type: str = "generic_building"):
        """
        Shrink the lot polygon to create a building footprint.
        """
        polygon = lot.polygon

        cx = sum(p[0] for p in polygon) / len(polygon)
        cy = sum(p[1] for p in polygon) / len(polygon)

        shrink_factor = 0.9 if building_type == "tower" else 0.7  # adjust this (0.5–0.9 works well)

        new_poly = []
        for x, y in polygon:
            dx = x - cx
            dy = y - cy
            new_poly.append([
                cx + dx * shrink_factor,
                cy + dy * shrink_factor
            ])

        return new_poly

    # Generate unique building ID
    def _next_building_id(self) -> str:
        building_id = f"bldg_{self._building_counter:03d}"
        self._building_counter += 1
        return building_id


# Converts raw JSON lot dictionaries into Lot objects
def lots_from_dicts(raw_lots: List[Dict[str, Any]]) -> List[Lot]:
    lots: List[Lot] = []
    for raw in raw_lots:
        lots.append(
            Lot(
                lot_id=raw["lot_id"],
                polygon=[tuple(point) for point in raw["polygon"]],
                centroid=tuple(raw["centroid"]),
                area=raw["area"],
                road_access=raw["road_access"],
                district=raw.get("district"),
                metadata=raw.get("metadata", {}),
            )
        )
    return lots


# Converts Building objects into JSON-serializable dictionaries
def buildings_to_dicts(buildings: List[Building]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for b in buildings:
        result.append(
            {
                "building_id": b.building_id,
                "lot_id": b.lot_id,
                "building_type": b.building_type,
                "style": b.style,
                "age": b.age,
                "floors": b.floors,
                "height": b.height,
                "roof_type": b.roof_type,
                "footprint": [list(point) for point in b.footprint],
                "district": b.district,
                "geometry_tags": b.geometry_tags,
                "texture_tags": b.texture_tags,
                "metadata": b.metadata,
            }
        )
    return result


# Loads lots and converts them into Lot objects
def load_lots_json(path: str | Path) -> List[Lot]:
    with open(path, "r", encoding="utf-8") as f:
        raw_lots = json.load(f)
    return lots_from_dicts(raw_lots)


# Saves generated buildings to a JSON file
def save_buildings_json(buildings: List[Building], path: str | Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(buildings_to_dicts(buildings), f, indent=2)