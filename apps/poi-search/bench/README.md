# Bench (SEARCH 2.0 gold)

FE/API smoke vẫn dùng `smoke_contract.py` khi runtime local chạy.

## Gold Stage 1 — model screen & prefix

```powershell
# Aggregate Round-1 exact runs (sau khi download Kaggle output)
python apps/poi-search/bench/gold_stage1_selection_report.py

# Overlap / lexical rescue vs mE5 (trước khi tune analyzer)
python apps/poi-search/bench/gold_stage1_lexical_rescue_report.py

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

## Stage 1 v6 — checkpoint 500

Benchmark dùng lexical DSL hiện hành, exact mE5 corpus vectors và RRF/policy
query-only từ `app.py`, không import Runtime hoặc tải lại corpus model:

```powershell
cd apps/poi-search
docker compose -f docker-compose.search-dev.yml run --rm bench `
  python apps/poi-search/bench/stage1_v6_500_baseline.py `
  --dataset-label train_stage1_v6_hard_noise_500 `
  --es-url http://host.docker.internal:9200
```

Output mặc định:
`artifacts/results/stage1_v6_hard_noise_500_baseline/`. Đây là diagnostic trên
authored train data, không phải untouched gold. Dùng cùng script với
`--dataset-role frozen_evaluation` để replay một evaluation snapshot.

Env smoke API: `POI_API_BASE_URL` (default `http://127.0.0.1:8000`).
