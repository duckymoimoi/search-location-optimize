# Mẫu số prefix Gold POI v2.1

Khóa trước khi chấm checkpoint dev-lock. Nguồn: `prefix_evidence_v2_1.jsonl`. Headline autocomplete chỉ tính checkpoint có `prefix_index >= entity_ready_grapheme`. Raw FHC trên cả chuỗi là diagnostic.

| Đại lượng | Giá trị |
|---|---:|
| q01 | 200 |
| Checkpoint từ `entity_ready` | 368 |
| Case chỉ `entity_ready` ở ký tự cuối | 180 |
| Case đủ 3 checkpoint sau mốc để tính SHC(w=3) | 20 |

SHC(w=3) không rút cửa sổ khi chuỗi còn ngắn hơn 3. 180 case chỉ có một checkpoint sau mốc nên không vào mẫu số SHC.

Công cụ: `tools/report_stage1_prefix_ready.py`. Kernel đang chạy chưa ghi `run_*_prefix.jsonl`; bản local của kernel dev-lock đã được sửa để lần sau ghi file đó. Chưa có điểm `entity_ready` của checkpoint sạch.
