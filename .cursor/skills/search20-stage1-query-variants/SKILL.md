---
name: search20-stage1-query-variants
description: >-
  Author Stage-1 gold query variants for SEARCH 2.0 Vietnamese POI retrieval.
  Writes canonical + controlled SINGLE/alias variants for locked gold cases
  (gold_stage1_v1). Use when writing query variants, labeling noise/alias,
  authoring gold queries, or when the user mentions Stage-1 variants / qrels text.
---

# SEARCH 2.0 — Stage 1 query variant authoring

## Scope

**Do:** viết / duyệt `query_text` + nhãn family/operator cho gold Stage 1 (text-only). Mọi query tự viết thủ công
**Do not:** metric model, ANN, Stage-2 geo/rerank, training compound augmentation, mở rộng POI list đã lock. DÙNG CODE ĐỂ SINH RA QUERY HÀNG LOẠT

**Sources of truth**

| Artifact | Path |
|---|---|
| Locked POIs | `data/vietnam/gold_stage1_v1/target_pois_v1.csv` |
| Manifest | `data/vietnam/gold_stage1_v1/manifest.json` |
| Operator detail | [operators.md](operators.md) |
| Examples | [examples.md](examples.md) |

Corpus: `vn-poi-core-v1` (`data/vietnam/poi_corpus_v1/`).

---

## Hard rules

1. Stage 1 = **text only**. Không dùng origin / distance / time / history để sinh hoặc quyết định đúng–sai.
2. Mỗi variant **một** `query_variant_family` + `variant_operator` trong whitelist ([operators.md](operators.md)).
3. Gold chỉ `severity=CLEAN|SINGLE`. **Không** `COMPOUND`.
4. Giữ intent: sửa 1 ký tự mà thành POI/địa chỉ khác thật → **reject**.
5. Không bịa tên / địa chỉ / mã; không chat template (`cho tôi đến…`); không nhét origin vào query.
6. Alias ≠ noise. Brand/Vincom/mã trùng → multi-positive qrels, không ép 1 chi nhánh.
7. Prefix đầy đủ (`char_prefix` mọi độ dài) **không** lưu vào gold — để benchmark sinh. Tối đa 1 `mid_token_incomplete` nếu hữu ích.

---

## Per-case pack (gold 6 variants)

Với mỗi `case_id` trong `target_pois_v1.csv`, viết **đúng 6** variant fold-distinct:

| slot | `severity` | Family / operator | Ghi chú vị trí |
|---|---|---|---|
| v1 | `CLEAN` | `CLEAN/canonical` | Chuẩn hoá đầy đủ nhận diện theo stratum |
| v2 | `CLEAN` hoặc `SINGLE` | `ADDRESS_VARIANT` / `ORTHOGRAPHIC_IME` / `TOKEN_EDIT` | Biến thể địa chỉ tự nhiên hoặc chính tả |
| v3 | `CLEAN` hoặc `SINGLE` | `ALIAS` / `ORTHOGRAPHIC_IME` / `ADDRESS_VARIANT` | Tên viết tắt, khu vực, strip diacritics |
| v4 | `CLEAN` hoặc `SINGLE` | `ALIAS` / `STRUCTURAL` (`token_order_variant`, `short_name`) | Standalone entity search hoặc đảo ngữ chuẩn |
| v5 | `SINGLE` | Nhóm nhiễu đơn (`telex_leftover`, `char_insert`, `double_letter`) | Bắt buộc Levenshtein ≤ 12 so với canonical |
| v6 | `SINGLE` | Nhóm nhiễu đơn (`adjacent_key`, `char_delete`, `char_transpose`, `phonological_confusion`, `tone_confuse`) | Bắt buộc Levenshtein ≤ 12 so với canonical |

Sáu `query_text` phải **khác nhau tuyệt đối** sau normalize NFKC + casefold (mục Validate).

---

## Nguyên Tắc Giữ Tính Tự Nhiên Tuyệt Đối Của Query (Naturalness Guidelines)

1. **Biến thể địa chỉ có dấu xuyệt (`/`)**:
   - Người dùng Việt Nam trên thực tế **không bao giờ gõ dạng gạch nối cơ học** như `166-9` hay `24-19`.
   - Bắt buộc dùng các dạng khẩu ngữ/văn bản tìm kiếm thực tế:
     * **Miền Bắc**: `Số [nhà] ngõ [ngõ] [đường]` (ví dụ: `Số 24 ngõ 19 Trần Quang Diệu`, `Số 48 ngách 34 ngõ 143 Nguyễn Chính`).
     * **Miền Nam**: `Hẻm [số nhà]/[hẻm] [đường]` hoặc `Hẻm [số]` (ví dụ: `Hẻm 96/2 Đông Nhì`, `Hẻm 30 Nguyễn Văn Linh`).
     * **Miền Trung**: `K[kiệt]/[số] [đường]` hoặc `Kiệt [số] [đường]` (ví dụ: `K151/68 Âu Cơ Liên Chiểu`, `K91/8 Ngô Xuân Thu`).
   - **Cấm tuyệt đối**: Tự chế đuôi số (`259-15`, `25-12`) gán vào canonical không hề có xuyệt.

2. **Truy vấn thực thể độc lập (Standalone Entity Search)**:
   - Với các địa điểm, quán ăn, khách sạn có tên riêng định danh rõ hoặc unique toàn quốc (như `Ngày của Nắng Coffee`, `Bún Ngan Cô Tuyết`, `Khách Sạn Little Saigon Boutique`):
     * Cần có dạng truy vấn chỉ gồm **tên riêng/thương hiệu**, lược bỏ toàn bộ số nhà, tên đường, quận huyện phía sau (`Ngày của Nắng Coffee`).
     * Mục đích: Tạo bài test thực sự (challenge) cho mô hình trích xuất thực thể POI mà không cần nương tựa vào tín hiệu địa chỉ hành chính.

3. **Bảo toàn danh từ riêng trong đảo từ (`token_order_variant`)**:
   - Khi đảo ngữ, **tuyệt đối không xé lẻ** danh từ riêng hoặc tên địa danh ghép (CẤM: `Trung Cà phê Nguyên`, `Hội Bánh Mì An`, `gà Phở Lâm`, `Lý Phở Quốc Sư`, `Tường Cà phê Vy`).
   - Chỉ được đảo cấu trúc cú pháp tiếng Việt: `[Thương hiệu] + [Loại hình]` (ví dụ: `Trung Nguyên Cà phê`, `Tường Vy Cà phê`, `Phở Lâm Gà`, `Phở Lý Quốc Sư Tân Phú`).

4. **Tách/dính khoảng cách tự nhiên (`space_split` / `space_merge`)**:
   - **Cấm tuyệt đối**: Nối dính tên tỉnh/thành phố cơ học (`ĐàNẵng`, `CầnThơ`, `HàNội`).
   - Chỉ áp dụng trên:
     * Tên riêng ngoại/từ mượn ghép: `SpringHotel`, `ThaiFood`, `bon s vegan`.
     * Tên đường ghép: `LêDuẩn`.
     * Khoảng trắng quanh ký tự đặc biệt: `30 / 49 Nguyễn Văn Linh`.

5. **Tránh bẫy từ đồng âm trong `address_component_omission`**:
   - Thận trọng với các từ đồng âm với cấp hành chính nhưng là tên riêng (ví dụ: chữ `Quận` trong `Café Cố Quận` là tên quán, không phải đơn vị hành chính; không được xóa).

---

## Workflow

Copy checklist:

```
Case Progress:
- [ ] 1. Đọc POI row từ target_pois_v1.csv
- [ ] 2. Viết canonical theo stratum
- [ ] 3. Ghi acceptable_poi_ids (single vs multi)
- [ ] 4. Viết 3 variant còn lại
- [ ] 5. Gắn family/operator/query_types/lang_*
- [ ] 6. Validate (checklist dưới)
- [ ] 7. Append rows → query_variants draft
```

### 1. Đọc POI

Dùng: `case_id`, `poi_id`, `name`, `brand`, `housenumber`, `street`, `province`, `subdistrict`, `primary_sampling_stratum`, `category`.

Mọi POI đã `address_status=direct` + hn + street.

### 2. Canonical theo stratum

| Stratum | Canonical |
|---|---|
| `brand_branch` | `{brand} {ward\|street\|khu}` — đủ disambiguation; **cấm** bare brand multi-branch |
| `named_clear` | tên đủ nhận diện (có thể + khu nếu trùng tên) |
| `category_local` | **tên POI thật** — không `category+ward` giả |
| `address_street_building` | `{housenumber} {street}` giữ `/` nếu có |
| `explicit_area_cross_region` | tên/brand + ward hoặc province trong text |
| `code_transit_landmark` | tên địa điểm / bến / đình… |
| `building_code` | mã hoặc tên tòa người dùng hay gõ (`S3.01`, `Landmark72`, `17T8 Trung Hòa…`) — có thể + khu nếu mã ngắn |

### 3. Qrels text

- Rõ ràng → `acceptable_poi_ids = [poi_id]`
- Brand/Vincom nhiều chi nhánh cùng text; mã tòa trùng; alias mỏng → liệt kê mọi POI corpus **hợp lý theo text** (cùng brand_fold + cùng khu nếu canonical có khu; hoặc mọi brand nếu alias chỉ brand — đánh `needs_review` nếu set quá lớn)
- Chưa chắc → `review_status=needs_review`, không fake single-ID

### 4–5. Viết variant + nhãn

Xem [operators.md](operators.md). Ưu tiên phép biến đổi **một chỗ**, đọc được.

`query_types`: ≥1 tag cấu trúc + đúng một `lang_vi|lang_en|lang_mixed` (pipe).

### 6. Validate trước accept

1. Non-empty; không chat template.  
2. Khác canonical (trừ dòng canonical).  
3. Fold-distinct trong cùng case.  
4. `severity` khớp số phép (gold: 0 hoặc 1).  
5. Operator thuộc family; không xóa digit số nhà / phá mã.  
6. Corpus-aware: không vô tình thành tên POI khác.  
7. `building_code` / brand: không gán unique-target nếu text còn mơ hồ.

Normalize so trùng:

```text
NFKC → casefold → trim → collapse whitespace
(optional) bỏ dấu khi bắt duplicate “cùng ý gõ”
```

### 7. Output row schema

```text
case_id
variant_id                 # {case_id}-v{1..4}
query_text
canonical_query
query_variant_family
variant_operator
variant_subtype            # optional
severity                   # CLEAN | SINGLE
query_types
intended_poi_id
acceptable_poi_ids         # JSON list or pipe-separated ids
primary_sampling_stratum
review_status              # draft | accepted | needs_review
generator_version          # search20-stage1-query-variants@1
```

Default draft path: `data/vietnam/gold_stage1_v1/query_variants_draft.csv` (tạo nếu chưa có; không sửa `target_pois_v1.csv`).

---

## Cấm tuyệt đối

- `COMPOUND` trên gold  
- Bare multi-branch brand làm unique-target  
- `category+ward` giả tên quán  
- Invent code / địa chỉ  
- Full grapheme-prefix dump vào dataset  
- Đổi POI list đã `target_pois_locked` (trừ lỗi adjudicate)

---

## Additional resources

- Operator whitelist + reject table: [operators.md](operators.md)  
- Worked examples by stratum: [examples.md](examples.md)
