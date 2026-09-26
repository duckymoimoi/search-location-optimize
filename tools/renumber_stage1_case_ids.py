"""Compact train20k case_id holes in authored batches and the 20k pool."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from serialize_stage1_v6 import serialize  # noqa: E402

DATA = ROOT / "data/vietnam"
TRAIN20K = DATA / "train_stage1_20k"
WORK = DATA / "train_stage1_queries_v6"

BATCHES = [
    {
        "id": "003",
        "dir": WORK / "staging/003_hard_noise_500",
        "csv": "query_variants_v6_hard_noise_500_final.csv",
        "rows": "authored_rows_500_final.jsonl",
        "trace": "authoring_trace_500_final.jsonl",
        "start": 1,
        "rewrite": False,
    },
    {
        "id": "004",
        "dir": WORK / "staging/004_coverage_501_1000",
        "csv": "query_variants.csv",
        "rows": "authored_rows.jsonl",
        "trace": "authoring_trace.jsonl",
        "start": 501,
        "rewrite": True,
    },
    {
        "id": "005",
        "dir": WORK / "staging/005_coverage_1001_1500",
        "csv": "query_variants.csv",
        "rows": "authored_rows.jsonl",
        "trace": "authoring_trace.jsonl",
        "start": 1001,
        "rewrite": False,
    },
    {
        "id": "006",
        "dir": WORK / "staging/006_coverage_1501_2002",
        "csv": "query_variants.csv",
        "rows": "authored_rows.jsonl",
        "trace": "authoring_trace.jsonl",
        "start": 1501,
        "rewrite": True,
    },
    {
        "id": "007",
        "dir": WORK / "staging/007_coverage_2003_2504",
        "csv": "query_variants.csv",
        "rows": "authored_rows.jsonl",
        "trace": "authoring_trace.jsonl",
        "start": 2001,
        "rewrite": True,
    },
]

CASE_RE = re.compile(r"train20k-\d{5}")
TWENTY_K_SCHEMA = pa.schema(
    [
        ("case_id", pa.string()),
        ("poi_id", pa.string()),
        ("name", pa.string()),
        ("brand", pa.string()),
        ("ref", pa.string()),
        ("category", pa.string()),
        ("province", pa.string()),
        ("subdistrict", pa.string()),
        ("housenumber", pa.string()),
        ("street", pa.string()),
        ("address_text", pa.string()),
        ("address_status", pa.string()),
        ("primary_sampling_stratum", pa.string()),
        ("region", pa.string()),
        ("clean_reason", pa.string()),
        ("clean_pass", pa.bool_()),
    ]
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def case_num(case_id: str) -> int:
    return int(case_id.split("-")[1])


def fmt_case(n: int) -> str:
    return f"train20k-{n:05d}"


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def unique_case_ids(csv_path: Path) -> list[str]:
    _, rows = read_csv(csv_path)
    seen: list[str] = []
    have: set[str] = set()
    for row in rows:
        cid = row["case_id"]
        if cid not in have:
            have.add(cid)
            seen.append(cid)
    seen.sort(key=case_num)
    return seen


def build_authored_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for batch in BATCHES:
        old_ids = unique_case_ids(batch["dir"] / batch["csv"])
        if len(old_ids) != 500:
            raise SystemExit(f"{batch['id']} has {len(old_ids)} cases")
        for offset, old in enumerate(old_ids):
            mapping[old] = fmt_case(batch["start"] + offset)
    if len(mapping) != 2500 or len(set(mapping.values())) != 2500:
        raise SystemExit("authored map is not 2500 unique")
    return mapping


def remap_case(value: str, mapping: dict[str, str]) -> str:
    return mapping.get(value, value)


def remap_variant(value: str, mapping: dict[str, str]) -> str:
    if not value or "-v" not in value:
        return remap_case(value, mapping)
    case, slot = value.rsplit("-", 1)
    return f"{remap_case(case, mapping)}-{slot}"


def remap_obj(obj, mapping: dict[str, str]):
    if isinstance(obj, dict):
        out = {}
        for key, value in obj.items():
            if key == "case_id" and isinstance(value, str):
                out[key] = remap_case(value, mapping)
            elif key in {"variant_id", "parent_variant_id"} and isinstance(value, str):
                out[key] = remap_variant(value, mapping)
            else:
                out[key] = remap_obj(value, mapping)
        return out
    if isinstance(obj, list):
        return [remap_obj(item, mapping) for item in obj]
    return obj


def remap_jsonl(path: Path, mapping: dict[str, str]) -> None:
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = remap_obj(json.loads(line), mapping)
        lines.append(json.dumps(rec, ensure_ascii=False))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def remap_csv_ids(path: Path, mapping: dict[str, str]) -> None:
    headers, rows = read_csv(path)
    for row in rows:
        if "case_id" in row:
            row["case_id"] = remap_case(row["case_id"], mapping)
        if "variant_id" in row:
            row["variant_id"] = remap_variant(row["variant_id"], mapping)
    rows.sort(key=lambda r: (case_num(r["case_id"]), r.get("variant_id", "")))
    write_csv(path, headers, rows)


def remap_text_ids(path: Path, mapping: dict[str, str]) -> None:
    text = path.read_text(encoding="utf-8")

    def repl(match: re.Match[str]) -> str:
        return mapping.get(match.group(0), match.group(0))

    path.write_text(CASE_RE.sub(repl, text), encoding="utf-8")


def rewrite_batch(batch: dict, mapping: dict[str, str]) -> None:
    folder: Path = batch["dir"]
    remap_jsonl(folder / batch["rows"], mapping)
    remap_jsonl(folder / batch["trace"], mapping)
    serialize(folder / batch["rows"], folder / batch["csv"], folder / Path(batch["csv"]).with_suffix(".parquet"))
    if (folder / "target_subset.csv").exists():
        remap_csv_ids(folder / "target_subset.csv", mapping)
        headers, rows = read_csv(folder / "target_subset.csv")
        table_rows = []
        for row in rows:
            item = dict(row)
            item["clean_pass"] = str(item.get("clean_pass", "")).lower() == "true"
            item["ref"] = item.get("ref") or None
            table_rows.append(item)
        pq.write_table(pa.Table.from_pylist(table_rows, schema=TWENTY_K_SCHEMA), folder / "target_subset.parquet")
    if (folder / "authoring_packet.jsonl").exists():
        remap_jsonl(folder / "authoring_packet.jsonl", mapping)
    specs = folder / "spec_batches"
    if specs.exists():
        for path in sorted(specs.glob("*.jsonl")):
            remap_jsonl(path, mapping)
        for path in sorted(specs.glob("*_validation.json")):
            remap_text_ids(path, mapping)
    for name in (
        "FINAL_MANIFEST.json",
        "LOCKED.json",
        "PARTIAL_STATUS.json",
        "validation_full_500.json",
        "validation_full_500_final.json",
        "authoring_packet_manifest.json",
    ):
        path = folder / name
        if path.exists():
            remap_text_ids(path, mapping)


def refresh_manifest_hashes(batch: dict) -> None:
    folder: Path = batch["dir"]
    man_path = folder / "FINAL_MANIFEST.json"
    if not man_path.exists():
        return
    man = json.loads(man_path.read_text(encoding="utf-8"))
    artifacts = man.get("artifacts", {})
    file_map = {
        "authored_rows": batch["rows"],
        "authoring_trace": batch["trace"],
        "csv": batch["csv"],
        "parquet": str(Path(batch["csv"]).with_suffix(".parquet")),
    }
    if "validation_report" in artifacts:
        report_name = artifacts["validation_report"]["path"]
        file_map["validation_report"] = report_name
    for key, rel in file_map.items():
        path = folder / rel
        if key not in artifacts or not path.exists():
            continue
        artifacts[key]["sha256"] = sha256(path)
        artifacts[key]["bytes"] = path.stat().st_size
    if (folder / "target_subset.parquet").exists() and "target_subset" in man:
        man["target_subset"]["sha256"] = sha256(folder / "target_subset.parquet")
    if (folder / "authoring_packet.jsonl").exists() and "authoring_packet" in man:
        man["authoring_packet"]["sha256"] = sha256(folder / "authoring_packet.jsonl")
    man_path.write_text(json.dumps(man, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def rebuild_20k(mapping: dict[str, str]) -> None:
    headers, rows = read_csv(TRAIN20K / "target_pois_20k.csv")
    authored_old = set(mapping)
    kept_authored: list[dict] = []
    rest: list[dict] = []
    seen_old_authored: set[str] = set()
    for row in rows:
        old = row["case_id"]
        if old in authored_old:
            rec = dict(row)
            rec["case_id"] = mapping[old]
            kept_authored.append(rec)
            seen_old_authored.add(old)
        else:
            rest.append(row)
    missing = authored_old - seen_old_authored
    if missing != {"train20k-02005"} and missing:
        raise SystemExit(f"unexpected authored missing from 20k: {sorted(missing)}")
    if "train20k-02005" in missing:
        subset_headers, subset_rows = read_csv(
            WORK / "staging/007_coverage_2003_2504/target_subset.csv"
        )
        # Always look up the pre-remap case_id. The new id may already belong
        # to another 007 row (old 02003 → 02001, so 02003 still means Vietinbank).
        restored = [r for r in subset_rows if r["case_id"] == "train20k-02005"]
        if restored:
            restored[0] = dict(restored[0])
            restored[0]["case_id"] = mapping["train20k-02005"]
        if len(restored) != 1:
            raise SystemExit("could not restore train20k-02005 into 20k")
        kept_authored.append({key: restored[0].get(key, "") for key in headers})

    rest.sort(key=lambda r: case_num(r["case_id"]))
    unused: list[dict] = []
    next_id = 2501
    unused_map: dict[str, str] = {}
    for row in rest:
        rec = dict(row)
        new_id = fmt_case(next_id)
        unused_map[row["case_id"]] = new_id
        rec["case_id"] = new_id
        unused.append(rec)
        next_id += 1

    combined = kept_authored + unused
    combined.sort(key=lambda r: case_num(r["case_id"]))
    nums = [case_num(r["case_id"]) for r in combined]
    if nums != list(range(1, len(combined) + 1)):
        raise SystemExit(f"20k not contiguous 1..{len(combined)}")
    write_csv(TRAIN20K / "target_pois_20k.csv", headers, combined)
    table_rows = []
    for row in combined:
        item = {key: (row.get(key) or None) for key in headers}
        item["case_id"] = row["case_id"]
        item["poi_id"] = row["poi_id"]
        item["clean_pass"] = str(row.get("clean_pass", "")).lower() == "true"
        if item["ref"] == "":
            item["ref"] = None
        table_rows.append(item)
    pq.write_table(pa.Table.from_pylist(table_rows, schema=TWENTY_K_SCHEMA), TRAIN20K / "target_pois_20k.parquet")

    remap_rows = [{"old_case_id": old, "new_case_id": new, "scope": "authored"} for old, new in mapping.items()]
    remap_rows.extend(
        {"old_case_id": old, "new_case_id": new, "scope": "unused_pool"}
        for old, new in unused_map.items()
    )
    remap_rows.sort(key=lambda r: (r["scope"], case_num(r["new_case_id"])))
    write_csv(
        TRAIN20K / "case_id_remap.csv",
        ["old_case_id", "new_case_id", "scope"],
        remap_rows,
    )
    write_csv(
        WORK / "case_id_remap.csv",
        ["old_case_id", "new_case_id", "scope"],
        remap_rows,
    )

    man = json.loads((TRAIN20K / "manifest.json").read_text(encoding="utf-8"))
    man["total_target_pois"] = len(combined)
    man["files"]["target_pois_20k.csv"] = {
        "rows": len(combined),
        "sha256": sha256(TRAIN20K / "target_pois_20k.csv"),
    }
    man["files"]["target_pois_20k.parquet"] = {
        "rows": len(combined),
        "sha256": sha256(TRAIN20K / "target_pois_20k.parquet"),
    }
    man["case_id_policy"] = (
        "Contiguous train20k-00001..N after compacting corpus-filter holes. "
        "Authored 003–007 occupy 00001–02500; unused pool continues at 02501. "
        "Restored authored train20k-02005 (PNJ) dropped by corpus v3 merge_duplicate."
    )
    man["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
    (TRAIN20K / "manifest.json").write_text(
        json.dumps(man, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("20k", len(combined), "unused_from", 2501, "to", next_id - 1)


def rebuild_combined() -> None:
    sys.path.insert(0, str(ROOT / "tools"))
    rows_out: list[dict] = []
    for batch in BATCHES:
        for line in (batch["dir"] / batch["rows"]).read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows_out.append(json.loads(line))
    rows_out.sort(key=lambda r: (case_num(r["case_id"]), r["variant_id"]))
    tmp = WORK / "_authored_rows_combined_tmp.jsonl"
    tmp.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows_out) + "\n", encoding="utf-8")
    try:
        n = serialize(tmp, WORK / "query_variants.csv", WORK / "query_variants.parquet")
    finally:
        if tmp.exists():
            tmp.unlink()
    if n != 15000:
        raise SystemExit(f"combined rows {n}")
    man = json.loads((WORK / "manifest.json").read_text(encoding="utf-8"))
    man["sources"]["target_pois"]["sha256"] = sha256(TRAIN20K / "target_pois_20k.parquet")
    man["published_train_table"]["csv"] = {
        "path": "query_variants.csv",
        "sha256": sha256(WORK / "query_variants.csv"),
        "bytes": (WORK / "query_variants.csv").stat().st_size,
    }
    man["published_train_table"]["parquet"] = {
        "path": "query_variants.parquet",
        "sha256": sha256(WORK / "query_variants.parquet"),
        "bytes": (WORK / "query_variants.parquet").stat().st_size,
    }
    man["published_train_table"]["note"] = (
        "Locked 003–007 after contiguous case_id compact: 00001–02500. "
        "001/002 QA staging excluded."
    )
    man["published_at_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    (WORK / "manifest.json").write_text(
        json.dumps(man, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("combined", n, sha256(WORK / "query_variants.csv"))


def main() -> int:
    mapping = build_authored_map()
    changed = {old: new for old, new in mapping.items() if old != new}
    print("authored remap", len(mapping), "changed", len(changed))
    print("sample", list(changed.items())[:8])

    # 20k first so 007 target_subset still has old 02005 when restoring
    rebuild_20k(mapping)

    for batch in BATCHES:
        if not batch["rewrite"]:
            print("skip rewrite", batch["id"])
            continue
        print("rewrite", batch["id"])
        rewrite_batch(batch, mapping)
        refresh_manifest_hashes(batch)

    rebuild_combined()

    _, qrows = read_csv(WORK / "query_variants.csv")
    qcases = sorted({case_num(r["case_id"]) for r in qrows})
    if qcases != list(range(1, 2501)):
        raise SystemExit(f"combined cases not 1-2500: {qcases[:5]}..{qcases[-5:]} n={len(qcases)}")
    _, trows = read_csv(TRAIN20K / "target_pois_20k.csv")
    tcases = [case_num(r["case_id"]) for r in trows]
    if tcases != list(range(1, len(trows) + 1)):
        raise SystemExit("20k case_ids not contiguous")
    authored_new = {mapping[old] for old in mapping}
    twenty_set = {r["case_id"] for r in trows}
    if not authored_new <= twenty_set:
        raise SystemExit(f"authored not subset of 20k: {sorted(authored_new - twenty_set)[:10]}")
    print("OK authored 00001-02500; 20k 00001-%05d" % len(trows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
