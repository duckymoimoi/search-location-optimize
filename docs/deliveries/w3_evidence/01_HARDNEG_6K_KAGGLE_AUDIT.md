# Audit Kaggle Stage-1 v6 hard-negative 6k

**Run:** [Kaggle notebook version 352867030](https://www.kaggle.com/code/hiengchi/vn-poi-stage1-v6-hardneg-6k-train?scriptVersionId=352867030), trạng thái `COMPLETE` theo Kaggle CLI. Đã tải lại `summary.json`, `gate_table.json`, `split_manifest.json` từ đúng version và đối chiếu byte-for-byte với output local: cả ba khớp.
**Snapshot:** corpus `vn-poi-core-v3-semantic-address-dedup50` (179.209 POI),
Gold POI v2.1 (800 query); pretrained `intfloat/multilingual-e5-small`, GPU
Tesla T4. Đây là exact-dense offline, **không** phải hybrid API/Docker.

## Kết quả có thể xác nhận

| Profile | Gold Hit@1 | Hit@5 | Hit@20 | Recall@100 | MRR@10 | Dev Hit@1 |
|---|---:|---:|---:|---:|---:|---:|
| Zero-shot cùng run | 84,625% | 93,50% | 96,375% | 98,625% | 0,8863 | 82,611% |
| Epoch 1 | **94,50%** | 98,125% | 99,375% | **100%** | **0,9603** | 91,361% |
| Epoch 2 / checkpoint lưu | 94,25% | **98,50%** | **99,50%** | 99,875% | 0,9591 | **91,417%** |

So epoch 2 với zero-shot **trong cùng run**, Gold Hit@1 tăng 9,625 điểm
phần trăm, Hit@20 tăng 3,125 điểm; bootstrap 10.000 lần theo 200 `case_id`
(seed 42) cho khoảng 95% diagnostic lần lượt `[6,375; 13,125]` và
`[1,75; 4,75]` điểm. Có 94 query chuyển thành đúng rank 1, 17 query mất
rank 1; 4 query còn ngoài top-20, đều thuộc q03. Đây không phải CI cho traffic
thực hoặc kết luận untouched-test vì giới hạn ở dưới.

Epoch 2 Gold Hit@1 theo role: q01 98,5%, q02 95,5%, q03 86,5%, q04 96,5%.
`building_code` 92,31% và `brand_branch` 90,13% là hai stratum yếu hơn phần
lớn các nhóm còn lại. 5.999 case (35.994 query) đi vào compile: 5.399 train,
600 dev; một case PNJ bị loại vì merge sang chi nhánh khác trên corpus v3.
Pack dùng 231.608 pair rows sau loại 24 Gold-positive rows; 2 epoch, 2.026
training steps, báo cáo tổng thời gian train ~990 giây.

Prefix q01 ở epoch 2: raw FHC@5 found 100%, SHC(w=3)@5 found 98,5%,
PrefixAUC@10 = 0,6777 so với zero-shot 0,6455. Đây là prefix **raw** trên
5.092 checkpoint; FHC có thể xảy ra trước khi đủ intent. Kernel chưa chấm
theo `entity_ready` của Gold và chưa có brand `group_ready`, nên không dùng
FHC raw 100% làm headline autocomplete có ý nghĩa ngữ nghĩa.

## Hai lỗi protocol cần xử lý trước khi nhận làm test cuối

1. `keep_checkpoint()` dùng **Gold Hit@1 cùng dev Hit@1** sau *mỗi epoch*;
   cả epoch 1 và 2 được mở Gold để quyết định lưu checkpoint, rồi epoch 2
   ghi đè epoch 1. Vì vậy Gold đã tham gia model selection. Epoch 2 có dev
   Hit@1 nhỉnh hơn epoch 1 nhưng không làm cho quy trình Gold-gated thành
   untouched test. Sửa sang dev-only selection; mở Gold đúng một lần sau
   khi checkpoint/threshold đã khóa.
2. Packager chỉ loại 24 `positive` pairs chứa Gold POI, **chưa loại negative**.
   Dataset upload còn 260 negative rows trỏ tới 106 Gold POI (258 train
   queries: 148 dense-hard, 66 random, 46 lexical-hard). Trainer đưa các
   POI này vào `negatives` và loss, nên strict cold-POI holdout bị vi phạm.
   Cần loại toàn bộ Gold IDs khỏi mọi pair/positive pool/ignore train, rồi
   assert overlap bằng 0 ngay trước upload và trong kernel. Gold POI vẫn ở
   corpus *đánh giá/index*, không biến mất khỏi search universe.

Điểm tốt của audit: train intended POI không giao Gold; query train/dev
không trùng Gold sau normalized text hoặc accent-fold trong lần kiểm tra
local. Không có bằng chứng direct query-text leakage, nhưng hai lỗi trên vẫn
đủ để hạ run này thành **diagnostic**, chưa làm checkpoint chính thức.

## So sánh và đánh giá bổ sung cần có

- Không so 6k với bảng 5k/4k Gold cũ bằng chênh lệch số trực tiếp: các run
  trước dùng `gold_stage1_v1_corpus_v2` (1.080 query), còn 6k dùng Gold v2.1
  (800 query). Muốn đo lợi ích của 1.000 case mới, replay checkpoint 5k và
  6k trên **cùng** Gold v2.1, corpus v3, exact-dense config; công bố profile
  và checkpoint selection của từng run.
- Rebuild pack 6k không dùng Gold làm negative, train với dev-only selection;
  giữ run hiện tại làm reference diagnostic, không xóa output/checkpoint.
- Eval checkpoint thắng dev trên Gold POI v2.1 theo role/stratum và
  `entity_ready` prefix; audit 17 rank-1 regressions và bốn q03 miss@20.
- Chấm Gold brand v1 bằng group-compatible semantics để biết POI-only train
  có hại bare-brand/namespace không. Đừng dùng branch Hit@1 cho bare brand.
- Muốn biết tác động trên app, re-encode toàn corpus bằng checkpoint mới,
  build index/version mới và so hybrid API E0/E1 cùng policy/candidate budget;
  không so exact dense offline với W2 hybrid API như cùng pipeline. Đo thêm
  latency p50/p95 và candidate recall trước quyết định triển khai.

## Evidence và provenance

- Exact-version download: `artifacts/results/kaggle_6k_version_352867030/stage1_v6_hardneg/` (local/derived). `summary.json` SHA-256 `cfe511f90a30041eb6c7d6379f25fbbc142deda851568944c743ebe24eb576a2`; `gate_table.json` SHA-256 `dc675020439f3ba6dd00bd4bd8da89b23d3770746aebb6392df9ed0ad9673c5b`.
- Checkpoint local `training/kaggle/output_stage1_v6_hardneg_6k/stage1_v6_hardneg/checkpoint_e5_hardneg/model.safetensors` SHA-256 `7fc36354e8a67e9562bff854ec4096a12022d7f0a29d0c38125daf2904b77ab8`.
- Uploaded pair table `training/kaggle/dataset_stage1_v6_hardneg_6k/training_pairs.parquet` SHA-256 `6d2e42844427423fd48ddf385b2a6ea5a42b109ec5467542fecbbbb8f727ae18`.
- Code path: `training/kaggle/prepare_kaggle_stage1_v6_hardneg_6k.py` (lọc positive), `training/kaggle/kernel_stage1_v6_hardneg_6k/run_train_stage1_v6_hardneg.py` (`rows_from_view`, `keep_checkpoint`, `train_one_epoch`).
