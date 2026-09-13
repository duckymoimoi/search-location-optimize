# Hanoi POI 20k — compact v6

**Bảng query chính còn 8 trường**, gồm query_id, query, intended_poi_id, query_family_id, split, track, case_type, query_surface. Nội dung dữ liệu giữ nguyên v5; đây là thay đổi cách lưu trữ và cách đọc, không phải một lần sinh/train/review mới.

## Dùng các file nào?

| Nhu cầu | File |
|---|---|
| Đọc query, chia nhóm/split | queries_20k.parquet |
| Train đơn đích hoặc chọn core eval | queries_20k.parquet + eligibility.parquet |
| Nội dung/tọa độ/alias POI | pois.parquet |
| Tập compatible nhãn yếu | qrels.parquet |
| Kiểm tra split theo nhóm POI | poi_splits.parquet |
| Đánh giá tiến trình gõ | typing_sessions.parquet |
| Xem nguồn sinh và quyết định review | audit/ |
| So với test E5 v3 cũ | reference/frozen_v3_test.parquet |
| Từ điển trường | HANOI_QUERIES_20K_SCHEMA.md / .json |

Không còn các bản train/dev/test, eligibility và corpus trùng lặp trong nhiều file active. Loader lọc từ bảng chính. Không random-split lại dữ liệu.

## Số lượng

- 20.000 query: train 13.190, dev 2.925, test v5 885, architecture holdout 3.000.
- 6,066 query train đơn đích đủ điều kiện theo policy v5.
- 45,693 destination-searchable POI trong catalog đầy đủ.
- 4,621,105 liên kết compatible nhãn yếu được tách khỏi bảng query.
- Bảng query chính 463,336 byte; không cần nạp qrels/audit để đọc query.
- Trạng thái review giữ nguyên: 1.790 dòng được Codex đọc trực tiếp, 18.210 dòng chưa được đọc riêng. Không có human-gold mới.

## Ví dụ nạp

```python
from load_dataset import load_training, load_evaluation, load_pois, iter_qrels

root = '/path/hanoi_queries_20k_v6'
train = load_training(root)  # Chỉ nạp queries và eligibility.
dev = load_evaluation(root, 'dev_synthetic', 'retrieval_core')
catalog = load_pois(root)    # Chỉ destination_searchable=true.

queries = dev['query'].to_pylist()
target_ids = dev['intended_poi_id'].to_pylist()
for labels in iter_qrels(root, dev['query_id'].to_pylist()):
    pass  # Batch các weak-compatible pairs, không nạp toàn bộ vào RAM.
```

Loader trả bảng query 8 trường. Passage POI được nối từ catalog theo canonical_id và dựng bằng text builder của experiment; không lấy clean_query từ audit làm input model. iter_qrels hiện quét theo batch rồi lọc; chưa phải dịch vụ indexed lookup.

## Tái tạo và kiểm chứng

```bash
pip install -r requirements.txt
python build_compact.py --source /path/hanoi_queries_20k_v5 --output /path/rebuild_v6
```

Cần input v5 để chạy migration; gói v6 không nhét lại toàn bộ v5 và các snapshot cũ. Manifest giữ hash nguồn. Quy trình đã kiểm tra bằng nhau với v5: 8 trường query, mọi cặp qrels, eligibility, review, generation audit và các trường POI được tách; frozen test giữ nguyên byte. Các loader đã chạy kiểm tra số dòng và liên kết target.

Mọi thông tin trong audit và reference chỉ phục vụ kiểm chứng; không đưa trực tiếp vào feature serving. Nhãn compatible vẫn yếu, IME chưa replay engine thật, test v5 không thay thế frozen v3 test, và Stage 2 chưa có dữ liệu cá nhân hóa mới.
