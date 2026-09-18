#!/usr/bin/env python3
"""Kaggle GPU Round-1b: gold char-prefix FHC/SHC/PrefixAUC.

No local embedding upload. Uses only `vn-poi-gold-stage1-w1` already on Kaggle:
  - expand NFC grapheme prefixes from query_variants_v1.csv
  - BM25 + re-encode corpus/prefixes for mE5 + Bekko A8M/A25M on GPU
"""
from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import time
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

os.environ.setdefault("TORCHDYNAMO_DISABLE", "1")
os.environ.setdefault("TORCH_COMPILE_DISABLE", "1")

K_LIST = (1, 5, 10)
SHC_W = 3
BRANCH_K = max(K_LIST)
OUT = Path("/kaggle/working/gold_stage1_prefix_char")

DENSE = [
    ("dense_me5_exact", "intfloat/multilingual-e5-small", "query: ", "passage: ", 128),
    ("dense_bekko_a8m_exact", "hotchpotch/bekko-embedding-v1-a8m", "", "", 128),
    ("dense_bekko_a25m_exact", "hotchpotch/bekko-embedding-v1-a25m", "", "", 128),
]


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def resolve_data() -> Path:
    preferred = Path("/kaggle/input/vn-poi-gold-stage1-w1")
    if (preferred / "query_variants_v1.csv").exists():
        return preferred
    hits = sorted(Path("/kaggle/input").rglob("query_variants_v1.csv"))
    if hits:
        return hits[0].parent
    raise FileNotFoundError("query_variants_v1.csv not under /kaggle/input")


def grapheme_clusters(text: str) -> list[str]:
    text = unicodedata.normalize("NFC", str(text or ""))
    out: list[str] = []
    for ch in text:
        if out and unicodedata.combining(ch):
            out[-1] += ch
        else:
            out.append(ch)
    return out


def parse_acceptable(raw) -> list[str]:
    if isinstance(raw, (list, tuple, np.ndarray)):
        return [str(x) for x in list(raw)]
    s = str(raw or "").strip()
    if not s:
        return []
    if s.startswith("["):
        return [str(x) for x in json.loads(s)]
    return [x for x in s.split("|") if x]


def expand_char_prefixes(sessions: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for row in sessions.itertuples(index=False):
        chars = grapheme_clusters(row.query_text)
        if not chars:
            continue
        acceptable = parse_acceptable(getattr(row, "acceptable_poi_ids", None))
        if not acceptable:
            acceptable = [str(row.intended_poi_id)]
        for n in range(1, len(chars) + 1):
            prefix = "".join(chars[:n])
            if not prefix.strip():
                continue
            rows.append(
                {
                    "variant_id": row.variant_id,
                    "case_id": row.case_id,
                    "query_variant_family": row.query_variant_family,
                    "primary_sampling_stratum": row.primary_sampling_stratum,
                    "intended_poi_id": str(row.intended_poi_id),
                    "acceptable_poi_ids": "|".join(acceptable),
                    "prefix_text": prefix,
                    "prefix_index": n,
                    "full_unit_count": len(chars),
                    "is_full_query": n == len(chars),
                }
            )
    return pd.DataFrame(rows)


def best_rank(top_ids: list[str], acceptable: set[str]) -> int | None:
    for i, pid in enumerate(top_ids, start=1):
        if str(pid) in acceptable:
            return i
    return None


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").replace("đ", "d").replace("Đ", "D")
    return " ".join(
        "".join(ch for ch in unicodedata.normalize("NFD", text) if not unicodedata.combining(ch))
        .casefold()
        .split()
    )


def tokenize(text: str) -> list[str]:
    return [t for t in fold(text).split() if t]


def mean_pool(h, m):
    import torch

    mask = m.unsqueeze(-1).expand(h.size()).float()
    return torch.sum(h * mask, dim=1) / torch.clamp(mask.sum(dim=1), min=1e-9)


def encode_texts(model, tok, texts, prefix, max_len, bs, device):
    import torch
    import torch.nn.functional as functional

    parts = []
    model.eval()
    with torch.no_grad():
        for i in range(0, len(texts), bs):
            batch = [prefix + t for t in texts[i : i + bs]]
            x = tok(batch, padding=True, truncation=True, max_length=max_len, return_tensors="pt")
            x = {k: v.to(device) for k, v in x.items()}
            x.pop("token_type_ids", None)
            v = functional.normalize(mean_pool(model(**x).last_hidden_state, x["attention_mask"]), p=2, dim=1)
            parts.append(v.cpu().numpy().astype(np.float32))
            done = min(i + bs, len(texts))
            if i == 0 or done % (bs * 20) == 0 or done == len(texts):
                print(f"  encoded {done}/{len(texts)}", flush=True)
    return np.concatenate(parts)


def exact_topk(q, corpus, ids, top_k, chunk=64):
    out = []
    for i in range(0, len(q), chunk):
        scores = q[i : i + chunk] @ corpus.T
        for row in scores:
            k = min(top_k, len(row))
            cand = np.argpartition(-row, k - 1)[:k]
            cand = cand[np.lexsort((cand, -row[cand]))]
            out.append([ids[j] for j in cand])
    return out


def session_metrics(ranks: list[int | None]) -> dict:
    t_q = len(ranks)
    out: dict[str, Any] = {"T_q": t_q, "fhc": {}, "shc": {}, "prefix_auc": {}}
    for k in K_LIST:
        hits = [r is not None and r <= k for r in ranks]
        fhc = next((t + 1 for t, h in enumerate(hits) if h), None)
        out["fhc"][k] = {"found": fhc is not None, "value": fhc}
        shc = None
        for t0 in range(t_q):
            if all(hits[s] for s in range(t0, min(t0 + SHC_W, t_q))):
                shc = t0 + 1
                break
        out["shc"][k] = {"found": shc is not None, "value": shc, "w": SHC_W}
        out["prefix_auc"][k] = sum(1 for h in hits if h) / t_q if t_q else 0.0
    return out


def summarize(prefix_df: pd.DataFrame, ranks: list[int | None]) -> tuple[dict, list[dict]]:
    by_vid: dict[str, list] = defaultdict(list)
    rows = []
    for row, rank in zip(prefix_df.itertuples(index=False), ranks):
        rec = {
            "variant_id": row.variant_id,
            "case_id": row.case_id,
            "query_variant_family": row.query_variant_family,
            "primary_sampling_stratum": row.primary_sampling_stratum,
            "prefix_index": int(row.prefix_index),
            "full_unit_count": int(row.full_unit_count),
            "is_full_query": bool(row.is_full_query),
            "rank": rank,
        }
        rows.append(rec)
        by_vid[row.variant_id].append(rec)

    variants = {}
    for vid, items in by_vid.items():
        items = sorted(items, key=lambda x: x["prefix_index"])
        m = session_metrics([x["rank"] for x in items])
        m["query_variant_family"] = items[0]["query_variant_family"]
        m["case_id"] = items[0]["case_id"]
        m["primary_sampling_stratum"] = items[0]["primary_sampling_stratum"]
        variants[vid] = m

    n = len(variants)

    def agg(metric, k):
        vals, miss = [], 0
        for info in variants.values():
            cell = info[metric][k]
            if not cell["found"]:
                miss += 1
            else:
                vals.append(cell["value"])
        arr = np.asarray(vals, dtype=np.float64) if vals else np.asarray([], dtype=np.float64)
        return {
            "hit_rate": (n - miss) / n if n else 0.0,
            "n_found": n - miss,
            "n_miss": miss,
            "mean_conditional": float(arr.mean()) if len(arr) else None,
            "p50_conditional": float(np.quantile(arr, 0.5)) if len(arr) else None,
        }

    summary: dict[str, Any] = {
        "n_variants": n,
        "n_prefixes": len(rows),
        "prefix_unit": "char_grapheme",
        "shc_window": SHC_W,
        "k_list": list(K_LIST),
        "fhc": {},
        "shc": {},
        "prefix_auc": {},
        "by_family": {},
    }
    for k in K_LIST:
        summary["fhc"][f"@{k}"] = agg("fhc", k)
        summary["shc"][f"@{k}"] = agg("shc", k)
        aucs = [info["prefix_auc"][k] for info in variants.values()]
        arr = np.asarray(aucs, dtype=np.float64)
        summary["prefix_auc"][f"@{k}"] = {
            "mean": float(arr.mean()) if len(arr) else 0.0,
            "p50": float(np.quantile(arr, 0.5)) if len(arr) else 0.0,
        }

    by_f: dict[str, list] = defaultdict(list)
    for info in variants.values():
        by_f[info["query_variant_family"]].append(info)
    for fam, items in by_f.items():
        nn = len(items)
        summary["by_family"][fam] = {
            "n": nn,
            **{f"FHC-char-HitRate@{k}": sum(1 for x in items if x["fhc"][k]["found"]) / nn for k in K_LIST},
            **{
                f"PrefixAUC-char@{k}_mean": float(np.mean([x["prefix_auc"][k] for x in items]))
                for k in K_LIST
            },
        }
    return summary, rows


def run_bm25(prefix_df: pd.DataFrame, passages: list[str], ids: list[str]) -> list[int | None]:
    try:
        from rank_bm25 import BM25Okapi
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "rank_bm25"], check=True)
        from rank_bm25 import BM25Okapi

    print("building BM25 …", flush=True)
    t0 = time.time()
    bm25 = BM25Okapi([tokenize(t) for t in passages])
    print(f"BM25 ready in {time.time() - t0:.1f}s; scoring {len(prefix_df)} prefixes", flush=True)
    ranks: list[int | None] = []
    t1 = time.time()
    for i, row in enumerate(prefix_df.itertuples(index=False), start=1):
        scores = np.asarray(bm25.get_scores(tokenize(row.prefix_text)), dtype=np.float64)
        k = min(BRANCH_K, len(scores))
        idx = np.argpartition(scores, -k)[-k:]
        idx = idx[np.argsort(scores[idx])[::-1]]
        top = [ids[j] for j in idx]
        ranks.append(best_rank(top, set(parse_acceptable(row.acceptable_poi_ids))))
        if i % 2000 == 0 or i == len(prefix_df):
            print(f"  bm25 {i}/{len(prefix_df)} elapsed={time.time() - t1:.1f}s", flush=True)
    return ranks


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    data = resolve_data()
    docs = pd.read_parquet(data / "search_documents.parquet")
    sessions = pd.read_csv(data / "query_variants_v1.csv")
    ids = docs["poi_id"].astype(str).tolist()
    passages = docs["passage_context"].fillna("").astype(str).tolist()

    prefix_df = expand_char_prefixes(sessions)
    prefix_df.to_parquet(OUT / "char_prefixes.parquet", index=False)
    print(f"expanded {len(prefix_df)} char prefixes from {sessions.variant_id.nunique()} variants", flush=True)

    report: dict[str, Any] = {
        "protocol": "gold_stage1_v1_round1b_prefix_char",
        "profiles": {},
        "runtime": {"python": platform.python_version()},
    }
    gate: list[dict] = []

    print("=== lexical_bm25 ===", flush=True)
    bm25_ranks = run_bm25(prefix_df, passages, ids)
    bm25_sum, bm25_rows = summarize(prefix_df, bm25_ranks)
    report["profiles"]["lexical_bm25"] = bm25_sum
    with (OUT / "prefix_ranks_lexical_bm25.jsonl").open("w", encoding="utf-8") as f:
        for r in bm25_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    gate.append(
        {
            "profile": "lexical_bm25",
            **{f"FHC-char-HitRate@{k}": bm25_sum["fhc"][f"@{k}"]["hit_rate"] for k in K_LIST},
            **{f"PrefixAUC-char@{k}": bm25_sum["prefix_auc"][f"@{k}"]["mean"] for k in K_LIST},
        }
    )
    write_json(OUT / "summary_partial.json", report)
    print(
        f"bm25 FHC@5 hit={bm25_sum['fhc']['@5']['hit_rate']:.3f} "
        f"PrefixAUC@5={bm25_sum['prefix_auc']['@5']['mean']:.3f}",
        flush=True,
    )

    import torch
    from transformers import AutoModel, AutoTokenizer

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    report["runtime"]["device"] = str(device)
    report["runtime"]["torch"] = torch.__version__
    print(f"device={device}", flush=True)

    prefix_texts = prefix_df["prefix_text"].astype(str).tolist()
    acceptables = [set(parse_acceptable(x)) for x in prefix_df["acceptable_poi_ids"].tolist()]

    for profile, hf_id, q_prefix, p_prefix, max_len in DENSE:
        print(f"=== {profile} ({hf_id}) ===", flush=True)
        try:
            tok = AutoTokenizer.from_pretrained(hf_id, trust_remote_code=True)
            model = AutoModel.from_pretrained(hf_id, trust_remote_code=True).to(device)
            print("encoding corpus …", flush=True)
            t0 = time.time()
            corpus = encode_texts(model, tok, passages, p_prefix, max_len, 48, device)
            corp_s = time.time() - t0
            print("encoding prefixes …", flush=True)
            t1 = time.time()
            qvec = encode_texts(model, tok, prefix_texts, q_prefix, max_len, 64, device)
            enc_s = time.time() - t1
            del model, tok
            if device.type == "cuda":
                torch.cuda.empty_cache()

            t2 = time.time()
            tops = exact_topk(qvec, corpus, ids, BRANCH_K, chunk=64)
            ret_s = time.time() - t2
            ranks = [best_rank(top, acc) for top, acc in zip(tops, acceptables)]
            summary, rows = summarize(prefix_df, ranks)
            summary["meta"] = {
                "hf_id": hf_id,
                "encode_corpus_s": round(corp_s, 1),
                "encode_prefix_s": round(enc_s, 1),
                "retrieve_s": round(ret_s, 1),
                "dim": int(corpus.shape[1]),
            }
            report["profiles"][profile] = summary
            with (OUT / f"prefix_ranks_{profile}.jsonl").open("w", encoding="utf-8") as f:
                for r in rows:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            gate.append(
                {
                    "profile": profile,
                    **{f"FHC-char-HitRate@{k}": summary["fhc"][f"@{k}"]["hit_rate"] for k in K_LIST},
                    **{f"PrefixAUC-char@{k}": summary["prefix_auc"][f"@{k}"]["mean"] for k in K_LIST},
                    "encode_corpus_s": summary["meta"]["encode_corpus_s"],
                    "encode_prefix_s": summary["meta"]["encode_prefix_s"],
                }
            )
            print(
                f"{profile} FHC@5 hit={summary['fhc']['@5']['hit_rate']:.3f} "
                f"PrefixAUC@5={summary['prefix_auc']['@5']['mean']:.3f} "
                f"corpus={corp_s:.0f}s prefix={enc_s:.0f}s",
                flush=True,
            )
            del corpus, qvec
            if device.type == "cuda":
                torch.cuda.empty_cache()
        except Exception as exc:  # noqa: BLE001
            print(f"FAILED {profile}: {exc}", flush=True)
            report["profiles"][profile] = {"error": str(exc)}
        write_json(OUT / "summary_partial.json", report)

    write_json(OUT / "summary.json", report)
    write_json(OUT / "gate_table_prefix_char.json", gate)
    print("DONE", OUT, flush=True)


if __name__ == "__main__":
    main()
