# Bench (SEARCH 2.0 gold)

FE/API smoke vẫn dùng `smoke_contract.py` khi runtime local chạy.

## Gold Stage 1 — model screen & prefix

```powershell
# Aggregate Round-1 exact runs (sau khi download Kaggle output)
python apps/poi-search/bench/gold_stage1_selection_report.py

# Expand char-prefixes (Round 1b); dense chạy trên Kaggle
python apps/poi-search/bench/gold_stage1_prefix_char_bench.py --expand-only
```

Kaggle:

```powershell
python training/kaggle/prepare_kaggle_gold_stage1_w1.py
python -m kaggle kernels push -p training/kaggle/kernel_gold_stage1_w1
python -m kaggle kernels push -p training/kaggle/kernel_gold_stage1_prefix
```

Protocol: `docs/specs/SEARCH_2.0_STAGE1_MODEL_SELECTION_PROTOCOL.md`.

Env smoke API: `POI_API_BASE_URL` (default `http://127.0.0.1:8000`).
