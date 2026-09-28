# Brand và POI trong cùng batch — epoch 2 được giữ

Kernel: https://www.kaggle.com/code/hiengchi/vn-poi-stage1-v6-brand-poi-mix-train
Output: `training/kaggle/output_stage1_v6_brand_poi_mix/brand_poi_mix/summary.json`

Không ghi câu brand vào bảng pair 6k. Mỗi batch là 12 pair POI sẵn có và 4 câu brand. Learning rate 2e-6. Giữ epoch khi brand dev Hit@1 không giảm và POI dev Hit@1 không tụt quá 0.01.

| | brand dev Hit@1 | brand dev Hit@20 | POI dev Hit@1 | giữ |
|---|---:|---:|---:|---|
| checkpoint 6k | 0.603 | 0.865 | 0.9192 | |
| epoch 1 | 0.596 | 0.878 | 0.9186 | không |
| epoch 2 | 0.608 | 0.901 | 0.9192 | có |

Gold chấm một lần trên epoch 2. Brand Hit@1 0.552 lên 0.578, Hit@20 0.893 lên 0.898. POI Hit@1 giữ 0.9475. Checkpoint này chưa gắn vào app demo.
