# 6k dev-lock — Gold chấm một lần

Kernel: https://www.kaggle.com/code/hiengchi/vn-poi-stage1-v6-hardneg-6k-devlock-train
Dataset: https://www.kaggle.com/datasets/hiengchi/vn-poi-stage1-v6-hardneg-6k-devlock
Output local: `training/kaggle/output_stage1_v6_hardneg_6k_devlock/stage1_v6_hardneg/`

Không ghi đè diagnostic `352867030`. `tools/judge_devlock_summary.py` trả `call=continue`: `checkpoint_selection=dev_only`, `gold_opened_after_lock=true`, `epoch_eval` không có `gold_hit1`. Giữ epoch 2 vì dev Hit@1 cao hơn epoch 1 và cao hơn zero-shot dev.

| | dev Hit@1 | Gold Hit@1 | Gold Hit@20 | Gold Hit@50 | Gold MRR@10 |
|---|---:|---:|---:|---:|---:|
| zero-shot | 0.8261 | 0.84625 | — | — | — |
| epoch 2 | 0.9192 | 0.9475 | 0.9925 | 0.995 | 0.9617 |

Gold n=800. Mất rank 1 so với zero-shot: 16. q03 miss@20: 5. miss@50: 4, tất cả ở q03.

Hit@1 theo role: q01 0.990, q02 0.950, q03 0.885, q04 0.965.

Prefix trong summary là raw grapheme trên 200 q01 / 5092 prefix, không phải mẫu số `entity_ready`. Kernel version đã chạy không ghi `run_*_prefix.jsonl`, nên chưa lọc được `entity_ready`. Raw FHC@10 finetuned = 1.0 (zero-shot cũng 1.0). Raw FHC@1 giảm 1.0 → 0.99. SHC@1 (window 3) 0.91 → 0.935. PrefixAUC@10 mean 0.646 → 0.677. Không dùng raw FHC làm kết luận autocomplete.

Pair train là bảng local đã sạch Gold (231608 hàng, overlap 0), dense negative lấy từ `artifacts/embeddings/me5_small_v3` (`max_length` 128). Chưa đưa checkpoint vào index demo.
