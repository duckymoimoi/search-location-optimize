"""Compose corpus v1→v2→v3 POI identity maps. Does not rewrite locked corpora."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from stage1_brand_v3_common import (
    CORPUS_V2,
    CORPUS_V3,
    MEMBERSHIP_V3,
    compose_migration,
    load_migration_tables,
    load_v3_core,
    refuse_nonempty,
    sha256_file,
    source_record,
    write_json,
)


def compose(output_dir: Path, *, overwrite: bool = False) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "composed_poi_id_migration_v1_v3.parquet"
    if path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite {path}")
    core = load_v3_core()
    v3_ids = set(core["poi_id"].astype(str))
    mig2, mig3 = load_migration_tables()
    composed = compose_migration(mig2, mig3, v3_ids)
    pq.write_table(pa.Table.from_pandas(composed, preserve_index=False), path, compression="zstd")
    counts = composed["composed_action"].value_counts().to_dict()
    manifest = {
        "dataset": "composed_poi_id_migration_v1_v3",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "sources": {
            "poi_corpus_v2_migration": source_record(CORPUS_V2 / "poi_id_migration.parquet"),
            "poi_corpus_v3_migration": source_record(CORPUS_V3 / "poi_id_migration.parquet"),
            "poi_corpus_v3_core": source_record(CORPUS_V3 / "pois_core.parquet"),
        },
        "counts": {
            "rows": int(len(composed)),
            "mapped": int((composed["mapped_poi_id"].astype(str) != "").sum()),
            "by_action": {str(key): int(value) for key, value in counts.items()},
        },
        "artifacts": {path.name: {"sha256": sha256_file(path), "bytes": path.stat().st_size}},
    }
    write_json(output_dir / "composed_migration_manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=MEMBERSHIP_V3)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if args.output_dir.exists() and any(args.output_dir.iterdir()) and not args.overwrite:
        refuse_nonempty(args.output_dir)
    print(json.dumps(compose(args.output_dir, overwrite=args.overwrite), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
