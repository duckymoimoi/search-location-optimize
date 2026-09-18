# SEARCH 2.0 — Chuẩn viết query variant (Stage 1)

**Trạng thái:** authoring SoT cho gold  
**Agent skill (đọc để viết):** `.cursor/skills/search20-stage1-query-variants/SKILL.md`

Tài liệu này chỉ giữ nguyên tắc ngắn. Chi tiết operator / ví dụ / checklist nằm trong skill (tránh lẫn train–eval–metric).

## Phạm vi

- Viết canonical + variant cho case trong `data/vietnam/gold_stage1_v1/` (`target_pois_locked`, 180 POI).
- Stage 1 text-only; không origin/distance.
- Gold: `severity=CLEAN|SINGLE` only — không compound training ở đây.

## Nguyên tắc

1. Tách alias hợp lệ khỏi lỗi gõ / IME / nhầm âm.  
2. Giữ intent; sửa thành POI khác → reject.  
3. Text mơ hồ → `acceptable_poi_ids` multi-positive (brand / mã trùng).  
4. Không bịa; không chat template; không bare multi-branch brand làm unique-target.  
5. Không dump full char-prefix vào gold.

## Đơn vị & Cấu trúc Pack

- `case_id` = intent → POI (không phải origin–pair).
- Mỗi case: **6 variant fold-distinct** (180 POIs × 6 = **1,080 queries**):
  * `v1` (CLEAN): `canonical`
  * `v2` (SINGLE): `ORTHOGRAPHIC_IME` (`strip_diacritics`)
  * `v3` (CLEAN/SINGLE): `ALIAS` (`name_area`, `name_address`, `short_name`, `code_short`)
  * `v4` (CLEAN/SINGLE): `ALIAS` hoặc `ADDRESS_VARIANT` (`abbreviation`, `slash_normalize`...)
  * `v5` (SINGLE): `ORTHOGRAPHIC_IME` (`telex_leftover`: vowel marker, tone marker, telex dd)
  * `v6` (SINGLE): `MECHANICAL_TYPO` (`adjacent_key`, `char_transpose`, `double_letter`) hoặc `PHONOLOGICAL` (`phonological_confusion`)

## Nguyên Tắc Qrels & Đánh Giá Benchmark (Evaluation Protocol)

1. **Dual Qrels & Recall Metrics**:
   - **`StrictTargetRecall@K`**: Chỉ tính thành công nếu đúng `intended_poi_id` xuất hiện trong Top K (đo độ nhạy đích danh gốc).
   - **`AcceptableRecall@K`**: Tính thành công nếu **bất kỳ POI nào** trong `acceptable_poi_ids` xuất hiện trong Top K (phản ánh trung thực tính chấp nhận được về mặt ngữ nghĩa văn bản của Stage-1 text retrieval).
2. **Micro vs Macro-Family Score**:
   - **Micro Score**: Tính trên toàn bộ 1,080 queries.
   - **Macro-Family Score**: Trung bình không trọng số của 6 family chính (`CLEAN`, `ORTHOGRAPHIC_IME`, `MECHANICAL_TYPO`, `PHONOLOGICAL`, `ALIAS`, `ADDRESS_VARIANT`) nhằm loại trừ độ lệch khi model chỉ mạnh ở một nhóm nhất định.
3. **Ngưỡng Phân Tích Cấp Operator**:
   - Chỉ xếp hạng/so sánh mô hình trên các operator có $N \ge 20$.
   - Các operator mỏng ($N < 20$) chỉ dùng cho chẩn đoán định tính (qualitative diagnostics).

## Stratum (khớp gold lock)

`brand_branch` · `named_clear` · `category_local` · `address_street_building` · `explicit_area_cross_region` · `code_transit_landmark` · `building_code`

## Không thuộc tài liệu / skill này

- Metric Stage-2 geo/rerank, ANN latency, trade-off origin
- Phân phối training / COMPOUND augmentation
- So sánh taxonomy v4/v5

Tham chiếu thiết kế dài (không dùng để author hàng ngày): `SEARCH_2_0_QUERY_VARIANT_GENERATION_RULES_V5.md`
