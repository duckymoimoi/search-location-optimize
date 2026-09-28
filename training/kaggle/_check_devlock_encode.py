import json
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from transformers import AutoModel, AutoTokenizer

CKPT = Path(r"training/kaggle/output_stage1_v6_hardneg_6k_devlock/stage1_v6_hardneg/checkpoint_e5_hardneg")
NPY = Path(r"artifacts/embeddings/me5_small_v3_6k_devlock/corpus_embeddings.npy")
IDS = Path(r"artifacts/embeddings/me5_small_v3_6k_devlock/poi_ids.parquet")
DOCS = Path(r"data/vietnam/poi_corpus_v3/search_documents.parquet")

import pandas as pd

tokenizer = AutoTokenizer.from_pretrained("intfloat/multilingual-e5-small")
model = AutoModel.from_pretrained(CKPT).eval()
docs = pd.read_parquet(DOCS, columns=["poi_id", "passage_context"])
text = "passage: " + str(docs.iloc[0]["passage_context"])
tokens = tokenizer(text, padding=True, truncation=True, max_length=128, return_tensors="pt")
tokens.pop("token_type_ids", None)
with torch.no_grad():
    hidden = model(**tokens).last_hidden_state
    mask = tokens["attention_mask"].unsqueeze(-1).expand(hidden.size()).float()
    pooled = (hidden * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
    vec = F.normalize(pooled, p=2, dim=1).numpy().astype(np.float32)[0]
ref = np.load(NPY, mmap_mode="r")[0]
print("cosine", float(np.dot(vec, ref)))
print("model", type(model).__name__)
