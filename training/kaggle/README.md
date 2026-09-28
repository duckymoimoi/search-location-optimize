# Kaggle — bộ trial hiện hành

Giữ một pipeline 6k clean/dev-lock cho retrieval. GPU local chỉ inference/benchmark; optimizer/training nặng chạy Kaggle.

| Thành phần | Thư mục /script |
|---|---|
| Pack dev-lock | `dataset_stage1_v6_hardneg_6k_devlock`, `prepare_kaggle_stage1_v6_hardneg_6k_devlock.py` |
| Trainer canonical | `kernel_stage1_v6_hardneg_6k_devlock` |
| Corpus encode | `kernel_stage1_v6_hardneg_6k_devlock_encode` |
| Miner | `dataset_stage1_v6_hardneg_6k_mine`, `kernel_stage1_v6_hardneg_6k_mine`, recipe cùng tên |
| Regression/prefix rescore | `dataset_stage1_v6_hardneg_6k_devlock_rescore`, `kernel_stage1_v6_hardneg_6k_devlock_rescore` |
| Weight trial chuẩn bị | `kernel_dense_first_loss_only_dev`, tạo từ `tools/prepare_dense_first_kaggle_trial.py` |

Output dev-lock/encode/mine/rescore và payload dataset giữ local, không commit model/vector. Giữ source/payload được manifest pin hash. Trial đã bị loại, các pack 5k/6k chưa clean và model-screen không nằm trong cây active; có bản lưu local dưới `artifacts/archive/retired_versions_20260928` ngoài Git.

Không submit lại kernel chỉ để dọn repo. Muốn trial mới phải khóa dataset/config/seed, đánh giá dev rồi chọn checkpoint; re-encode đúng checkpoint trước benchmark. Bộ Gold POI hiện hành dùng regression, không phải untouched holdout.
