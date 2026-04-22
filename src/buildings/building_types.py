from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any, Optional

Point = Tuple[float, float]


@dataclass
class Lot:
    """
    Expected input from the lot division stage.
    """
    lot_id: str
    polygon: List[Point]
    centroid: Point
    area: float
    road_access: bool
    district: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Building:
    """
    Output from the building generation stage.
    """
    building_id: str
    lot_id: str
    building_type: str
    style: str
    age: str
    floors: int
    height: float
    roof_type: str
    footprint: List[Point]
    district: Optional[str] = None
    geometry_tags: Dict[str, Any] = field(default_factory=dict)
    texture_tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

BUILDING_TYPE_RULES = {
    "residential": {
        "types": ["house", "duplex", "apartment"],
        "styles": ["traditional", "suburban", "modern"],
        "roofs": ["gable", "shed", "flat"],
        "ages": ["old", "mid", "new"],
    },
    "commercial": {
        "types": ["storefront", "office", "mixed_use"],
        "styles": ["modern", "main_street", "brick_commercial"],
        "roofs": ["flat", "shed"],
        "ages": ["mid", "new"],
    },
    "industrial": {
        "types": ["warehouse", "factory"],
        "styles": ["industrial", "concrete", "metal"],
        "roofs": ["flat", "shed", "gable"],
        "ages": ["old", "mid"],
    },
    "default": {
        "types": ["generic_building"],
        "styles": ["generic"],
        "roofs": ["flat", "gable"],
        "ages": ["mid"],
    },
}
