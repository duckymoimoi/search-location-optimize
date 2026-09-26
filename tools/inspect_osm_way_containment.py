"""Inspect whether a source OSM node is inside a source way polygon (two PBF passes)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import osmium
from shapely.geometry import Point, Polygon

ROOT = Path(__file__).resolve().parents[1]


class WayTags(osmium.SimpleHandler):
    def __init__(self, way_id: int) -> None:
        super().__init__()
        self.way_id = way_id
        self.tags: dict[str, str] | None = None
        self.refs: list[int] = []

    def way(self, way: osmium.osm.Way) -> None:
        if way.id == self.way_id:
            self.tags = {t.k: t.v for t in way.tags}
            self.refs = [n.ref for n in way.nodes]


class NodeLocations(osmium.SimpleHandler):
    def __init__(self, ids: set[int]) -> None:
        super().__init__()
        self.ids = ids
        self.points: dict[int, tuple[float, float]] = {}
        self.target_tags: dict[str, str] | None = None
        self.target_id: int | None = None

    def node(self, node: osmium.osm.Node) -> None:
        if node.id in self.ids and node.location.valid():
            self.points[node.id] = (node.location.lon, node.location.lat)
            if node.id == self.target_id:
                self.target_tags = {t.k: t.v for t in node.tags}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--way", type=int, required=True)
    parser.add_argument("--node", type=int, required=True)
    parser.add_argument("--pbf", type=Path, default=ROOT / "vietnam-260910.osm.pbf")
    args = parser.parse_args()
    way = WayTags(args.way)
    way.apply_file(str(args.pbf), locations=False)
    if way.tags is None or len(way.refs) < 4:
        raise SystemExit("Way missing or too few vertices")
    locations = NodeLocations(set(way.refs) | {args.node})
    locations.target_id = args.node
    locations.apply_file(str(args.pbf), locations=False)
    missing = set(way.refs) - locations.points.keys()
    if missing or args.node not in locations.points:
        raise SystemExit(f"Missing coordinates for {len(missing)} way vertices or target node")
    vertices = [locations.points[ref] for ref in way.refs]
    polygon = Polygon(vertices)
    target = Point(locations.points[args.node])
    print(json.dumps({
        "way_id": args.way,
        "way_tags": way.tags,
        "way_vertex_count": len(way.refs),
        "node_id": args.node,
        "node_tags": locations.target_tags,
        "node_lon_lat": locations.points[args.node],
        "polygon_valid": polygon.is_valid,
        "node_inside_or_on_way": polygon.covers(target),
        "distance_degrees_to_way": target.distance(polygon),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
