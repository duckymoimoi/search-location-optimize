"""Merge JSONL files while optionally enforcing a unique object key."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", action="append", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--unique-key")
    parser.add_argument("--expect", type=int)
    args = parser.parse_args()

    if args.output.exists():
        raise FileExistsError(f"Refusing to overwrite: {args.output}")

    objects: list[dict] = []
    seen: set[str] = set()
    for path in args.input:
        with path.open("r", encoding="utf-8") as source:
            for line_number, line in enumerate(source, 1):
                if not line.strip():
                    continue
                obj = json.loads(line)
                if args.unique_key:
                    value = obj.get(args.unique_key)
                    if value is None:
                        raise KeyError(f"{path}:{line_number}: missing {args.unique_key}")
                    if value in seen:
                        raise ValueError(f"Duplicate {args.unique_key}: {value}")
                    seen.add(value)
                objects.append(obj)

    if args.expect is not None and len(objects) != args.expect:
        raise ValueError(f"Expected {args.expect} objects, got {len(objects)}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as target:
        for obj in objects:
            target.write(json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"merged {len(objects)} objects into {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
