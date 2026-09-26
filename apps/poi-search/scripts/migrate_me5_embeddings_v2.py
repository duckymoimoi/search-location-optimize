"""Reuse unchanged v1 passages and encode changed v2 passages with the live API model.

Requires the running vn-poi-stage1-api container, which already has the exact
multilingual-e5-small weights cached. Checks sample vectors against v1 before
writing the new embedding matrix.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[3]
OLD = ROOT / "data/vietnam/poi_corpus_v1/search_documents.parquet"
NEW = ROOT / "data/vietnam/poi_corpus_v2/search_documents.parquet"
SOURCE = ROOT / "artifacts/embeddings/me5_small"
TARGET = ROOT / "artifacts/embeddings/me5_small_v2"
MODEL = "intfloat/multilingual-e5-small"

ENCODER = r"""
import json, sys
import torch
import torch.nn.functional as F
from transformers import AutoModel, AutoTokenizer
payload = json.load(sys.stdin)
model_id = 'intfloat/multilingual-e5-small'
tokenizer = AutoTokenizer.from_pretrained(model_id, local_files_only=True)
model = AutoModel.from_pretrained(model_id, local_files_only=True).eval()
torch.set_num_threads(4)
result = []
with torch.inference_mode():
    for start in range(0, len(payload), 16):
        texts = ['passage: ' + text for text in payload[start:start + 16]]
        tokens = tokenizer(texts, padding=True, truncation=True, max_length=128, return_tensors='pt')
        hidden = model(**tokens).last_hidden_state
        mask = tokens['attention_mask'].unsqueeze(-1).expand(hidden.size()).float()
        pooled = F.normalize((hidden * mask).sum(1) / mask.sum(1).clamp(min=1e-9), p=2, dim=1)
        result.extend(pooled.tolist())
json.dump(result, sys.stdout)
"""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_documents(path: Path) -> tuple[list[str], list[str]]:
    table = pq.read_table(path, columns=["poi_id", "passage_context"])
    return ([str(x) for x in table["poi_id"].to_pylist()],
            [str(x or "") for x in table["passage_context"].to_pylist()])


def main() -> None:
    old_ids, old_passages = read_documents(OLD)
    new_ids, new_passages = read_documents(NEW)
    source_ids = [str(x) for x in pq.read_table(SOURCE / "poi_ids.parquet")["poi_id"].to_pylist()]
    source_vectors = np.load(SOURCE / "corpus_embeddings.npy", mmap_mode="r")
    if old_ids != source_ids or source_vectors.shape != (len(old_ids), 384):
        raise SystemExit("v1 embedding ID/order/shape mismatch")
    old_by_id = {poi_id: i for i, poi_id in enumerate(old_ids)}
    if any(poi_id not in old_by_id for poi_id in new_ids):
        raise SystemExit("v2 contains IDs with no v1 vector; full encoding required")
    changed = [i for i, poi_id in enumerate(new_ids)
               if new_passages[i] != old_passages[old_by_id[poi_id]]]
    unchanged = [i for i, poi_id in enumerate(new_ids)
                 if new_passages[i] == old_passages[old_by_id[poi_id]]]
    sample = [unchanged[round(j * (len(unchanged) - 1) / 15)] for j in range(16)]
    request_indices = sample + changed
    request_texts = [new_passages[i] for i in request_indices]
    run = subprocess.run(
        ["docker", "exec", "-i", "vn-poi-stage1-api", "python", "-c", ENCODER],
        input=json.dumps(request_texts, ensure_ascii=True), text=True, encoding="utf-8",
        capture_output=True, check=True,
    )
    encoded = np.asarray(json.loads(run.stdout), dtype=np.float32)
    if encoded.shape != (len(request_indices), 384):
        raise SystemExit(f"Unexpected encoder result: {encoded.shape}")
    cosines = [float(np.dot(encoded[j], source_vectors[old_by_id[new_ids[i]]]))
               for j, i in enumerate(sample)]
    print(f"v1 vector reproduction: min_cosine={min(cosines):.6f} max_cosine={max(cosines):.6f}")
    if min(cosines) < 0.999:
        raise SystemExit("Live encoder does not reproduce v1 vectors; aborting migration")

    vectors = np.empty((len(new_ids), 384), dtype=np.float32)
    for i, poi_id in enumerate(new_ids):
        vectors[i] = source_vectors[old_by_id[poi_id]]
    for j, i in enumerate(changed, start=len(sample)):
        vectors[i] = encoded[j]
    TARGET.mkdir(parents=True, exist_ok=True)
    emb_path = TARGET / "corpus_embeddings.npy"
    ids_path = TARGET / "poi_ids.parquet"
    np.save(emb_path, vectors)
    pq.write_table(pa.table({"poi_id": new_ids}), ids_path)
    manifest = {
        "model_id": MODEL,
        "corpus_version": "vn-poi-core-v2-address-name-dedup50",
        "row_count": len(new_ids),
        "embedding_dimension": 384,
        "dtype": "float32",
        "normalized": True,
        "passage_prefix": "passage: ",
        "max_length": 128,
        "reused_vectors": len(unchanged),
        "reencoded_vectors": len(changed),
        "v1_reproduction_min_cosine": min(cosines),
        "source_embeddings_sha256": sha256(SOURCE / "corpus_embeddings.npy"),
        "source_documents_sha256": sha256(OLD),
        "documents_sha256": sha256(NEW),
        "embeddings_sha256": sha256(emb_path),
        "poi_ids_sha256": sha256(ids_path),
    }
    (TARGET / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(new_ids)} vectors; reused {len(unchanged)}, reencoded {len(changed)}")


if __name__ == "__main__":
    main()
