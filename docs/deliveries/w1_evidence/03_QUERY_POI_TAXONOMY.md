# SEARCH 2.0 — Query / POI Taxonomy (W1)

**SoT authoring:** `docs/specs/SEARCH_2.0_STAGE1_QUERY_VARIANT_STANDARD.md`  
**Operator whitelist:** `.cursor/skills/search20-stage1-query-variants/operators.md`  
**Locked data:** `gold_stage1_v1`

Taxonomy dùng chung cho (1) gắn nhãn gold, (2) slice benchmark, (3) map sang error taxonomy.

---

## 1. Đơn vị

| Khái niệm | Định nghĩa |
|---|---|
| `case_id` | Một intent → một POI đích (gold: `g150-001`…`g150-180`) |
| `variant_id` | Một query text thuộc case (`…-v1`…`…-v6`) |
| `intended_poi_id` | POI đích chính |
| `acceptable_poi_ids` | Tập chấp nhận Stage 1 (thường = {intended}; multi-positive khi text mơ hồ) |

**Không dùng** origin–POI pair làm đơn vị Stage 1.

---

## 2. POI taxonomy — sampling strata

| Stratum | Intent điển hình | Canonical gợi ý |
|---|---|---|
| `named_clear` | Tên riêng đủ nhận diện | Tên POI (+ khu nếu trùng) |
| `brand_branch` | Thương hiệu + chi nhánh | `{brand} {ward\|street\|khu}` — cấm bare multi-branch |
| `category_local` | Quán/dịch vụ local | **Tên POI thật**, không bịa `category+ward` |
| `address_street_building` | Số nhà + đường | `{housenumber} {street}` giữ `/` nếu có |
| `building_code` | Mã tòa/căn | Mã + đủ context (S3.01, Landmark…) |
| `explicit_area_cross_region` | Tên dễ trùng vùng | Tên/brand + ward hoặc province trong text |
| `code_transit_landmark` | Bến / landmark / di tích | Tên địa điểm chuẩn |

### POI attributes dùng để gắn stratum / hardness

`name`, `brand`, `category`, `housenumber`, `street`, `province`, `subdistrict`, `address_status`, folded-name collision size.

---

## 3. Query taxonomy — macro families

| Family | Bản chất | Severity gold |
|---|---|---|
| `CLEAN` | Canonical / hình thức chuẩn | CLEAN |
| `ALIAS` | Viết tắt, short name, name+area/address, category form, code_short | CLEAN |
| `ORTHOGRAPHIC_IME` | Không dấu, partial diacritics, Telex leftover, nhầm tone | SINGLE |
| `MECHANICAL_TYPO` | Phím kề, insert/delete/transpose, double letter | SINGLE |
| `PHONOLOGICAL` | Confusion ngữ âm kiểm soát (`s↔x`, `tr↔ch`…) | SINGLE |
| `ADDRESS_VARIANT` | Ngõ/hẻm/kiệt, omission component, slash normalize | CLEAN/SINGLE |
| `TOKEN_EDIT` | `space_merge` / `space_split` | SINGLE |
| `STRUCTURAL` | Đảo trật tự từ, giữ entity | CLEAN |

Gold **không** dùng `COMPOUND` (nhiều lỗi chồng).

---

## 4. Query taxonomy — operators (whitelist rút gọn)

### CLEAN
`canonical`

### ORTHOGRAPHIC_IME
`strip_diacritics` · `partial_diacritics` · `tone_confuse` · `telex_leftover`

### MECHANICAL_TYPO
`adjacent_key` · `char_delete` · `char_insert` · `char_transpose` · `double_letter` (± `char_substitute`)

### PHONOLOGICAL
`phonological_confusion`

### ALIAS
`short_name` · `abbreviation` · `name_area` · `name_address` · `code_short` · `category` · (± bilingual)

### ADDRESS_VARIANT
`slash_normalize` · `address_component_omission` · `street` / housenumber format

### TOKEN_EDIT / STRUCTURAL
`space_merge` · `space_split` · `token_order_variant`

### PREFIX (không lưu full chuỗi trên gold)
`char_prefix` / `token_prefix` — sinh lúc benchmark.

---

## 5. Query-type tags (multi-label)

Dùng để slice, **không** thay family/operator:

`exact_name` · `partial` · `typo` · `brand` · `address` · `street` · `landmark` · `category` · `code` · `short_name` · `abbreviation` · `name_area` · `name_address` · `lang_vi` · `lang_en` · `lang_mixed`

---

## 6. Map query → intent → target

```text
query_text
  → family + operator + tags
  → case_id (intent)
  → intended_poi_id ∈ corpus
  → acceptable_poi_ids  (1..k)
```

| Tình huống text | Qrels |
|---|---|
| Đủ disambiguation một POI | `{intended}` |
| Brand/category còn mơ hồ về mặt chữ | multi-positive (sparse; brand-first policy) |
| Building code trùng | **không** auto-expand trên v1 |

---

## 7. Hardness tiers (corpus-relative)

| Tier | Ý nghĩa ngắn |
|---|---|
| EASY | Ít collision folded-name / brand nhỏ |
| MEDIUM | ~2 candidate tương tự |
| HARD | Cụm ~3–9 |
| VERY_HARD | Chuỗi lớn / ≥10 branch hoặc cụm địa chỉ dày |

Dùng để breakdown — không phải stratum chọn mẫu.

---

## 8. Ranh giới Stage 1 vs Stage 2 trong taxonomy

| Thuộc taxonomy Stage 1 | Thuộc Stage 2 (không gắn nhãn gold text) |
|---|---|
| Family / operator / stratum / tags ngôn ngữ | origin distance, time-of-day, repeat user |
| Acceptable set theo **chữ** | “Vincom *của tôi*” theo lịch sử |
| Same-name *có mặt trong top-K* | Same-name *đứng #1 đúng chỗ* |
