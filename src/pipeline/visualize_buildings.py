import json
from pathlib import Path
import matplotlib.pyplot as plt


def plot_polygon(polygon, color="blue", alpha=0.3):
    xs = [p[0] for p in polygon] + [polygon[0][0]]
    ys = [p[1] for p in polygon] + [polygon[0][1]]
    plt.fill(xs, ys, color=color, alpha=alpha)
    plt.plot(xs, ys, color=color)


def main():
    base_dir = Path(__file__).resolve().parents[2]

    lots_path = base_dir / "data" / "processed" / "lots.json"
    buildings_path = base_dir / "data" / "processed" / "buildings.json"

    with open(lots_path) as f:
        lots = json.load(f)

    with open(buildings_path) as f:
        buildings = json.load(f)

    plt.figure(figsize=(10, 8))

    # plot lots (light gray)
    for lot in lots:
        plot_polygon(lot["polygon"], color="gray", alpha=0.2)

    # plot buildings (blue)
    for b in buildings:
        plot_polygon(b["footprint"], color="blue", alpha=0.5)

    plt.title("Lots (gray) and Buildings (blue)")
    plt.xlabel("X")
    plt.ylabel("Y")
    plt.axis("equal")
    plt.show()


if __name__ == "__main__":
    main()