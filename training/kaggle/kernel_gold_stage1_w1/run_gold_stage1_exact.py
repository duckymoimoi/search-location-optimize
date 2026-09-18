#!/usr/bin/env python3
"""Kaggle GPU: gold_stage1_v1 Round-1 — BM25 + 6 dense exact (D=1000).

No ANN. No hybrid RRF in this round.
BM25 = rank_bm25.BM25Okapi defaults (k1=1.5, b=0.75) — diagnostic lexical floor.
"""
from __future__ import annotations

import argparse
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

BRANCH_K = 1000
RECALL_KS = (100, 500, 1000)
DIAG_KS = (1, 5, 10, 50)

os.environ.setdefault("TORCHDYNAMO_DISABLE", "1")
os.environ.setdefault("TORCH_COMPILE_DISABLE", "1")

# Round-1b remaining only (BM25 + me5 + bekko*2 + halong already done on prior run)
MODELS: list[tuple[str, str, str, str, int]] = [
    ("dense_bge_m3_exact", "BAAI/bge-m3", "", "", 128),
    ("dense_gte_mbase_exact", "Alibaba-NLP/gte-multilingual-base", "", "", 128),
]


def disable_torch_compile() -> None:
    os.environ["TORCHDYNAMO_DISABLE"] = "1"
    os.environ["TORCH_COMPILE_DISABLE"] = "1"
    try:
        import torch._dynamo

        torch._dynamo.config.disable = True
    except Exception:
        pass


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").replace("đ", "d").replace("Đ", "D")
    return " ".join(
        "".join(ch for ch in unicodedata.normalize("NFD", text) if not unicodedata.combining(ch))
        .casefold()
        .split()
    )


def tokenize(text: str) -> list[str]:
    return [t for t in fold(text).split() if t]


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def resolve_input(preferred: Path) -> Path:
    if (preferred / "search_documents.parquet").exists():
        return preferred
    kaggle_input = Path("/kaggle/input")
    if kaggle_input.exists():
        matches = sorted(kaggle_input.rglob("search_documents.parquet"))
        if matches:
            return matches[0].parent
    raise FileNotFoundError(f"search_documents.parquet not under {preferred}")


def ensure_kaggle_gpu_compatibility() -> None:
    if not Path("/kaggle").exists():
        return
    probe = subprocess.run(
        ["nvidia-smi", "--query-gpu=compute_cap", "--format=csv,noheader"],
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.stdout.strip().startswith("6.0"):
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--quiet",
                "--force-reinstall",
                "torch==2.7.1",
                "--index-url",
                "https://download.pytorch.org/whl/cu126",
            ],
            check=True,
        )
        subprocess.run(
            [sys.executable, "-m", "pip", "uninstall", "-y", "torchvision", "torchaudio"],
            check=False,
        )


def mean_pool(last_hidden_state: Any, attention_mask: Any) -> Any:
    import torch

    mask = attention_mask.unsqueeze(-1).expand(last_hidden_state.size()).float()
    return torch.sum(last_hidden_state * mask, dim=1) / torch.clamp(mask.sum(dim=1), min=1e-9)


def encode_sentence_transformers(
    model_id: str,
    texts: list[str],
    prefix: str,
    max_length: int,
    batch_size: int,
    device: Any,
) -> tuple[np.ndarray, float]:
    """Prefer ST encode path for GTE/BGE — more stable than raw AutoModel+fp16 on Kaggle."""
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", "sentence-transformers"],
            check=True,
        )
        from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(model_id, device=str(device), trust_remote_code=True)
    model.max_seq_length = max_length
    payloads = [prefix + t for t in texts]
    t0 = time.time()
    vec = model.encode(
        payloads,
        batch_size=batch_size,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    elapsed = time.time() - t0
    del model
    if str(device).startswith("cuda"):
        import torch

        torch.cuda.empty_cache()
    return np.asarray(vec, dtype=np.float32), elapsed


def encode_transformers(
    model: Any,
    tokenizer: Any,
    texts: list[str],
    prefix: str,
    max_length: int,
    batch_size: int,
) -> tuple[np.ndarray, float]:
    import torch
    import torch.nn.functional as functional

    parts = []
    model.eval()
    device = next(model.parameters()).device
    t0 = time.time()
    with torch.no_grad():
        for start in range(0, len(texts), batch_size):
            batch = [prefix + t for t in texts[start : start + batch_size]]
            tokens = tokenizer(
                batch,
                padding=True,
                truncation=True,
                max_length=max_length,
                return_tensors="pt",
            )
            tokens = {k: v.to(device) for k, v in tokens.items()}
            # Drop token_type_ids — breaks some GTE / BGE checkpoints
            tokens.pop("token_type_ids", None)
            out = model(**tokens)
            hidden = getattr(out, "last_hidden_state", None)
            if hidden is None:
                hidden = out[0] if isinstance(out, (tuple, list)) else out
            vec = functional.normalize(mean_pool(hidden, tokens["attention_mask"]), p=2, dim=1)
            parts.append(vec.cpu().numpy().astype(np.float32, copy=False))
            done = min(start + batch_size, len(texts))
            if start == 0 or done % (batch_size * 20) == 0 or done == len(texts):
                print(f"  encoded {done}/{len(texts)}", flush=True)
    elapsed = time.time() - t0
    return np.concatenate(parts), elapsed


def exact_topk(
    queries: np.ndarray, corpus: np.ndarray, ids: list[str], top_k: int, chunk: int
) -> list[list[str]]:
    out: list[list[str]] = []
    for start in range(0, len(queries), chunk):
        scores = queries[start : start + chunk] @ corpus.T
        for row_scores in scores:
            k = min(top_k, len(row_scores))
            cand = np.argpartition(-row_scores, k - 1)[:k]
            order = np.lexsort((cand, -row_scores[cand]))
            cand = cand[order]
            out.append([ids[i] for i in cand])
    return out


def parse_acceptable(raw) -> list[str]:
    if isinstance(raw, (list, tuple)):
        return [str(x) for x in raw]
    s = str(raw or "").strip()
    if not s:
        return []
    if s.startswith("["):
        return [str(x) for x in json.loads(s)]
    return [x for x in s.split("|") if x]


def best_rank(top_ids: list[str], acceptable: set[str], depth: int = BRANCH_K) -> int:
    for i, pid in enumerate(top_ids, start=1):
        if str(pid) in acceptable:
            return i if i <= depth else depth + 1
    return depth + 1


def k_at_recall(ranks: list[int], rate: float, depth: int = BRANCH_K) -> int | None:
    n = len(ranks)
    if n == 0:
        return None
    need = int(np.ceil(rate * n))
    ordered = sorted(ranks)
    if need > n:
        return None
    k = ordered[need - 1]
    return int(k) if k <= depth else None


def summarize_rows(rows: list[dict], label: str) -> dict:
    ranks = [r["best_rank"] for r in rows]
    n = len(ranks)
    out: dict[str, Any] = {"n": n, "label": label, "recall": {}, "diagnostic": {}, "k_at_r": {}}
    for k in RECALL_KS:
        out["recall"][f"Recall@{k}"] = sum(1 for r in ranks if r <= k) / n if n else 0.0
    for k in DIAG_KS:
        out["diagnostic"][f"SR@{k}"] = sum(1 for r in ranks if r <= k) / n if n else 0.0
    out["diagnostic"]["MRR@10"] = (
        sum(1.0 / r for r in ranks if r <= 10) / n if n else 0.0
    )
    out["k_at_r"]["K@95"] = k_at_recall(ranks, 0.95)
    out["k_at_r"]["K@98"] = k_at_recall(ranks, 0.98)
    return out


def write_run_jsonl(
    path: Path,
    sessions: pd.DataFrame,
    ranked_lists: list[list[str]],
    profile: str,
) -> list[dict]:
    rows_out = []
    with path.open("w", encoding="utf-8") as f:
        for row, top in zip(sessions.itertuples(index=False), ranked_lists):
            acceptable = set(parse_acceptable(row.acceptable_poi_ids))
            if not acceptable:
                acceptable = {str(row.intended_poi_id)}
            br = best_rank(top, acceptable)
            intended = str(row.intended_poi_id)
            intended_rank = None
            try:
                intended_rank = top.index(intended) + 1
            except ValueError:
                intended_rank = None
            rec = {
                "variant_id": row.variant_id,
                "case_id": row.case_id,
                "query_text": row.query_text,
                "query_variant_family": row.query_variant_family,
                "variant_operator": row.variant_operator,
                "primary_sampling_stratum": row.primary_sampling_stratum,
                "intended_poi_id": intended,
                "acceptable_poi_ids": list(acceptable),
                "rank": intended_rank,
                "best_rank": br,
                "top_ids": top[:BRANCH_K],
                "profile": profile,
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            rows_out.append(rec)
    return rows_out


def profile_report(rows: list[dict]) -> dict:
    overall = summarize_rows(rows, "overall")
    by_f: dict[str, list] = defaultdict(list)
    by_s: dict[str, list] = defaultdict(list)
    for r in rows:
        by_f[str(r["query_variant_family"])].append(r)
        by_s[str(r["primary_sampling_stratum"])].append(r)
    return {
        "overall": overall,
        "by_family": {k: summarize_rows(v, k) for k, v in by_f.items()},
        "by_stratum": {k: summarize_rows(v, k) for k, v in by_s.items()},
    }


def run_bm25(
    sessions: pd.DataFrame, passages: list[str], ids: list[str], out_dir: Path
) -> list[dict]:
    try:
        from rank_bm25 import BM25Okapi
    except ImportError:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", "rank_bm25"], check=True
        )
        from rank_bm25 import BM25Okapi

    print("building BM25Okapi (default k1/b) …", flush=True)
    t0 = time.time()
    bm25 = BM25Okapi([tokenize(t) for t in passages])
    print(f"BM25 index ready in {time.time() - t0:.1f}s", flush=True)
    ranked: list[list[str]] = []
    t1 = time.time()
    for i, row in enumerate(sessions.itertuples(index=False), start=1):
        scores = np.asarray(bm25.get_scores(tokenize(str(row.query_text))), dtype=np.float64)
        k = min(BRANCH_K, len(scores))
        idx = np.argpartition(scores, -k)[-k:]
        idx = idx[np.argsort(scores[idx])[::-1]]
        ranked.append([ids[j] for j in idx])
        if i % 200 == 0 or i == len(sessions):
            print(f"  bm25 {i}/{len(sessions)}", flush=True)
    print(f"BM25 retrieve done in {time.time() - t1:.1f}s", flush=True)
    rows = write_run_jsonl(out_dir / "run_lexical_bm25.jsonl", sessions, ranked, "lexical_bm25")
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=Path("/kaggle/input/vn-poi-gold-stage1-w1"))
    ap.add_argument("--output", type=Path, default=Path("/kaggle/working/gold_stage1_w1"))
    ap.add_argument("--batch-size", type=int, default=48)
    ap.add_argument("--exact-chunk", type=int, default=16)
    ap.add_argument(
        "--models",
        nargs="*",
        default=None,
        help="Optional subset of profile keys, e.g. dense_me5_exact dense_bekko_a8m_exact",
    )
    ap.add_argument("--skip-bm25", action="store_true")
    args = ap.parse_args()

    data_dir = resolve_input(args.data)
    args.output.mkdir(parents=True, exist_ok=True)

    docs = pd.read_parquet(data_dir / "search_documents.parquet")
    sessions = pd.read_csv(data_dir / "query_variants_v1.csv")
    poi_ids = docs["poi_id"].astype(str).tolist()
    passages = docs["passage_context"].fillna("").astype(str).tolist()
    print(f"corpus={len(poi_ids)} queries={len(sessions)} data={data_dir}", flush=True)

    pd.DataFrame({"row_index": range(len(poi_ids)), "poi_id": poi_ids}).to_parquet(
        args.output / "poi_ids.parquet", index=False
    )

    summary: dict[str, Any] = {
        "protocol": "gold_stage1_v1_round1",
        "depth": BRANCH_K,
        "bm25": "rank_bm25.BM25Okapi defaults (untuned lexical floor)",
        "profiles": {},
        "runtime": {},
    }

    if not args.skip_bm25:
        bm25_rows = run_bm25(sessions, passages, poi_ids, args.output)
        summary["profiles"]["lexical_bm25"] = profile_report(bm25_rows)
        o = summary["profiles"]["lexical_bm25"]["overall"]
        print(
            f"lexical_bm25 Recall@1000={o['recall']['Recall@1000']:.3f} "
            f"K@95={o['k_at_r']['K@95']} MRR@10={o['diagnostic']['MRR@10']:.3f}",
            flush=True,
        )
        write_json(args.output / "summary_partial.json", summary)

    ensure_kaggle_gpu_compatibility()
    disable_torch_compile()
    import torch
    import transformers
    from transformers import AutoModel, AutoTokenizer

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    torch.set_num_threads(max(1, min(8, os.cpu_count() or 1)))
    print(f"device={device} torch={torch.__version__}", flush=True)
    summary["runtime"] = {
        "device": str(device),
        "torch": torch.__version__,
        "transformers": transformers.__version__,
        "python": platform.python_version(),
    }

    selected = MODELS
    if args.models:
        want = set(args.models)
        selected = [m for m in MODELS if m[0] in want]

    for profile, hf_id, q_prefix, p_prefix, max_len in selected:
        run_path = args.output / f"run_{profile}.jsonl"
        if run_path.exists() and run_path.stat().st_size > 0:
            print(f"=== skip {profile} (found {run_path.name}) ===", flush=True)
            continue
        print(f"=== {profile} ({hf_id}) ===", flush=True)
        model = None
        tokenizer = None
        corp = None
        qvec = None
        try:
            heavy = profile in {"dense_gte_mbase_exact", "dense_bge_m3_exact", "dense_halong_exact"}
            batch = 8 if heavy else args.batch_size
            use_st = profile in {"dense_gte_mbase_exact", "dense_bge_m3_exact"}

            print(f"encoding passages (batch={batch}, st={use_st}) …", flush=True)
            if use_st:
                corp, corp_s = encode_sentence_transformers(
                    hf_id, passages, p_prefix, max_len, batch, device
                )
            else:
                load_kw: dict[str, Any] = {"trust_remote_code": True}
                tokenizer = AutoTokenizer.from_pretrained(hf_id, trust_remote_code=True)
                model = AutoModel.from_pretrained(hf_id, **load_kw).to(device)
                model.eval()
                corp, corp_s = encode_transformers(
                    model, tokenizer, passages, p_prefix, max_len, batch
                )
            np.save(args.output / f"embedding_{profile}.npy", corp)

            print("encoding queries …", flush=True)
            qtexts = sessions["query_text"].astype(str).tolist()
            if use_st:
                qvec, q_s = encode_sentence_transformers(
                    hf_id, qtexts, q_prefix, max_len, batch, device
                )
            else:
                qvec, q_s = encode_transformers(
                    model, tokenizer, qtexts, q_prefix, max_len, batch
                )
            np.save(args.output / f"query_embedding_{profile}.npy", qvec)
            per_q_ms = (q_s / max(len(qtexts), 1)) * 1000.0

            del model, tokenizer
            model = tokenizer = None
            if device.type == "cuda":
                torch.cuda.empty_cache()

            print("exact top-1000 …", flush=True)
            t0 = time.time()
            ranked = exact_topk(qvec, corp, poi_ids, BRANCH_K, args.exact_chunk)
            retrieve_s = time.time() - t0
            rows = write_run_jsonl(
                args.output / f"run_{profile}.jsonl", sessions, ranked, profile
            )
            rep = profile_report(rows)
            rep["meta"] = {
                "hf_id": hf_id,
                "query_prefix": q_prefix,
                "passage_prefix": p_prefix,
                "dim": int(corp.shape[1]),
                "encode_corpus_s": round(corp_s, 1),
                "encode_queries_s": round(q_s, 1),
                "encode_query_ms_mean": round(per_q_ms, 2),
                "retrieve_s": round(retrieve_s, 1),
                "batch_size": batch,
                "encode_backend": "sentence_transformers" if use_st else "transformers",
            }
            summary["profiles"][profile] = rep
            o = rep["overall"]
            print(
                f"{profile} R@1000={o['recall']['Recall@1000']:.3f} "
                f"K@95={o['k_at_r']['K@95']} encode_q_ms={per_q_ms:.1f}",
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"FAILED {profile} ({hf_id}): {exc}", flush=True)
            summary["profiles"][profile] = {"error": str(exc)}
            # CUDA device-side assert poisons the context — abort further GPU models
            if "device-side assert" in str(exc).lower() or "cuda error" in str(exc).lower():
                print("CUDA poisoned — stopping remaining dense profiles", flush=True)
                write_json(args.output / "summary_partial.json", summary)
                break
        finally:
            write_json(args.output / "summary_partial.json", summary)
            del model, tokenizer, corp, qvec
            if device.type == "cuda":
                try:
                    torch.cuda.empty_cache()
                except Exception:
                    pass

    write_json(args.output / "summary.json", summary)
    # compact gate table
    gate = []
    for name, prof in summary["profiles"].items():
        if "overall" not in prof:
            gate.append({"profile": name, "error": prof.get("error")})
            continue
        o = prof["overall"]
        gate.append(
            {
                "profile": name,
                "Recall@100": o["recall"]["Recall@100"],
                "Recall@500": o["recall"]["Recall@500"],
                "Recall@1000": o["recall"]["Recall@1000"],
                "K@95": o["k_at_r"]["K@95"],
                "K@98": o["k_at_r"]["K@98"],
                "MRR@10": o["diagnostic"]["MRR@10"],
                "encode_query_ms_mean": (prof.get("meta") or {}).get("encode_query_ms_mean"),
                "dim": (prof.get("meta") or {}).get("dim"),
            }
        )
    write_json(args.output / "gate_table.json", gate)
    print("DONE", args.output, flush=True)


if __name__ == "__main__":
    # Round-1b: MODELS list is BGE+GTE only; always skip BM25 on Kaggle for this push.
    if Path("/kaggle").exists() and "--skip-bm25" not in sys.argv:
        sys.argv.append("--skip-bm25")
    main()
