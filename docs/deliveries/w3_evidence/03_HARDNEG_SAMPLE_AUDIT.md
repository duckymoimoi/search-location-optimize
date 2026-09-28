# Soi 150 hard negative — pack 6k sạch Gold

Nguồn: `data/vietnam/train_stage1_v6_hardneg_6k_clean/training_pairs.parquet` (231.608 hàng, Gold overlap 0). Mẫu seed 42: 75 dense, 50 random, 25 lexical. Nhãn nằm trong [`hardneg_audit_6k_sample.csv`](hardneg_audit_6k_sample.csv).

| Nguồn | true_hard | easy | false_negative |
|---|---:|---:|---:|
| dense_hard | 73 | 0 | 2 |
| lexical_hard | 25 | 0 | 0 |
| random | 0 | 50 | 0 |
| Tổng | 98 | 50 | 2 |

False negative trên mẫu: **2/150 (1,3%)**, cả hai thuộc dense. Cùng tên hiển thị nhưng khác địa chỉ: 12 hàng, chủ yếu chi nhánh khác (Highlands, WinMart+, PNJ, Circle K, Petrolimex, Bách Hóa Xanh, Lotteria, PV Oil). Protocol hiện tại giữ các chi nhánh đó làm hard negative.

Hai hàng đánh `false_negative` là Petrolimex cùng tên và cùng địa chỉ hành chính nhưng khác `poi_id`:

- `osm:node/12722252501` và `osm:node/4386947095`, Phường Nam Hồng Lĩnh, Hà Tĩnh
- `osm:node/13011289001` và `osm:node/13011288901`, Xã Chư A Thai, Tỉnh Gia Lai

Chưa đổi pair vì chưa chứng minh hai id là cùng một cửa hàng. Không dùng mẫu này để chọn checkpoint.
