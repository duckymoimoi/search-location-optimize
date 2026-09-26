"""Replace keyed JSONL objects with objects from one or more patch files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--patch", action="append", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--key", default="variant_id")
    parser.add_argument("--expect", type=int)
    args = parser.parse_args()

    if args.output.exists():
        raise FileExistsError(f"Refusing to overwrite: {args.output}")
    base = load(args.base)
    patches: dict[str, dict] = {}
    for path in args.patch:
        for obj in load(path):
            value = obj.get(args.key)
            if value is None:
                raise KeyError(f"{path}: missing {args.key}")
            if value in patches:
                raise ValueError(f"Duplicate patch key: {value}")
            patches[value] = obj

    base_keys = {obj.get(args.key) for obj in base}
    missing = sorted(set(patches) - base_keys)
    if missing:
        raise ValueError(f"Patch keys absent from base: {missing[:10]}")
    result = [patches.get(obj.get(args.key), obj) for obj in base]
    if args.expect is not None and len(result) != args.expect:
        raise ValueError(f"Expected {args.expect} objects, got {len(result)}")

    with args.output.open("x", encoding="utf-8", newline="\n") as handle:
        for obj in result:
            handle.write(json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"replaced {len(patches)} of {len(result)} objects")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
