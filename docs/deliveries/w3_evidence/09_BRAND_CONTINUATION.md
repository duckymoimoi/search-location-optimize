# Brand continuation — checkpoint 6k không được thay

Kernel: https://www.kaggle.com/code/hiengchi/vn-poi-stage1-v6-brand-dev-trial-train
Output: `training/kaggle/output_stage1_v6_brand_dev_trial/brand_trial/summary.json`

Tiếp từ checkpoint 6k, 2 epoch, câu brand nhiều POI đúng. Giữ epoch chỉ khi brand dev Hit@1 không giảm và POI dev Hit@1 không tụt quá 0.01 so với checkpoint 6k. Cả epoch 1 và epoch 2 đều rớt cửa POI, nên checkpoint giữ lại là epoch 0.

| | brand dev Hit@1 | brand dev Hit@20 | POI dev Hit@1 |
|---|---:|---:|---:|
| checkpoint 6k | 0.603 | 0.865 | 0.919 |
| epoch 1 | 0.655 | 0.914 | 0.849 |
| epoch 2 | 0.654 | 0.914 | 0.840 |

Gold chấm trên checkpoint được giữ, tức vẫn là model 6k: brand Hit@1 0.552, POI Hit@1 0.9475. Brand dev nhích lên khoảng 0.05, đổi lại POI dev mất khoảng 0.07. Chưa có checkpoint brand nào thay 6k.
