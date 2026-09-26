"""Encode versioned POI corpus passages with multilingual-e5-small (offline).

Writes:
  artifacts/embeddings/me5_small/corpus_embeddings.npy
  artifacts/embeddings/me5_small/poi_ids.parquet
  artifacts/embeddings/me5_small/manifest.json

Prefer GPU (Kaggle). CPU works but is slow for ~186k docs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import torch
import torch.nn.functional as F
from transformers import AutoModel, AutoTokenizer

MODEL_ID = "intfloat/multilingual-e5-small"
DIM = 384
PASSAGE_PREFIX = "passage: "
DEFAULT_MAX_LENGTH = 96


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def mean_pool(hidden: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    mask_f = mask.unsqueeze(-1).expand(hidden.size()).float()
    summed = torch.sum(hidden * mask_f, dim=1)
    counts = torch.clamp(mask_f.sum(dim=1), min=1e-9)
    return F.normalize(summed / counts, p=2, dim=1)


@torch.inference_mode()
def encode_passages(
    model: AutoModel,
    tokenizer: AutoTokenizer,
    texts: list[str],
    *,
    batch_size: int,
    max_length: int,
    device: torch.device,
) -> np.ndarray:
    vectors: list[np.ndarray] = []
    for start in range(0, len(texts), batch_size):
        batch = [PASSAGE_PREFIX + text for text in texts[start : start + batch_size]]
        tokens = tokenizer(
            batch,
            padding=True,
            truncation=True,
            max_length=max_length,
            return_tensors="pt",
        )
        tokens = {key: value.to(device) for key, value in tokens.items()}
        hidden = model(**tokens).last_hidden_state
        pooled = mean_pool(hidden, tokens["attention_mask"])
        vectors.append(pooled.cpu().numpy().astype(np.float32, copy=False))
        done = min(start + batch_size, len(texts))
        if done == len(texts) or done % (batch_size * 20) == 0:
            print(f"  encoded {done}/{len(texts)}", flush=True)
    return np.vstack(vectors)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--documents",
        type=Path,
        default=None,
        help="search_documents.parquet (default: data/vietnam/poi_corpus_v1/...)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory (default: artifacts/embeddings/me5_small)",
    )
    parser.add_argument("--model-id", default=MODEL_ID)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--max-length", type=int, default=DEFAULT_MAX_LENGTH)
    parser.add_argument("--device", default=None, help="cuda | cpu (default: auto)")
    args = parser.parse_args()

    root = repo_root()
    documents_path = args.documents or (
        root / "data" / "vietnam" / "poi_corpus_v1" / "search_documents.parquet"
    )
    corpus_manifest_path = documents_path.parent / "manifest.json"
    if not corpus_manifest_path.exists():
        raise SystemExit(f"Missing corpus manifest: {corpus_manifest_path}")
    corpus_manifest = json.loads(corpus_manifest_path.read_text(encoding="utf-8"))
    corpus_version = str(corpus_manifest.get("corpus_version") or "")
    if not corpus_version:
        raise SystemExit(f"Missing corpus_version in {corpus_manifest_path}")
    output_dir = args.output_dir or (root / "artifacts" / "embeddings" / "me5_small")
    output_dir.mkdir(parents=True, exist_ok=True)

    table = pq.read_table(documents_path, columns=["poi_id", "passage_context"])
    poi_ids = table.column("poi_id").to_pylist()
    passages = [str(value or "") for value in table.column("passage_context").to_pylist()]
    if len(poi_ids) != len(passages) or not poi_ids:
        raise SystemExit("search_documents.parquet is empty or malformed")

    device_name = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    device = torch.device(device_name)
    print(f"model={args.model_id} device={device} docs={len(poi_ids)}", flush=True)

    tokenizer = AutoTokenizer.from_pretrained(args.model_id)
    model = AutoModel.from_pretrained(args.model_id).to(device).eval()

    began = time.perf_counter()
    embeddings = encode_passages(
        model,
        tokenizer,
        passages,
        batch_size=args.batch_size,
        max_length=args.max_length,
        device=device,
    )
    elapsed = time.perf_counter() - began
    if embeddings.shape != (len(poi_ids), DIM):
        raise SystemExit(f"Unexpected embedding shape {embeddings.shape}")

    emb_path = output_dir / "corpus_embeddings.npy"
    ids_path = output_dir / "poi_ids.parquet"
    np.save(emb_path, embeddings)
    pq.write_table(pa.table({"poi_id": poi_ids}), ids_path)

    passage_digest = hashlib.sha256()
    for text in passages:
        passage_digest.update(text.encode("utf-8"))
        passage_digest.update(b"\0")

    manifest = {
        "model_id": args.model_id,
        "embedding_dimension": DIM,
        "row_count": len(poi_ids),
        "query_prefix": "query: ",
        "passage_prefix": PASSAGE_PREFIX,
        "max_length": args.max_length,
        "normalized": True,
        "dtype": "float32",
        "documents_path": str(documents_path.as_posix()),
        "documents_sha256": sha256_file(documents_path),
        "passage_context_sha256": passage_digest.hexdigest(),
        "embeddings_sha256": sha256_file(emb_path),
        "poi_ids_sha256": sha256_file(ids_path),
        "encode_seconds": round(elapsed, 1),
        "device": str(device),
        "corpus_version": corpus_version,
        "corpus_manifest_sha256": sha256_file(corpus_manifest_path),
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {emb_path} shape={embeddings.shape} in {elapsed:.1f}s", flush=True)
    print(f"wrote {ids_path}", flush=True)
    print(f"wrote {output_dir / 'manifest.json'}", flush=True)


if __name__ == "__main__":
    main()
