#!/usr/bin/env python3
"""Mine hard negatives for the v6 hard-negative pilot.

Reads compiled views + pinned mE5-small v3 embeddings. Writes only to
data/vietnam/train_stage1_v6_hardneg_pilot/.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
import time
import unicodedata
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "data" / "vietnam" / "train_stage1_v6_hardneg_pilot"
CORPUS_DOCS = ROOT / "data" / "vietnam" / "poi_corpus_v3" / "search_documents.parquet"
CORPUS_CORE = ROOT / "data" / "vietnam" / "poi_corpus_v3" / "pois_core.parquet"
EMB = ROOT / "artifacts" / "embeddings" / "me5_small_v3" / "corpus_embeddings.npy"
EMB_IDS = ROOT / "artifacts" / "embeddings" / "me5_small_v3" / "poi_ids.parquet"
MODEL_ID = "intfloat/multilingual-e5-small"
QUERY_PREFIX = "query: "
MAX_QUERY_TOKENS = 64
POOL_DEPTH = 100
SEED = 42
QUOTA = {"random": 2, "lexical_hard": 3, "dense_hard": 3, "same_brand_other_branch": 2}
MAX_NEGATIVES = 8
GOLD_DIR = ROOT / "data" / "vietnam" / "stage1_eval_suite_v2" / "gold_stage1_v2_1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").replace("đ", "d").replace("Đ", "D")
    return " ".join(
        "".join(ch for ch in unicodedata.normalize("NFD", text) if not unicodedata.combining(ch))
        .casefold()
        .split()
    )


def tokenize(text: str) -> list[str]:
    return [token for token in fold(text).split() if token]


def parse_ids(raw) -> list[str]:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return []
    if isinstance(raw, (list, tuple)):
        return [str(item) for item in raw]
    if hasattr(raw, "tolist") and not isinstance(raw, str):
        return [str(item) for item in raw.tolist()]
    text = str(raw).strip()
    if not text or text.lower() == "nan":
        return []
    if text.startswith("["):
        return [str(item) for item in json.loads(text)]
    return [part for part in text.split("|") if part]


def load_holdout_ids(gold_dir: Path) -> set[str]:
    sessions = pd.read_parquet(
        gold_dir / "query_sessions_v2_1.parquet",
        columns=["intended_poi_id", "acceptable_poi_ids"],
    )
    ids = set(sessions["intended_poi_id"].astype(str))
    for raw in sessions["acceptable_poi_ids"]:
        ids.update(parse_ids(raw))
    targets = pd.read_parquet(gold_dir / "target_pois_v2_1.parquet", columns=["poi_id"])
    ids.update(targets["poi_id"].astype(str))
    ids.discard("")
    return ids


class SparseBm25:
    def __init__(self, documents: list[str]):
        self.n_docs = len(documents)
        self.doc_len = np.zeros(self.n_docs, dtype=np.int32)
        df: dict[str, int] = defaultdict(int)
        postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for index, text in enumerate(documents):
            counts: dict[str, int] = defaultdict(int)
            tokens = tokenize(text)
            self.doc_len[index] = len(tokens)
            for token in tokens:
                counts[token] += 1
            for token, tf in counts.items():
                df[token] += 1
                postings[token].append((index, tf))
            if index == 0 or (index + 1) % 40000 == 0 or index + 1 == self.n_docs:
                print(f"  lexical docs {index + 1}/{self.n_docs}", flush=True)
        self.avgdl = float(self.doc_len.mean()) if self.n_docs else 1.0
        self.idf = {
            token: math.log((self.n_docs - freq + 0.5) / (freq + 0.5) + 1.0)
            for token, freq in df.items()
        }
        self.postings = {
            token: (
                np.fromiter((doc for doc, _ in pairs), dtype=np.int32, count=len(pairs)),
                np.fromiter((tf for _, tf in pairs), dtype=np.float32, count=len(pairs)),
            )
            for token, pairs in postings.items()
        }

    def topk(self, query: str, k: int) -> list[tuple[int, float]]:
        scores = np.zeros(self.n_docs, dtype=np.float32)
        k1 = 1.5
        b = 0.75
        for token in tokenize(query):
            if token not in self.postings:
                continue
            docs, tfs = self.postings[token]
            denom = tfs + k1 * (1.0 - b + b * self.doc_len[docs] / self.avgdl)
            scores[docs] += self.idf[token] * (tfs * (k1 + 1.0) / denom)
        if k >= self.n_docs:
            order = np.argsort(-scores)
        else:
            pool = np.argpartition(-scores, k)[:k]
            order = pool[np.argsort(-scores[pool])]
        return [(int(i), float(scores[i])) for i in order if scores[i] > 0][:k]


def encode_texts(texts: list[str], prefix: str, max_length: int, batch_size: int = 64) -> np.ndarray:
    import torch
    import torch.nn.functional as functional
    from transformers import AutoModel, AutoTokenizer

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModel.from_pretrained(MODEL_ID).to(device).eval()
    parts: list[np.ndarray] = []
    print(f"encoding {len(texts)} texts on {device} prefix={prefix!r} max_length={max_length}", flush=True)
    with torch.no_grad():
        for start in range(0, len(texts), batch_size):
            batch = [prefix + text for text in texts[start : start + batch_size]]
            tokens = tokenizer(
                batch,
                padding=True,
                truncation=True,
                max_length=max_length,
                return_tensors="pt",
            )
            tokens.pop("token_type_ids", None)
            tokens = {key: value.to(device) for key, value in tokens.items()}
            hidden = model(**tokens).last_hidden_state
            mask = tokens["attention_mask"].unsqueeze(-1).expand(hidden.size()).float()
            pooled = torch.sum(hidden * mask, dim=1) / torch.clamp(mask.sum(dim=1), min=1e-9)
            vec = functional.normalize(pooled, p=2, dim=1)
            parts.append(vec.cpu().numpy().astype(np.float32, copy=False))
            done = min(start + batch_size, len(texts))
            if start == 0 or done == len(texts) or done % (batch_size * 20) == 0:
                print(f"  encode {done}/{len(texts)}", flush=True)
    del model
    if device.type == "cuda":
        torch.cuda.empty_cache()
    return np.concatenate(parts)


def encode_queries(texts: list[str], batch_size: int = 64) -> np.ndarray:
    return encode_texts(texts, QUERY_PREFIX, MAX_QUERY_TOKENS, batch_size)


def dense_topk(
    queries: np.ndarray, corpus: np.ndarray, k: int, chunk: int = 64
) -> list[list[tuple[int, float]]]:
    out: list[list[tuple[int, float]]] = []
    for start in range(0, len(queries), chunk):
        scores = queries[start : start + chunk] @ corpus.T
        for row in scores:
            if k >= len(row):
                order = np.argsort(-row)
            else:
                pool = np.argpartition(-row, k)[:k]
                order = pool[np.argsort(-row[pool])]
            out.append([(int(i), float(row[i])) for i in order[:k]])
        done = min(start + chunk, len(queries))
        if start == 0 or done == len(queries) or done % (chunk * 20) == 0:
            print(f"  dense topk {done}/{len(queries)}", flush=True)
    return out


def dense_topk_torch(
    queries: np.ndarray, corpus: np.ndarray, k: int, chunk: int = 256
) -> list[list[tuple[int, float]]]:
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("dense_topk_torch requires CUDA")
    device = torch.device("cuda")
    corpus_t = torch.from_numpy(np.ascontiguousarray(corpus)).to(device)
    query_t = torch.from_numpy(np.ascontiguousarray(queries))
    out: list[list[tuple[int, float]]] = []
    for start in range(0, len(queries), chunk):
        scores = query_t[start : start + chunk].to(device) @ corpus_t.T
        values, indices = torch.topk(scores, k=min(k, scores.shape[1]), dim=1)
        idx_cpu = indices.cpu().numpy()
        val_cpu = values.cpu().numpy()
        for row_idx, row_val in zip(idx_cpu, val_cpu):
            out.append([(int(i), float(v)) for i, v in zip(row_idx, row_val)])
        done = min(start + chunk, len(queries))
        if start == 0 or done == len(queries) or done % (chunk * 4) == 0:
            print(f"  dense topk {done}/{len(queries)}", flush=True)
        del scores, values, indices
    del corpus_t, query_t
    torch.cuda.empty_cache()
    return out


def take_unique(
    ranked: list[tuple[str, int, float]],
    blocked: set[str],
    chosen: set[str],
    limit: int,
) -> list[dict[str, object]]:
    picked: list[dict[str, object]] = []
    if limit <= 0:
        return picked
    for poi_id, rank, score in ranked:
        if poi_id in blocked or poi_id in chosen:
            continue
        picked.append({"poi_id": poi_id, "source_rank": rank, "score": score})
        chosen.add(poi_id)
        if len(picked) >= limit:
            break
    return picked


def sample_random(poi_ids: list[str], blocked: set[str], chosen: set[str], limit: int, rng: random.Random) -> list[dict[str, object]]:
    picked: list[dict[str, object]] = []
    if limit <= 0 or not poi_ids:
        return picked
    attempts = 0
    max_attempts = max(64, limit * 64)
    n = len(poi_ids)
    while len(picked) < limit and attempts < max_attempts:
        attempts += 1
        poi_id = poi_ids[rng.randrange(n)]
        if poi_id in blocked or poi_id in chosen:
            continue
        picked.append({"poi_id": poi_id, "source_rank": None, "score": None})
        chosen.add(poi_id)
    return picked


def apply_kaggle_defaults() -> None:
    """Kaggle executes this file alone, with no CLI args and no sibling modules."""
    root = Path("/kaggle/input")
    if not root.exists() or any(arg.startswith("--") for arg in sys.argv[1:]):
        return
    needed = (
        "query_train_view.parquet",
        "query_relation_view.parquet",
        "search_documents.parquet",
        "pois_entity.parquet",
    )
    data = None
    for match in sorted(root.rglob("gold_holdout_ids.json")):
        parent = match.parent
        if all((parent / name).exists() for name in needed):
            data = parent
            break
    if data is None:
        raise SystemExit("Mine input pack not found under /kaggle/input")
    out = Path("/kaggle/working/mine_out")
    sys.argv.extend(
        [
            "--views",
            str(data),
            "--out",
            str(out),
            "--docs",
            str(data / "search_documents.parquet"),
            "--core",
            str(data / "pois_entity.parquet"),
            "--holdout-ids",
            str(data / "gold_holdout_ids.json"),
            "--holdout-gold",
            "",
            "--lexical-quota",
            "1",
            "--sibling-quota",
            "0",
            "--encode-corpus",
            "--require-gpu",
            "--passage-max-tokens",
            "128",
            "--encode-batch-size",
            "64",
        ]
    )


def main() -> None:
    apply_kaggle_defaults()
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=PILOT)
    parser.add_argument("--views", type=Path, default=None, help="Directory with compiled views. Defaults to --out.")
    parser.add_argument("--docs", type=Path, default=None)
    parser.add_argument("--core", type=Path, default=None)
    parser.add_argument("--sibling-quota", type=int, default=QUOTA["same_brand_other_branch"])
    parser.add_argument("--lexical-quota", type=int, default=QUOTA["lexical_hard"])
    parser.add_argument("--encode-corpus", action="store_true", help="Encode passages on this machine. Do not read a local embedding npy.")
    parser.add_argument("--require-gpu", action="store_true")
    parser.add_argument("--passage-max-tokens", type=int, default=128)
    parser.add_argument("--encode-batch-size", type=int, default=64)
    parser.add_argument("--holdout-ids", type=Path, default=None, help="JSON list of POI ids blocked from every pair.")
    parser.add_argument(
        "--holdout-gold",
        default=str(GOLD_DIR),
        help="Gold release directory. Those POI ids cannot be train pairs. Empty disables.",
    )
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    quota = dict(QUOTA)
    quota["same_brand_other_branch"] = max(0, int(args.sibling_quota))
    quota["lexical_hard"] = max(0, int(args.lexical_quota))
    holdout_ids: set[str] = set()
    holdout_dir = ""
    if args.holdout_ids is not None:
        holdout_ids = {str(item) for item in json.loads(args.holdout_ids.read_text(encoding="utf-8"))}
        holdout_dir = str(args.holdout_ids)
    else:
        holdout_dir = str(args.holdout_gold or "").strip()
        if holdout_dir:
            gold_dir = Path(holdout_dir)
            if not gold_dir.is_absolute():
                gold_dir = ROOT / gold_dir
            if not (gold_dir / "query_sessions_v2_1.parquet").exists():
                raise SystemExit(f"Missing Gold sessions: {gold_dir}")
            holdout_ids = load_holdout_ids(gold_dir)
    if args.require_gpu:
        import torch

        if not torch.cuda.is_available():
            raise SystemExit("This miner requires a CUDA GPU")

    views_dir = (args.views or out).resolve()
    docs_path = (args.docs or CORPUS_DOCS).resolve()
    core_path = (args.core or CORPUS_CORE).resolve()
    view_path = views_dir / "query_train_view.parquet"
    rel_path = views_dir / "query_relation_view.parquet"
    required = [view_path, rel_path, docs_path, core_path]
    if not args.encode_corpus:
        required.extend([EMB, EMB_IDS])
    for path in required:
        if not path.exists():
            raise SystemExit(f"Missing input: {path}")

    view = pd.read_parquet(view_path)
    relations = pd.read_parquet(rel_path)
    docs = pd.read_parquet(docs_path, columns=["poi_id", "passage_context"])
    core = pd.read_parquet(core_path, columns=["poi_id", "entity_group_id"])
    poi_ids = docs["poi_id"].astype(str).tolist()
    if args.encode_corpus:
        print(f"encoding {len(poi_ids)} passages; no embedding file is read", flush=True)
        corpus_vectors = encode_texts(
            docs["passage_context"].fillna("").astype(str).tolist(),
            "passage: ",
            int(args.passage_max_tokens),
            int(args.encode_batch_size),
        )
    else:
        emb_ids = pd.read_parquet(EMB_IDS)
        print("loading dense corpus vectors …", flush=True)
        corpus_vectors = np.asarray(np.load(EMB), dtype=np.float32)
        emb_poi_ids = emb_ids["poi_id"].astype(str).tolist()
        if poi_ids != emb_poi_ids:
            raise SystemExit("me5_small_v3 poi_ids do not match search_documents order")
        if corpus_vectors.shape[0] != len(poi_ids):
            raise SystemExit(f"Embedding rows {corpus_vectors.shape[0]} != docs {len(poi_ids)}")

    entity_members: dict[str, set[str]] = defaultdict(set)
    for row in core.itertuples(index=False):
        entity_members[str(row.entity_group_id)].add(str(row.poi_id))

    train = view[view["split"] == "train"].reset_index(drop=True)
    blocked: dict[str, set[str]] = defaultdict(set)
    ignore_ids: dict[str, set[str]] = defaultdict(set)
    siblings: dict[str, list[str]] = defaultdict(list)
    for row in relations.itertuples(index=False):
        if row.split != "train":
            continue
        if row.label in {"positive", "ignore"}:
            blocked[str(row.query_id)].add(str(row.poi_id))
        if row.label == "ignore":
            ignore_ids[str(row.query_id)].add(str(row.poi_id))
        if row.label == "hard_neg_candidate":
            siblings[str(row.query_id)].append(str(row.poi_id))
    for row in train.itertuples(index=False):
        query_id = str(row.query_id)
        blocked[query_id].update(entity_members.get(str(row.entity_group_id), ()))

    print(f"building lexical index on {len(poi_ids)} passages …", flush=True)
    t0 = time.time()
    lexical = SparseBm25(docs["passage_context"].fillna("").astype(str).tolist())
    print(f"lexical index ready in {time.time() - t0:.1f}s", flush=True)

    query_texts = train["query_text"].astype(str).tolist()
    query_vectors = encode_texts(query_texts, QUERY_PREFIX, MAX_QUERY_TOKENS, int(args.encode_batch_size))
    print("dense retrieval …", flush=True)
    if args.encode_corpus:
        dense_ranks = dense_topk_torch(query_vectors, np.asarray(corpus_vectors), POOL_DEPTH)
    else:
        dense_ranks = dense_topk(query_vectors, np.asarray(corpus_vectors), POOL_DEPTH)

    rng = random.Random(SEED)
    pairs: list[dict[str, object]] = []
    fill = {"random": 0, "lexical_hard": 0, "dense_hard": 0, "same_brand_other_branch": 0, "queries": 0}
    gold_pool_hits = 0
    weight_by_query = dict(zip(train["query_id"].astype(str), train["sample_weight"].astype(float)))

    print("assembling pairs …", flush=True)
    for offset, row in enumerate(train.itertuples(index=False)):
        query_id = str(row.query_id)
        positives = parse_ids(row.acceptable_poi_ids)
        blocked_ids = set(blocked.get(query_id, ()))
        blocked_ids.update(positives)
        blocked_ids.update(holdout_ids)
        weight = float(row.sample_weight)
        for poi_id in positives:
            pairs.append(
                {
                    "query_id": query_id,
                    "poi_id": poi_id,
                    "label": "positive",
                    "negative_source": None,
                    "source_rank": None,
                    "label_reason": "authored_acceptable",
                    "sample_weight": weight,
                }
            )
        lex_ranked = [
            (poi_ids[index], rank, score)
            for rank, (index, score) in enumerate(lexical.topk(str(row.query_text), POOL_DEPTH), start=1)
        ]
        dense_ranked = [
            (poi_ids[index], rank, score)
            for rank, (index, score) in enumerate(dense_ranks[offset], start=1)
        ]
        if holdout_ids:
            gold_pool_hits += sum(1 for poi_id, _rank, _score in lex_ranked if poi_id in holdout_ids)
            gold_pool_hits += sum(1 for poi_id, _rank, _score in dense_ranked if poi_id in holdout_ids)
        chosen: set[str] = set()
        lex_pick = take_unique(lex_ranked, blocked_ids, chosen, quota["lexical_hard"])
        dense_pick = take_unique(dense_ranked, blocked_ids, chosen, quota["dense_hard"])
        sib_ranked = [
            (poi_id, rank, 0.0)
            for rank, poi_id in enumerate(siblings.get(query_id, ()), start=1)
        ]
        sib_pick = take_unique(sib_ranked, blocked_ids, chosen, quota["same_brand_other_branch"])
        remain = max(0, MAX_NEGATIVES - len(lex_pick) - len(dense_pick) - len(sib_pick))
        rand_pick = sample_random(poi_ids, blocked_ids, chosen, min(quota["random"], remain), rng)

        for item in lex_pick:
            pairs.append(
                {
                    "query_id": query_id,
                    "poi_id": item["poi_id"],
                    "label": "negative",
                    "negative_source": "lexical_hard",
                    "source_rank": item["source_rank"],
                    "label_reason": "lexical_top100_minus_positive_ignore",
                    "sample_weight": weight,
                }
            )
        for item in dense_pick:
            pairs.append(
                {
                    "query_id": query_id,
                    "poi_id": item["poi_id"],
                    "label": "negative",
                    "negative_source": "dense_hard",
                    "source_rank": item["source_rank"],
                    "label_reason": "dense_top100_minus_positive_ignore",
                    "sample_weight": weight,
                }
            )
        for item in sib_pick:
            pairs.append(
                {
                    "query_id": query_id,
                    "poi_id": item["poi_id"],
                    "label": "negative",
                    "negative_source": "same_brand_other_branch",
                    "source_rank": item["source_rank"],
                    "label_reason": "forced_same_brand_other_branch",
                    "sample_weight": weight,
                }
            )
        for item in rand_pick:
            pairs.append(
                {
                    "query_id": query_id,
                    "poi_id": item["poi_id"],
                    "label": "negative",
                    "negative_source": "random",
                    "source_rank": None,
                    "label_reason": "random_eligible",
                    "sample_weight": weight,
                }
            )
        fill["lexical_hard"] += len(lex_pick)
        fill["dense_hard"] += len(dense_pick)
        fill["same_brand_other_branch"] += len(sib_pick)
        fill["random"] += len(rand_pick)
        fill["queries"] += 1
        if offset == 0 or (offset + 1) % 1000 == 0 or offset + 1 == len(train):
            print(f"  pairs {offset + 1}/{len(train)}", flush=True)

    for row in relations.itertuples(index=False):
        if row.split != "train" or row.label != "ignore":
            continue
        weight = float(weight_by_query.get(str(row.query_id), 1.0))
        pairs.append(
            {
                "query_id": str(row.query_id),
                "poi_id": str(row.poi_id),
                "label": "ignore",
                "negative_source": None,
                "source_rank": None,
                "label_reason": str(row.label_reason),
                "sample_weight": weight,
            }
        )

    table = pd.DataFrame(pairs)
    overlap = sorted(set(table["poi_id"].astype(str)) & holdout_ids) if holdout_ids else []
    if overlap:
        raise SystemExit(f"Mined pairs still contain Gold POIs: {overlap[:10]}")
    out_path = out / "training_pairs.parquet"
    pq.write_table(pa.Table.from_pandas(table, preserve_index=False), out_path, compression="zstd")

    n_train = max(fill["queries"], 1)
    mining = {
        "dataset": out.name,
        "status": "EXPERIMENTAL",
        "miner_checkpoint": MODEL_ID,
        "embedding_source": "encoded_on_device" if args.encode_corpus else str(EMB.as_posix()),
        "embeddings_sha256": None if args.encode_corpus else sha256(EMB),
        "poi_ids_sha256": None if args.encode_corpus else sha256(EMB_IDS),
        "passage_max_tokens": int(args.passage_max_tokens) if args.encode_corpus else None,
        "documents_sha256": sha256(docs_path),
        "view_sha256": sha256(view_path),
        "relation_sha256": sha256(rel_path),
        "seed": SEED,
        "pool_depth": POOL_DEPTH,
        "quota": quota,
        "exclusions": [
            "authored_positive",
            "brand_membership_needs_review",
            "same_entity_group",
            "gold_holdout_poi",
        ],
        "holdout_gold": {
            "path": holdout_dir,
            "n_ids": len(holdout_ids),
            "gold_pool_hits": gold_pool_hits,
            "pair_overlap": 0,
        },
        "note": (
            "Same-brand other branches stay eligible as hard-neg candidates. "
            "They are not expanded into positives."
        ),
        "train_queries": fill["queries"],
        "pair_rows": int(len(table)),
        "pairs_by_label": table["label"].value_counts().to_dict(),
        "negatives_by_source": table.loc[table["label"] == "negative", "negative_source"]
        .value_counts()
        .to_dict(),
        "fill_rate": {
            "lexical_hard": fill["lexical_hard"] / (n_train * quota["lexical_hard"]),
            "dense_hard": fill["dense_hard"] / (n_train * quota["dense_hard"]),
            "same_brand_other_branch": (
                fill["same_brand_other_branch"] / (n_train * quota["same_brand_other_branch"])
                if quota["same_brand_other_branch"]
                else 0.0
            ),
            "random": fill["random"] / (n_train * quota["random"]),
        },
        "outputs": {"training_pairs.parquet": sha256(out_path)},
    }
    (out / "mining_manifest.json").write_text(
        json.dumps(mining, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: mining[k] for k in ("train_queries", "pair_rows", "pairs_by_label", "fill_rate")}, indent=2))
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
