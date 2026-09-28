"""Inference-only paired ablation on downloaded checkpoints. Never trains.

Outputs immutable per-query traces; evaluator can replay without GPU or ES.
Run with PYTHONPATH pointing to api and POI_INDEX/POI_ES_URL pinned.
"""
from __future__ import annotations

import argparse
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import platform
import time

import numpy as np

KS = (1, 5, 10, 20, 100)


def dump(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def accepted_ids(raw):
    if isinstance(raw, str):
        return json.loads(raw) if raw.startswith("[") else raw.split("|")
    return list(raw)


def metrics(rows, mode):
    groups = {}
    for row in rows:
        ids = row.get("stages", {}).get(mode, [])
        accepted = set(row["accepted_poi_ids"])
        rank = next((i for i, x in enumerate(ids, 1) if x in accepted), None)
        vals = {f"Hit@{k}": float(rank is not None and rank <= k) for k in KS}
        vals["MRR@10"] = 1 / rank if rank and rank <= 10 else 0.0
        vals["coverage@20"] = len(accepted.intersection(ids[:20])) / len(accepted)
        groups.setdefault(row["group_id"], []).append(vals)
    keys = [f"Hit@{k}" for k in KS] + ["MRR@10", "coverage@20"]
    family = rows[0]["suite"] == "brand_dev"
    units = [dict((key, float(np.mean([x[key] for x in values]))) for key in keys) for values in groups.values()] if family else [x for values in groups.values() for x in values]
    return {key: float(np.mean([x[key] for x in units])) for key in keys}


def evaluate(folder):
    folder = Path(folder)
    rows = [json.loads(x) for x in (folder / "queries.jsonl").read_text(encoding="utf-8").splitlines()]
    if len({(r["suite"], r["query_id"], r["normalizer"]) for r in rows}) != len(rows):
        raise ValueError("Duplicate query trace")
    report, regressions = {}, []
    for suite in sorted({r["suite"] for r in rows}):
        for normalizer in sorted({r["normalizer"] for r in rows}):
            subset = [r for r in rows if r["suite"] == suite and r["normalizer"] == normalizer]
            modes = sorted(set().union(*(r.get("stages", {}) for r in subset)))
            result = {"n": len(subset), "errors": sum(r["status"] != "ok" for r in subset), "modes": {mode: metrics(subset, mode) for mode in modes}}
            groups = sorted({r["group_id"] for r in subset})
            rng = np.random.default_rng(42)
            indices = rng.integers(0, len(groups), size=(10000, len(groups)))
            complement = {}
            for mode in modes:
                if mode == "ann_raw":
                    continue
                deltas, rescue, harm = [], 0, 0
                for group in groups:
                    differences = []
                    for r in subset:
                        if r["group_id"] != group:
                            continue
                        accepted = set(r["accepted_poi_ids"])
                        base = bool(accepted.intersection(r.get("stages", {}).get("ann_raw", [])[:1]))
                        hit = bool(accepted.intersection(r.get("stages", {}).get(mode, [])[:1]))
                        rescue += hit and not base
                        harm += base and not hit
                        differences.append(int(hit) - int(base))
                        if base != hit:
                            regressions.append({"suite": suite, "normalizer": normalizer, "mode": mode, "query_id": r["query_id"], "group_id": group, "query_text": r["query_text"], "delta_hit1": int(hit)-int(base)})
                    deltas.append(np.mean(differences))
                boot = np.asarray(deltas)[indices].mean(axis=1)
                complement[mode] = {"rescued_queries": int(rescue), "harmed_queries": int(harm), "group_mean_delta_hit1": float(np.mean(deltas)), "ci95": np.quantile(boot, [0.025, 0.975]).tolist()}
            result["paired_vs_ann_raw"] = complement
            result["latency_microbenchmark_ms"] = {key: {"p50": float(np.quantile([r["timings_ms"][key] for r in subset if r["status"] == "ok"], .5)), "p95": float(np.quantile([r["timings_ms"][key] for r in subset if r["status"] == "ok"], .95))} for key in subset[0].get("timings_ms", {})}
            report[f"{suite}:{normalizer}"] = result
    dump(folder / "summary.json", report)
    (folder / "regressions.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in regressions), encoding="utf-8")
    return report


def run(args):
    import pandas as pd
    import torch
    from transformers import AutoModel, AutoTokenizer
    from es_client import ElasticsearchClient
    from es_query import ann_body, search_candidates
    from lexical import lexical_body
    from ranking import candidate_document_stages, rank_candidates_traced, _dense_evidence, _hybrid_evidence
    import ranking
    # Dedup repeatedly compares immutable folded names across candidate pairs.
    ranking.fold = lru_cache(maxsize=100000)(ranking.fold)
    from settings import INDEX_NAME, ES_URL, POLICY
    from textnorm import encoder_input

    root = Path(args.root)
    out = root / args.out
    out.mkdir(parents=True, exist_ok=False)
    model_path = root / "artifacts/models/me5_6k_devlock_serving"
    emb_path = root / "artifacts/embeddings/me5_small_v3_6k_devlock"
    if INDEX_NAME != "vn-poi-core-v3-me5-6k-devlock":
        raise ValueError("This experiment requires the pinned 6k devlock index")
    client = ElasticsearchClient(ES_URL)
    count = client.request("POST", f"/{INDEX_NAME}/_count", {"query": {"term": {"destination_searchable": True}}})["count"]
    poi = pd.read_parquet(root / "data/vietnam/train_stage1_v6_hardneg_6k_clean/query_train_view.parquet")
    poi = poi[poi.split == "dev"].copy()
    brand = pd.read_parquet(root / "data/vietnam/train_stage1_brand_queries_v3/brand_intent_queries_v3.parquet")
    brand_qrels = pd.read_parquet(root / "data/vietnam/train_stage1_brand_queries_v3/brand_query_qrels_v3.parquet")
    positives = brand_qrels[brand_qrels.relation == "positive_pool"].groupby("query_id").poi_id.agg(list)
    brand["acceptable_poi_ids"] = brand.query_id.map(positives)
    split_path = root / "data/vietnam/train_stage1_brand_splits_v1/family_split.json"
    splits = json.loads(split_path.read_text(encoding="utf-8"))
    families = {r["brand_family_id"] for r in splits["families"] if r["split"] == "dev"}
    brand = brand[brand.brand_family_id.isin(families)]
    if not len(brand) or brand.brand_family_id.nunique() != len(families):
        raise ValueError("Incomplete brand dev family coverage")
    records = []
    for suite, frame, group_key in [("poi_dev", poi, "case_id"), ("brand_dev", brand, "brand_family_id")]:
        if args.suite != "both" and args.suite != suite:
            continue
        for row in frame.to_dict("records"):
            records.append({"suite": suite, "query_id": str(row["query_id"]), "group_id": str(row[group_key]), "query_text": str(row["query_text"]), "accepted_poi_ids": accepted_ids(row["acceptable_poi_ids"]), "stratum": str(row.get("primary_sampling_stratum", row.get("namespace", "")))})
    if args.limit:
        records = records[:args.limit]
    if args.sessions:
        records = [json.loads(line) for line in (root/args.sessions).read_text(encoding='utf-8').splitlines() if line]
    ids = pd.read_parquet(emb_path / "poi_ids.parquet").poi_id.astype(str).tolist()
    vectors = np.load(emb_path / "corpus_embeddings.npy")
    if vectors.shape != (len(ids), 384) or count != len(ids) or len(set(ids)) != len(ids):
        raise ValueError("Corpus/index/id-map mismatch")
    if not np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-4):
        raise ValueError("Unnormalized corpus vectors")
    id_set = set(ids)
    if any(not r["accepted_poi_ids"] or not set(r["accepted_poi_ids"]).issubset(id_set) for r in records):
        raise ValueError("Invalid acceptable ids")
    mapping = client.request("GET", f"/{INDEX_NAME}/_mapping")
    provenance = root / "artifacts/results/dense_first/source_inventory.json"
    manifest = {"schema_version": "dense-first-manifest-v1", "status": "running", "training": False, "dataset_role": args.dataset_role, "index": INDEX_NAME, "n_queries": len(records), "normalizers": args.normalizers, "k": 100, "budgets": [50, 100], "policy": POLICY, "mapping": mapping, "cpu": platform.processor(), "cuda": torch.cuda.is_available(), "source_inventory": json.loads(provenance.read_text(encoding="utf-8")) if provenance.exists() else None, "hashes": {str(p.relative_to(root)): digest(p) for p in [model_path / "model.safetensors", model_path / "tokenizer.json", emb_path / "corpus_embeddings.npy", emb_path / "poi_ids.parquet", split_path, root / "data/vietnam/train_stage1_v6_hardneg_6k_clean/query_train_view.parquet", root / "data/vietnam/train_stage1_brand_queries_v3/brand_intent_queries_v3.parquet", root / "data/vietnam/train_stage1_brand_queries_v3/brand_query_qrels_v3.parquet", Path(__file__)]}}
    if args.sessions:
        manifest['sessions_sha256'] = digest(root/args.sessions)
    if not torch.cuda.is_available():
        raise ValueError("Downloaded checkpoint inference experiment requires local CUDA")
    manifest["gpu"] = torch.cuda.get_device_name(0)
    manifest["torch"] = torch.__version__
    dump(out / "manifest.json", manifest)
    device = torch.device("cuda")
    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
    model = AutoModel.from_pretrained(model_path, local_files_only=True).to(device).eval()
    corpus = torch.from_numpy(vectors).to(device)
    fields = ["canonical_id", "search_label", "search_aliases", "address", "ranking_point", "housenumber", "entity_group_id", "branch_id", "category", "preserve_individual_access_point"]
    cache = {}
    # Reuse pure per-query document features across ablation profiles.
    feature_caches = []
    def cached_feature(function):
        values = {}
        feature_caches.append(values)
        def wrapper(query, document):
            key = (query, document["canonical_id"])
            if key not in values:
                values[key] = function(query, document)
            return values[key]
        return wrapper
    for name in ("name_match_class", "name_address_evidence", "mixed_text_number_signals", "token_overlap", "accent_token_coverage"):
        setattr(ranking, name, cached_feature(getattr(ranking, name)))

    def encode(text):
        start = time.perf_counter()
        tokens = tokenizer(["query: " + text], return_tensors="pt", truncation=True, max_length=64).to(device)
        with torch.inference_mode():
            hidden = model(**tokens).last_hidden_state
            mask = tokens.attention_mask.unsqueeze(-1).float()
            vector = torch.nn.functional.normalize((hidden * mask).sum(1) / mask.sum(1), dim=1)[0]
        cpu = vector.cpu().numpy()
        return vector, cpu, (time.perf_counter() - start) * 1000

    for _ in range(10):
        encode("benchmark warmup không thuộc holdout")
    trace = out / "queries.jsonl"
    with trace.open("w", encoding="utf-8") as stream:
        for i, record in enumerate(records):
            for values in feature_caches:
                values.clear()
            lexical, lex_ms = search_candidates(client, lexical_body(record["query_text"], 100))
            lex_ids = [x["poi_id"] for x in lexical]
            for normalizer in args.normalizers:
                row = dict(record, schema_version="dense-first-trace-v1", normalizer=normalizer, dataset_role=args.dataset_role, status="ok")
                try:
                    actual = encoder_input(record["query_text"], normalizer)
                    vector, cpu, enc_ms = encode(actual)
                    ann, ann_ms = search_candidates(client, ann_body(cpu, 100))
                    ann_ids = [x["poi_id"] for x in ann]
                    start = time.perf_counter()
                    scores, positions = torch.topk(vector @ corpus.T, 100)
                    exact = [{"poi_id": ids[j], "source": "exact", "branch_rank": k, "raw_score": float(score), "score_kind": "cosine"} for k, (j, score) in enumerate(zip(positions.cpu().tolist(), scores.cpu().tolist()), 1)]
                    exact_ms = (time.perf_counter() - start) * 1000
                    fused, hybrid_evidence = _hybrid_evidence(lex_ids, ann_ids, depth=100)
                    union = list(dict.fromkeys(lex_ids + ann_ids))
                    missing = [x for x in union if x not in cache]
                    if missing:
                        response = client.request("POST", f"/{INDEX_NAME}/_mget", {"docs": [{"_id": poi_id, "_source": fields} for poi_id in missing]})
                        cache.update({x["_id"]: x["_source"] for x in response["docs"] if x.get("found")})
                    if any(x not in cache for x in union):
                        raise ValueError("Missing candidate metadata")
                    stages = {"lexical": lex_ids, "ann_raw": ann_ids, "exact_raw": [x["poi_id"] for x in exact], "hybrid_raw": fused[:100], "union": union}
                    for budget in (50, 100):
                        for source, ordering, evidence in [("ann", ann_ids, _dense_evidence(ann_ids)), ("hybrid", fused, hybrid_evidence)]:
                            ds = candidate_document_stages(ordering, [cache[x] for x in ordering], budget=budget)
                            stages[f"{source}_dedup_{budget}"] = [d["canonical_id"] for d in ds["after_dedup"]]
                            stages[f"{source}_cap_{budget}"] = [d["canonical_id"] for d in ds["after_cap"]]
                            for profile in ("dedup_only", "name_address", "name_quality", "current"):
                                ranked = rank_candidates_traced(record["query_text"], ds["after_cap"], evidence, None, profile=profile)
                                stages[f"{source}_{profile}_{budget}"] = [d[3]["canonical_id"] for d in ranked["final"]]
                    row.update(encoder_input=actual, stages=stages, candidates={"lexical": lexical, "dense": ann, "exact": exact}, ann_recall100=len(set(ann_ids).intersection(stages["exact_raw"])) / 100, timings_ms={"encode": enc_ms, "lexical": lex_ms, "ann": ann_ms, "exact": exact_ms})
                except Exception as exc:
                    row.update(status="error", error=f"{type(exc).__name__}: {exc}", stages={})
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                stream.flush()
                if row["status"] != "ok":
                    manifest["status"] = "failed"
                    manifest["error"] = row["error"]
                    dump(out / "manifest.json", manifest)
                    raise RuntimeError(row["error"])
            if (i + 1) % 100 == 0:
                print(f"{i+1}/{len(records)}", flush=True)
    evaluate(out)
    manifest["status"] = "complete"
    dump(out / "manifest.json", manifest)
    print(f"Output: {out}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="/repo")
    parser.add_argument("--out", required=True)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--suite", choices=("poi_dev", "brand_dev", "both"), default="both")
    parser.add_argument('--sessions')
    parser.add_argument('--dataset-role',default='dev')
    parser.add_argument('--normalizers',nargs='+',choices=['raw','glue_code_spans'],default=['raw','glue_code_spans'])
    parser.add_argument("--evaluate-only", action="store_true")
    args = parser.parse_args()
    if args.evaluate_only:
        evaluate(Path(args.root) / args.out)
    else:
        run(args)
