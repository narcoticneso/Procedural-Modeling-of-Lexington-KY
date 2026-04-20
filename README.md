# Procedural Modeling of Lexington, KY

## Overview
This project generates a procedural city model of Lexington, KY. The system has a pipeline approach with stages that contribute to building a complete urban environment.

---

## Pipeline Structure
Roads → Lots → Buildings → (Geometry / Rendering)

---

## Building Generation Files

### `src/buildings/building_types.py`
Defines the core strucutres and characteristics of the buildings.

---

### `src/buildings/building_generator.py`
Implements the building generation logicby taking a list of lots as input, assigning random building type, style, height, and roof which creates a building footprint, and then outputs the building data for the next stage. A note is that once more zoning/district information is availble, the rule making decisions of building characterisics will be more inflcuneced by that (downtown zoning giving more tall buildings, residential being houses, etc.).

---

### `src/pipeline/run_building_stage.py`
Runs the building generation pipeline by loading in the lots.json, then converting that data into lot objects, then generating buildings.json.

---

### `src/pipeline/visualize_buildings.py`
Provides a visualization by displaying lots (gray) and buildings (blue).

---

## Lots / Buildings Output Example

### Lots
`data/processed/lots.json`  
```json
[
  {
    "lot_id": "lot_001",
    "polygon": [[0, 0], [20, 0], [20, 15], [0, 15]],
    "centroid": [10, 7.5],
    "area": 300.0,
    "road_access": true,
    "district": "residential",
    "metadata": {}
  }
]
```

### Buildings
`data/processed/buildings.json`  
```json
[
  {
    "building_id": "bldg_001",
    "lot_id": "lot_001",
    "building_type": "house",
    "style": "traditional",
    "age": "mid",
    "floors": 2,
    "height": 6.0,
    "roof_type": "gable",
    "footprint": [[0, 0], [20, 0], [20, 15], [0, 15]],
    "district": "residential",
    "geometry_tags": {
      "extrude_height": 6.0,
      "floors": 2,
      "roof_type": "gable",
      "source_stage": "building_generation"
    },
    "texture_tags": ["residential", "house", "traditional", "mid"],
    "metadata": {
      "input_area": 300.0,
      "road_access": true
    }
  }
]
```


## What needs to be done:

(Geometry/Texture Step)
For each building:
    take buildings.json footprint
    extrude to height
    add roof
    build mesh
