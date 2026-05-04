# Procedural Modeling of Lexington, KY

## Overview
This project generates a procedural city model of Lexington, KY. The system has a pipeline approach with stages that contribute to building a complete urban environment.

### Full Pipeline Runner
`src/pipeline/run_full_pipeline.py`

Runs the stages in order:

1. Roads
2. Lots
3. Buildings
4. Texture engine
5. Building visualization

### Main Libraries Used

- `numpy`
- `pandas`
- `networkx`
- `matplotlib`
- `requests`
- `geopandas`
- `pyogrio`
- `shapely`
- `pyproj`
- `osmnx`
- `gdal`
- `pyvista`
- `vispy`
- `seamless-3dep`


## Instructions to Build and Render the City

### Step 1. Fetch Fayette GIS Data

```bash
python3 src/graph_tools/fetch_fayette_gis.py
```

This creates:

- `data/raw/gis/fayette_population.geojson`
- `data/raw/gis/fayette_hydro.geojson`
- `data/raw/gis/fayette_dem.asc`

### Step 1: Generate Buildings
Run the building stage to create `buildings.json` from the lots:
```powershell
python .\src\pipeline\run_building_stage.py
```

### Step 2. Generate Roads

#### Default road generation

```bash
python3 src/graph_tools/citygen_lsystem.py \
  --population-data data/raw/gis/fayette_population.geojson \
  --population-field population_density \
  --hydro-data data/raw/gis/fayette_hydro.geojson \
  --elevation-data data/raw/gis/fayette_dem.asc
```

#### Pure L-system road generation

```bash
python3 src/graph_tools/citygen_lsystem.py \
  --pure-lsystem \
  --population-data data/raw/gis/fayette_population.geojson \
  --population-field population_density \
  --hydro-data data/raw/gis/fayette_hydro.geojson \
  --elevation-data data/raw/gis/fayette_dem.asc
```

Both write to:

`data/raw/cityGen.txt`

### Step 3. Lot Generation
`src/lots/divison_lots.py`

Reads `data/raw/cityGen.txt`, polygonizes enclosed road space, and writes:

`data/processed/lots.json`

### Step 4. Building Generation
`src/pipeline/run_building_stage.py`

Reads `data/processed/lots.json` and writes:

`data/processed/buildings.json`

### Step 5: Generate Geometry (PyVista preview)
```powershell
python .\src\pipeline\run_geometry_stage.py
```
This renders the city with flat solid colors using PyVista. Useful for verifying geometry is correct.

Controls: R → reset camera, T → top-down view, I → isometric view

### Step 6: Render with Texture Engine (Vispy/OpenGL)
```powershell
python .\src\pipeline\run_texture_stage.py
```
This runs the full texture engine pipeline: face classification, material assignment, UV mapping, procedural texture generation, and renders the city with custom GLSL shaders and Phong lighting.

Controls:
- WASD → move camera
- Q/E → move up/down
- Left-drag → orbit camera
- Right-drag → pan camera
- Scroll → zoom
- R → reset camera
- T → top-down view
- I → isometric view

### Step 7: Demo Flythrough (optional)
```powershell
python .\src\pipeline\run_demo_flythrough.py
```
Automated camera flythrough for recording demos. Space to pause/resume, R to restart.

## Pipeline Structure
Roads → Lots → Buildings → Geometry/Mesh Building → Texture Engine & Rendering

## Building Generation Files

### `src/buildings/building_types.py`
Defines the core strucutres and characteristics of the buildings.

### `src/buildings/building_generator.py`
Implements the building generation logicby taking a list of lots as input, assigning random building type, style, height, and roof which creates a building footprint, and then outputs the building data for the next stage. A note is that once more zoning/district information is availble, the rule making decisions of building characterisics will be more inflcuneced by that (downtown zoning giving more tall buildings, residential being houses, etc.).

### `src/pipeline/run_building_stage.py`
Runs the building generation pipeline by loading in the lots.json, then converting that data into lot objects, then generating buildings.json.

### `src/pipeline/visualize_buildings.py`
Provides a visualization by displaying lots (gray) and buildings (blue).

## Geometry / Rendering Files

### `src/geometry/mesh_builder.py`
Handles the conversion from building data into 3D geometry. It takes the building footprints from buildings.json, normalizes and scales them for visualization, then extrudes each footprint into a 3D mesh. It also calls the roof builder to attach the appropriate roof geometry to each building before combining everything into a full city mesh.

### `src/geometry/roof_builder.py`
Implements the procedural roof generation logic. Based on the roof_type assigned in the building stage, different roof shapes are made. The roofs are generated from the footprint so they match the building size.

### `src/pipeline/run_geometry_stage.py`
Runs the full geometry pipeline. It loads buildings.json and lots.json, generates the 3D building meshes (including roofs), and creates a ground texture by rendering all roads and lot outlines into a single image. The script then renders the final scene with buildings on top of the textured ground and outputs both a mesh file and a screenshot.

## Texture Engine Files

### `src/textures/texture_engine.py`
Main texture engine class. Takes PyVista meshes from the geometry stage, classifies each triangle face by its surface normal (upward = roof, downward = floor, sideways = wall), assigns materials based on building type, generates UV coordinates, and outputs combined render-ready GPU buffers (positions, normals, UVs, label IDs).

### `src/textures/material_library.py`
Maps face label strings to material properties (color, tile scale, specular value, texture key). Includes `WALL_LABEL_BY_TYPE` which assigns different wall textures by building type: brick for residential, concrete panels for commercial, glass curtain wall for towers.

### `src/textures/procedural.py`
Algorithmic texture generators that produce RGBA uint8 numpy arrays. Generates brick (mortar grid + staggered rows + noise), concrete (gray + noise + panel seams), roof tiles (overlapping rows with gradient), wall concrete (panel seams), and wall glass (blue-tinted with dark grid frame). No external image files are used.

### `src/textures/uv_mapper.py`
Planar projection UV coordinate generator. Picks the two axes most perpendicular to the face normal, maps vertex positions to UV space, and scales by tile size so textures repeat at a consistent real-world scale regardless of face size.

### `src/textures/renderer.py`
Custom Vispy/OpenGL renderer. Uses `vispy.gloo` for direct OpenGL access with hand-written GLSL shaders. Packs all city geometry into a single vertex buffer for one draw call. Includes WASD camera movement at 60fps, mouse orbit/pan, and scroll zoom.

### `shaders/vertex.glsl` and `shaders/fragment.glsl`
GLSL shaders for the rendering pipeline. The vertex shader transforms positions and passes normals, UV coordinates, and face label IDs to the fragment shader. The fragment shader selects one of 7 texture samplers based on the label ID and applies Phong illumination (ambient + diffuse + specular) with per-material specular intensity.

### `src/pipeline/run_texture_stage.py`
Runs the full texture engine pipeline: loads buildings, builds meshes, processes them through the texture engine, generates procedural textures, and launches the Vispy renderer.

### `src/pipeline/run_demo_flythrough.py`
Automated camera flythrough with keyframe interpolation and smoothstep easing for presentation demo recording.

### `tests/test_texture_engine.py`
Test suite covering imports, label IDs, material lookup, face classification (including building-type-aware wall assignment), UV mapping, procedural texture generation, and ground quad construction.

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
