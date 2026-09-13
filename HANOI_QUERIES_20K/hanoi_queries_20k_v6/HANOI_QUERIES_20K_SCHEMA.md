# Schema Hanoi POI 20k — compact v6

Version: `hnq20k-compact-v6`, lưu ở manifest.json, không lặp trên từng query. Các bảng active chỉ có một version bundle. Tên và nội dung query, target, split, weak qrels và eligibility giữ nguyên v5.

## Queries: 8 trường

`queries_20k.parquet`: 20.000 dòng, khóa query_id. Đây là bảng dùng hằng ngày.

| Trường | Kiểu Arrow | Ý nghĩa |
|---|---|---|
| `query_id` | `string` | Khóa query trong version bundle; không tự chứa version. |
| `query` | `string` | Chuỗi gõ đầu vào Stage 1; không dùng clean_query thay thế. |
| `intended_poi_id` | `string` | Đích giả định lúc sinh; FK tới pois.canonical_id, không phải đáp án duy nhất đã xác minh. |
| `query_family_id` | `string` | Family để nhóm biến thể/bootstrap. Khác leakage_group_id. |
| `split` | `string` | train / dev_synthetic / test_synthetic / architecture_holdout. |
| `track` | `string` | retrieval_core / autocomplete / ambiguity_stress / ime_keystream / structured_code. |
| `case_type` | `string` | Loại biến thể cụ thể; không phải feature lúc serving. |
| `query_surface` | `string` | committed_text hoặc raw_keys; raw_keys chưa replay bằng engine thật. |

## Nhãn tương thích

`qrels.parquet`: 4.621.105 liên kết, khóa ghép (query_id, poi_id).

| Trường | Kiểu Arrow | Ý nghĩa |
|---|---|---|
| `query_id` | `string` | Khóa query trong version bundle; không tự chứa version. |
| `poi_id` | `string` | FK tới pois.canonical_id; một known-compatible weak label. |

Mỗi dòng là một POI đã biết tương thích theo rule. Đây không phải qrels được người adjudicate, không có relevance grade và cũng không phải hard negative. Đích giả định lưu trong queries.intended_poi_id; không lặp thêm cờ is_intended ở qrels. Đích này thuộc tập compatible theo snapshot, nhưng compatible không bảo đảm đầy đủ.

## Eligibility

`eligibility.parquet`: 20.000 dòng; join query_id, một nguồn quyết định train/core eval.

| Trường | Kiểu Arrow | Ý nghĩa |
|---|---|---|
| `query_id` | `string` | Khóa query trong version bundle; không tự chứa version. |
| `supervised_training_eligible` | `bool` | Cờ cho phép train đơn đích theo policy v5, bao gồm split=train. |
| `main_metric_candidate` | `bool` | Cờ cho phép core metric; vẫn phải chọn split eval. |
| `structured_metric_candidate` | `bool` | Subset structured có namespace theo policy; không đồng nghĩa main metric. |
| `training_exclusion_reasons` | `list<element: string>` | Rỗng iff supervised_training_eligible=true. |
| `main_metric_exclusion_reasons` | `list<element: string>` | Rỗng iff main_metric_candidate=true. |

## Các bảng còn lại

| File | Khóa | Nội dung |
|---|---|---|
| pois.parquet | canonical_id | 46.792 object, tên/alias/address JSON, tọa độ, origin flags, entity/branch/complex. Index 45.693 dòng destination_searchable=true |
| poi_splits.parquet | canonical_id | leakage_group_id và split; không thay entity_group_id |
| typing_sessions.parquet | (session_id,event_index) | 800 phiên / 16.190 trạng thái, ngoài 20k; giữ schema lịch sử và version nguồn |
| audit/query_generation.parquet | query_id | Evidence, namespace, phép biến đổi, nguồn/version/seed, collision flags… Chỉ mở khi cần audit |
| audit/query_review.parquet | query_id | Trạng thái AI/human review, scope, notes và review_reasons |
| audit/initial_query_lineage.parquet | query_id / source_query_id | Lượt refine ban đầu; không phải lịch sử đầy đủ mọi sửa |
| audit/ai_review_log.json, ai_review_edits.json | query_id | Bằng chứng review và nội dung sửa sau lượt refine |
| reference/frozen_v3_test.parquet | ID lịch sử | Test v3 nguyên bản để so với kết quả đã công bố; không trộn vào v6 train |

`HANOI_QUERIES_20K_SCHEMA.json` liệt kê kiểu Arrow thực tế của toàn bộ bảng. Kiểu null ở metadata kế thừa nghĩa chưa có giá trị, không tự chuyển thành false hay chuỗi rỗng. Hậu tố _json nghĩa chuỗi JSON cần json.loads, không phải Arrow struct.

## Trường đã bỏ khỏi bảng query chính

- Tên/địa chỉ/category/origin: nối query.intended_poi_id → pois.canonical_id. poi_name cũ là search_label. poi_address cũ là các trường housenumber/street/subdistrict nối bằng khoảng trắng, bỏ trường thiếu.
- known_compatible_poi_ids: nhóm qrels theo query_id; compatible_count là số dòng trong nhóm, không lưu hai lần.
- corpus_version/search_view_version và completeness: manifest.json.source_record_constants. dataset_version tại đó là version record nguồn v5; manifest.json.dataset_version mới là version bundle v6.
- requires_review: bool(review_reasons). label_status cũ có thể suy từ review_reasons rỗng hay không; nó không phải ground truth.
- session_id/keystroke_index của query v5 toàn null nên bỏ. Thông tin session thật của bộ mô phỏng nằm ở typing_sessions, không nối bằng session_id của bảng query.
- leakage_group_id: lấy từ poi_splits theo intended_poi_id. Flags/metadata còn lại chuyển audit, không xóa mất bằng chứng.

Mapping từng trường v5 nằm trong `audit/v5_field_mapping.json`. Không xóa qrels, eligibility hoặc audit rồi cho rằng bảng 8 trường đủ tự chứng minh chất lượng nhãn.

## Quan hệ và quy tắc sử dụng

Train: queries → eligibility bằng query_id, lọc split=train và supervised_training_eligible=true; nối pois theo intended_poi_id để dựng passage bằng đúng text builder đã chọn. Loader không tự đổi passage template của checkpoint E5 hiện tại.

Eval core: chọn split và track, lọc main_metric_candidate; đánh giá target hoặc qrels theo đúng metric protocol. Prefix/ambiguity/IME/structured phải báo riêng; không ép tất cả thành Hit@1 đơn đích. Routing Stage 1 không được dùng track/case_type/target/audit như feature lúc serving.

Review được giữ nguyên: 1.790 dòng đã đọc trực tiếp; phần còn lại không được nâng thành AI-reviewed khi đổi schema. Corpus vẫn chưa có pickup point được xác minh; ranking_lat/lon không phải routing_lat/lon. Dataset không có user/time/origin counterfactual của Stage 2.
