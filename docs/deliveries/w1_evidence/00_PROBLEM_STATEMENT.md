# SEARCH 2.0 — Problem Statement (W1)

**Tuần:** W1 · Understand the Problem  
**Phạm vi đánh giá hiện tại:** Stage 1 text-only trên `vn-poi-core-v1` + gold `gold_stage1_v1`  
**SoT thiết kế:** [`docs/specs/search2.0.md`](../../specs/search2.0.md)

---

## 1. Bài toán đang giải

Trong ô tìm địa điểm của app đặt xe, người dùng gõ một chuỗi **chưa hoàn chỉnh / có nhiễu / viết tắt**, hệ thống phải trả về đúng địa điểm họ muốn tới đủ nhanh để gợi ý khi đang gõ.

“Tìm sai địa điểm” **không phải một loại lỗi**. Theo tầm nhìn SEARCH 2.0, có **ba nguồn khó khác gốc**:

| Nguồn khó | Ví dụ | Bản chất |
|---|---|---|
| **Cách gõ** | `vạn hanhj`, `phợ bò`, `s702` | Vấn đề *văn bản*: không dấu, Telex, typo, mã tòa, alias |
| **Cùng tên / nhiều chỗ** | `sư vạn hạnh`, `vincom` | Đúng chữ nhưng sai chỗ nếu thiếu không gian–thời gian–hành vi |
| **Độ phủ & chất lượng data** | tiệm nhỏ, thiếu địa chỉ, near-dup OSM | Vấn đề *kho dữ liệu*, không chỉ mô hình |

Một embedding văn bản giải tốt nguồn 1 nhưng **mù** nguồn 2. Một ranker theo hành vi mà không có candidate đúng từ nguồn 1 thì xếp hạng vô nghĩa. Vì vậy kiến trúc **tách hai stage**:

- **Stage 1 — Retrieval:** địa điểm đúng có nằm trong candidate set không? — **chỉ văn bản**.
- **Stage 2 — Ranking:** trong candidates, cái nào đứng trước? — khoảng cách, thời điểm, thói quen.
- **Business layer:** dedup, filter, fallback.

---

## 2. Định nghĩa “tìm đúng” (W1 → metric W2)

### Stage 1 (đang khóa evaluation)

Với một truy vấn text `q` và tập chấp nhận `acceptable_poi_ids(q)`:

> **Stage 1 thành công** khi ít nhất một POI trong `acceptable_poi_ids` xuất hiện trong top-K candidate  
> (primary: K ∈ {100, 500, 1000}; kèm K@95 / K@98).

- Đơn vị thống kê độc lập: **`case_id`** (không bootstrap 1080 query như i.i.d.).
- Multi-positive: sparse, chủ yếu brand / category mơ hồ về text — xem `qrels_policy_v1.json`.
- Stage 1 **không** dùng origin, distance, time, history.

### Stage 2 (ngoài phạm vi W1 metric, nhưng định nghĩa sẵn)

> **Stage 2 thành công** khi, trong các candidate Stage 1 đã lấy đúng, thứ tự ưu tiên phản ánh ngữ cảnh ride-hailing (gần user, đúng lúc, quen thuộc) — đo bằng ranking/geo/business metrics ở W2+.

### End-to-end (demo W5–W6)

> Người dùng chọn (hoặc hệ thống xếp #1) đúng điểm đến họ muốn, trong latency chấp nhận được, kể cả khi một tầng fallback.

---

## 3. Câu hỏi W1 phải trả lời

| Câu hỏi | Trả lời ngắn (chi tiết trong các báo cáo kèm) |
|---|---|
| Data có gì? | Corpus `vn-poi-core-v1`: **186,322** POI searchable; gold **180** target × **1,080** query |
| User search gì? | Diagnostic families: CLEAN, alias, IME/orthography, typo, phonological, address, structural (không phải traffic thật) |
| Search fail ở đâu? | Ba nguồn ở §1; Stage 1 fail = miss candidate / collision same-name / nhiễu gõ; Stage 2 fail = đúng chữ sai chỗ |
| Ground truth là gì? | `intended_poi_id` + `acceptable_poi_ids` trên `query_variants_v1` |
| Success định nghĩa thế nào? | §2 — AcceptableRecall@K / K@R cho Stage 1 |

---

## 4. Giả thuyết ưu tiên (đưa sang W2)

1. **Same-name / multi-branch** là failure mode nặng nhất cho text-only khi query thiếu area — cần Recall sâu + multi-positive đúng chỗ; geo thuộc Stage 2.
2. **IME / không dấu / Telex** chiếm phần lớn nhiễu controlled trên gold — lexical floor (BM25) và dense zero-shot sẽ lệch nhau rõ trên slice này.
3. **Address + building code** cần surface form trung thực (ngõ/hẻm/kiệt, mã `S3.xx`) — không chỉ fuzzy name.
4. **Thiếu địa chỉ / near-dup trong corpus** giới hạn trần chất lượng dù model tốt — data quality là blocker song song với model.

---

## 5. Phạm vi cố ý *không* giải ở W1

- Không train / fine-tune retriever (W3).
- Không ranking geo/time/behavior (W4).
- Không coi phân bố family trên gold là phân bố production.
- Không dùng click log có PII trong báo cáo.

---

## 6. Output bàn giao W1

| Artifact | File |
|---|---|
| Problem statement | `00_PROBLEM_STATEMENT.md` (file này) |
| EDA POI | `01_EDA_POI.md` |
| EDA Query | `02_EDA_QUERY.md` |
| Query / POI taxonomy | `03_QUERY_POI_TAXONOMY.md` |
| Error taxonomy | `04_ERROR_TAXONOMY.md` |
| Data quality | `05_DATA_QUALITY_REPORT.md` |
| Locked data | `data/vietnam/gold_stage1_v1/{target_pois,query_variants}_v1.{csv,parquet}` |
