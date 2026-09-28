# Prefix entity_ready và brand group-compatible — checkpoint 6k dev-lock

Nguồn: https://www.kaggle.com/code/hiengchi/vn-poi-stage1-v6-hardneg-6k-devlock-rescore-run
Output: `training/kaggle/output_stage1_v6_hardneg_6k_devlock_rescore/rescore/`

Exact-dense, corpus v3, cùng checkpoint epoch 2 đã khóa bằng dev. Không phải hybrid API.

## Prefix Gold POI q01

Mẫu số khóa trước điểm model: 200 q01, 368 checkpoint `entity_ready`, 180 case chỉ sẵn sàng ở ký tự cuối, 20 case có ít nhất 3 checkpoint nên SHC chỉ tính trên 20 case.

| | raw FHC@1 | entity_ready FHC@1 | entity_ready FHC@5 | entity_ready FHC@10 | entity_ready PrefixAUC@10 |
|---|---:|---:|---:|---:|---:|
| zero-shot | 1.00 | 0.960 | 1.00 | 1.00 | 1.00 |
| epoch 2 | 0.99 | 0.990 | 0.99 | 1.00 | 1.00 |

`entity_ready` FHC@1 tăng. Raw FHC@1 và `entity_ready` FHC@5 mỗi cái giảm một bậc, từ 1.00 xuống 0.99. Raw FHC không phải kết luận autocomplete.

## Brand Gold v1

70 family, 248 query. Hit là trung bình theo family của AnyCompatible. POI-only train làm brand kém đi, rõ nhất ở rank 1 và độ phủ.

| | Hit@1 | Hit@20 | Hit@50 | group MRR@10 | coverage@20 | namespace false-branch@20 |
|---|---:|---:|---:|---:|---:|---:|
| zero-shot | 0.674 | 0.901 | 0.929 | 0.737 | 0.700 | 0.012 |
| epoch 2 | 0.552 | 0.893 | 0.921 | 0.658 | 0.624 | 0.037 |

Namespace false-branch@20 tính trên 82 query có namespace. Checkpoint này chưa được đưa vào index demo.
