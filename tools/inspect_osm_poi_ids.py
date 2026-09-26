"""Read original OSM node tags for exact IDs from the local PBF, read-only."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import osmium

ROOT = Path(__file__).resolve().parents[1]


class Nodes(osmium.SimpleHandler):
    def __init__(self, wanted: set[int]) -> None:
        super().__init__()
        self.wanted = wanted
        self.found: dict[int, dict] = {}

    def node(self, node: osmium.osm.Node) -> None:
        if node.id not in self.wanted:
            return
        self.found[node.id] = {
            "osm_id": node.id,
            "version": node.version,
            "timestamp": str(node.timestamp),
            "location": {"lat": node.location.lat, "lon": node.location.lon}
            if node.location.valid() else None,
            "tags": {tag.k: tag.v for tag in node.tags},
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("ids", nargs="+", type=int)
    parser.add_argument("--pbf", type=Path, default=ROOT / "vietnam-260910.osm.pbf")
    args = parser.parse_args()
    handler = Nodes(set(args.ids))
    handler.apply_file(str(args.pbf), locations=False)
    print(json.dumps({"found": list(handler.found.values()),
                      "missing": sorted(handler.wanted - handler.found.keys())},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
