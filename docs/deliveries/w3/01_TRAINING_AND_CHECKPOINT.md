# W3 — Training dataset và checkpoint

Cập nhật 2026-09-28. Model bàn giao: `me5-6k-devlock-epoch2`; corpus/index `vn-poi-core-v3-me5-6k-devlock`, 179.209 POI, vector 384 chiều.

## Dữ liệu và quy trình

Pack `train_stage1_v6_hardneg_6k_clean`: 35.994 query, chia 32.394 train/3.600 dev theo entity/case; 231.608 pairs gồm 37.446 positive, 194.060 negative, 102 ignore. Train/dev intended entity và normalized text overlap 0; pair Gold-positive IDs overlap 0 theo [EDA](../w1/eda/dataset_eda.json).

Train trên Kaggle, chọn checkpoint theo dev rồi encode/index cùng checkpoint. Không train optimizer trên GPU local. Manifest run phải pin dataset thực dùng; audit file hiện có không tự chứng nhận dataset của mọi model.

## Checkpoint selection evidence

| Model | Dev Hit@1 | POI regression Hit@1 |
|---|---:|---:|
| Pretrained đối chứng trong run train | 82,61% | 84,625% |
| Dev-lock epoch 2 | 91,92% | 94,75% |

Đây là evaluation của run train, không phải ANN serving metric. Epoch 2 regression Hit@20 99,25%, Hit@50 99,50%, MRR@10 0,9617. Dataset regression đã phơi nhiễm, không dùng claim independent generalization.

Run: `hiengchi/vn-poi-stage1-v6-hardneg-6k-devlock-train`; output local `training/kaggle/output_stage1_v6_hardneg_6k_devlock/stage1_v6_hardneg/`. Bundle model/vector/ID map hash tại [snapshot](handoff/evidence_snapshot.json).

## Quyết định

Giữ checkpoint này cho baseline nghiên cứu; chưa train thêm trong vòng bàn giao. Tách sampling probability/loss weight cho trial sau; chỉ kích hoạt trial nếu error analysis xác định gap thuộc model sau serving fixes. Mọi model mới phải re-encode và chạy lại quality/latency gates.
