# Gold Stage1 Round-1 — BM25 + 6 dense exact (Kaggle GPU)

Profiles: BM25Okapi default · mE5-small · Bekko A8M · Bekko A25M · Halong · GTE-multilingual-base · BGE-M3.

Exact top-1000 only (no ANN). Internet ON for HF downloads.

**Live kernel:** https://www.kaggle.com/code/hiengchi/vn-poi-gold-stage1-w1-exact-dense-bm25  
**Dataset:** https://www.kaggle.com/datasets/hiengchi/vn-poi-gold-stage1-w1

```bash
python data/vietnam/gold_stage1_v1/lock_query_variants_v1.py
python training/kaggle/prepare_kaggle_gold_stage1_w1.py
python -m kaggle datasets create -p training/kaggle/dataset_gold_stage1_w1 --dir-mode zip
# or: python -m kaggle datasets version -p training/kaggle/dataset_gold_stage1_w1 -m "gold w1" --dir-mode zip
python -m kaggle kernels push -p training/kaggle/kernel_gold_stage1_w1
python -m kaggle kernels status hiengchi/vn-poi-gold-stage1-w1-exact-dense-bm25
```

Download + aggregate:

```bash
python -m kaggle kernels output hiengchi/vn-poi-gold-stage1-w1-exact-dense-bm25 -p training/kaggle/output_gold_stage1_w1
python apps/poi-search/bench/gold_stage1_selection_report.py
```
