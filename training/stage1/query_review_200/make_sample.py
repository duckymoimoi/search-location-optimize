import json
import hashlib
from collections import defaultdict, Counter
from pathlib import Path
import pyarrow.parquet as pq

path = Path(r"d:\vsf\HANOI_QUERIES_20K\hanoi_queries_20k\queries_20k.parquet")
df = pq.read_table(path).to_pylist()

track_quota = {
    "retrieval_core": 90,
    "autocomplete": 30,
    "ambiguity_stress": 30,
    "ime_keystream": 25,
    "structured_code": 25,
}
assert sum(track_quota.values()) == 200

by_track = defaultdict(list)
for r in df:
    by_track[r["track"]].append(r)

rng_seed = 20260913


def stable_key(r):
    return hashlib.sha256(f"{rng_seed}|{r['query_id']}".encode()).hexdigest()


selected = []
selection_log = []
for track, quota in track_quota.items():
    rows = by_track[track]
    by_case = defaultdict(list)
    for r in rows:
        by_case[r["case_type"]].append(r)
    cases = sorted(by_case.keys())
    per_case = {c: sorted(by_case[c], key=stable_key) for c in cases}
    idxs = {c: 0 for c in cases}
    picked = []
    while len(picked) < quota and any(idxs[c] < len(per_case[c]) for c in cases):
        for c in cases:
            if len(picked) >= quota:
                break
            i = idxs[c]
            if i < len(per_case[c]):
                picked.append(per_case[c][i])
                idxs[c] = i + 1
    selected.extend(picked)
    selection_log.append((track, len(picked), Counter(r["case_type"] for r in picked)))

out_dir = Path(r"d:\vsf\training\stage1\query_review_200")
out_dir.mkdir(parents=True, exist_ok=True)

fields = [
    "query_id",
    "query",
    "clean_query",
    "poi_name",
    "poi_address",
    "category",
    "case_type",
    "track",
    "split",
    "query_surface",
    "generation_method",
    "intended_poi_id",
    "compatible_count",
    "supervised_training_eligible",
    "main_metric_candidate",
    "label_status",
    "label_completeness",
    "requires_review",
    "typo_source",
    "typo_result",
    "mutation_operations",
    "ime_mode",
    "namespace_in_query",
    "is_structured_code",
    "main_metric_exclusion_reasons",
    "training_exclusion_reasons",
    "review_reasons",
    "known_compatible_poi_ids",
    "corruption_collision_poi_ids",
    "dataset_version",
]


def slim(r):
    o = {k: r.get(k) for k in fields}
    for k in ["known_compatible_poi_ids", "corruption_collision_poi_ids"]:
        v = o.get(k) or []
        o[k] = v[:8]
        o[k + "_total"] = len(v)
    return o


slimmed = [slim(r) for r in selected]
out_jsonl = out_dir / "sample_200.jsonl"
with out_jsonl.open("w", encoding="utf-8") as f:
    for r in slimmed:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

md = out_dir / "sample_200_readable.md"
with md.open("w", encoding="utf-8") as f:
    f.write("# Stratified sample 200 queries for quality review\n\n")
    f.write(f"Seed: {rng_seed}. Quotas: {track_quota}\n\n")
    for track, n, cc in selection_log:
        f.write(f"- {track}: {n} ({dict(cc)})\n")
    f.write("\n")
    for i, r in enumerate(slimmed, 1):
        f.write(f"## {i}. [{r['track']}/{r['case_type']}] `{r['query_id']}`\n")
        f.write(f"- **query**: `{r['query']}`\n")
        f.write(f"- **clean_query**: `{r['clean_query']}`\n")
        f.write(f"- **POI**: {r['poi_name']} | {r['poi_address']} | {r['category']}\n")
        f.write(
            f"- **split**: {r['split']} | surface={r['query_surface']} | gen={r['generation_method']}\n"
        )
        f.write(
            f"- **compat**: {r['compatible_count']} | train_elig={r['supervised_training_eligible']} | main_metric={r['main_metric_candidate']}\n"
        )
        f.write(
            f"- **label**: {r['label_status']} / {r['label_completeness']} | requires_review={r['requires_review']}\n"
        )
        if r.get("typo_source") or r.get("mutation_operations"):
            f.write(
                f"- **mutation**: {r.get('typo_source')} → {r.get('typo_result')} ops={r.get('mutation_operations')} ime={r.get('ime_mode')}\n"
            )
        if (
            r.get("main_metric_exclusion_reasons")
            or r.get("training_exclusion_reasons")
            or r.get("review_reasons")
        ):
            f.write(
                f"- **flags**: main_excl={r.get('main_metric_exclusion_reasons')} train_excl={r.get('training_exclusion_reasons')} review={r.get('review_reasons')}\n"
            )
        f.write("\n")

print("Wrote", out_jsonl)
print("Wrote", md)
print("Sample size", len(slimmed))
print("By track", Counter(r["track"] for r in slimmed))
print("By split", Counter(r["split"] for r in slimmed))
print("By case", Counter(r["case_type"] for r in slimmed).most_common())
print("Train eligible", sum(1 for r in slimmed if r["supervised_training_eligible"]))
print("Main metric", sum(1 for r in slimmed if r["main_metric_candidate"]))
print("Requires review", sum(1 for r in slimmed if r["requires_review"]))
print("Compat>1", sum(1 for r in slimmed if (r["compatible_count"] or 0) > 1))
print("Compat>50", sum(1 for r in slimmed if (r["compatible_count"] or 0) > 50))
