"""Expand concise, manually authored Gold v2.1 case JSONL into serializer input.

Compact record contract:
  case_id, evidence, group_prefix, q01, q02, q03, q04
Each q01 is [text, tags]. Each q02-q04 is
  [text, difficulty, tags, mutation_evidence].
Optional positive_overrides and evidence_overrides are maps keyed by role.
The defaults are explicit draft assumptions, never an automatic qrel judgment.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "data/vietnam/stage1_eval_suite_v2/staging/gold_stage1_v2_1"


def expand(row: dict) -> dict:
    case_id = row["case_id"]
    evidence = row["evidence"]
    if not isinstance(evidence, list) or not evidence:
        raise ValueError(f"{case_id}: source evidence list required")
    if any(not str(item).startswith(("corpus_v2:", "corpus_v3:", "pbf:")) for item in evidence):
        raise ValueError(f"{case_id}: evidence must point to a pinned corpus or local OSM PBF facts")
    queries: dict[str, dict] = {}
    for role in ("q01", "q02", "q03", "q04"):
        fields = row[role]
        if role == "q01":
            if len(fields) != 2:
                raise ValueError(f"{case_id}: q01 must be [text,tags]")
            text, tags = fields
            query = {
                "text": text, "difficulty": "clean", "tags": tags,
                "group_ready_prefix": row["group_prefix"],
                "entity_ready_prefix": text,
            }
        else:
            if len(fields) != 4:
                raise ValueError(f"{case_id}: {role} must be [text,difficulty,tags,mutation_evidence]")
            text, difficulty, tags, mutations = fields
            query = {
                "text": text, "difficulty": difficulty, "tags": tags,
                "mutation_evidence": mutations,
            }
        query["positives"] = row.get("positive_overrides", {}).get(role, "target")
        query["qrel_evidence"] = row.get("evidence_overrides", {}).get(role, evidence)
        query["review_status"] = "needs_review"
        queries[role] = query
    return {"case_id": case_id, "queries": queries}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staging", type=Path, default=STAGING)
    parser.add_argument("--batch", required=True, help="e.g. 004")
    args = parser.parse_args()
    source = args.staging / "compact" / f"batch_{args.batch}.jsonl"
    target = args.staging / "authored" / f"batch_{args.batch}.jsonl"
    if target.exists():
        raise SystemExit(f"Refusing to overwrite existing authored batch: {target}")
    rows = [expand(json.loads(line)) for line in source.read_text(encoding="utf-8").splitlines() if line.strip()]
    ids = [row["case_id"] for row in rows]
    if not rows or len(ids) != len(set(ids)):
        raise SystemExit("Empty compact batch or duplicate case_id")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
    print(json.dumps({"cases": len(rows), "output": str(target)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
