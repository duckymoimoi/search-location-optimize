# SEARCH 2.0 — Gold Stage-1 Vietnamese POI Query Variants
## Exploratory Data Analysis (EDA) — `v1.0 Frozen`

## 1. Mục tiêu và phạm vi

`query_variants_v1` là bộ **gold benchmark Stage 1** của SEARCH 2.0, dùng để đánh giá khả năng truy xuất POI **chỉ từ văn bản truy vấn**. Benchmark không sử dụng vị trí hiện tại của người dùng, thời gian, lịch sử hay tín hiệu cá nhân hóa; các tín hiệu đó thuộc Stage 2.

Bộ dữ liệu được thiết kế theo hướng **diagnostic benchmark**: chủ động bao phủ nhiều loại truy vấn và nhiễu quan trọng thay vì mô phỏng tần suất thực tế của traffic production. Vì vậy, tỷ lệ các family/operator trong tài liệu này không nên được diễn giải như phân bố query thật của người dùng.

### 1.1. Chỉ số tổng quan

| Chỉ số | Giá trị | Ghi chú |
| :--- | :--- | :--- |
| Tổng số query | **1,080** | 6 biến thể cho mỗi `case_id` |
| POI mục tiêu | **180** | Chọn từ corpus **186,322 POIs** |
| Đơn vị thống kê độc lập | **180 `case_id`** | Các biến thể trong cùng case có tương quan |
| Sampling strata | **7** | Bao phủ brand, named POI, address, building code, category, cross-region, transit/landmark |
| Macro families | **8** | Clean, alias và các nhóm robustness |
| Variant operators | **23** | Operator đã chuẩn hóa và tách biệt theo taxonomy |
| Severity | **499 CLEAN / 581 SINGLE / 0 COMPOUND** | 100% perturbation dạng lỗi là single-edit |
| Review status | **100% accepted** | Không còn `needs_review` |
| Multi-positive qrels | **17 queries (1.57%)** | Dùng cho intent mơ hồ về mặt text |
| Format | CSV, Parquet | Kèm `manifest.json`, `qrels_policy_v1.json` |
| SHA-256 `query_variants_v1.csv` | `3703931627d4...` | Dùng để khóa phiên bản benchmark |

---

## 2. Cấu trúc POI mục tiêu

### 2.1. Sampling strata

| Sampling stratum | POI | Query | Tỷ lệ | Mục tiêu diagnostic |
| :--- | ---: | ---: | ---: | :--- |
| `brand_branch` | 36 | 216 | 20.00% | Phân biệt chi nhánh cùng thương hiệu bằng street/area |
| `named_clear` | 36 | 216 | 20.00% | Truy xuất POI có tên riêng tương đối đặc trưng |
| `address_street_building` | 28 | 168 | 15.56% | Số nhà, ngõ/ngách/hẻm/kiệt, street formatting |
| `building_code` | 22 | 132 | 12.22% | Mã tòa/căn hộ dạng chữ + số |
| `category_local` | 20 | 120 | 11.11% | Tên quán/dịch vụ kết hợp category và địa danh |
| `explicit_area_cross_region` | 20 | 120 | 11.11% | Disambiguation bằng area khi tên POI dễ trùng vùng |
| `code_transit_landmark` | 18 | 108 | 10.00% | Bến xe, landmark, chùa/di tích, mã rút gọn |
| **Tổng** | **180** | **1,080** | **100%** | |

### 2.2. Phân bố địa lý

180 POI trải trên **19 tỉnh/thành**, được cân bằng tương đối giữa ba vùng lớn:

| Vùng | POI | Tỷ lệ | Tỉnh/thành trong benchmark |
| :--- | ---: | ---: | :--- |
| Miền Bắc | 64 | 35.56% | Hà Nội (39), Bắc Ninh (16), Hải Phòng (6), Ninh Bình (2), Tuyên Quang (1) |
| Miền Nam | 60 | 33.33% | TP.HCM (43), Cần Thơ (9), Đồng Nai (5), An Giang (1), Vĩnh Long (1), Tây Ninh (1) |
| Miền Trung & Tây Nguyên | 56 | 31.11% | Đà Nẵng (18), Lâm Đồng/Đà Lạt (15), Khánh Hòa/Nha Trang (7), Đắk Lắk/Buôn Ma Thuột (6), Gia Lai (4), Thừa Thiên Huế (3), Quảng Trị (2), Hà Tĩnh (1) |

**Diễn giải:** phân bố này giúp giảm nguy cơ benchmark chỉ phản ánh Hà Nội hoặc TP.HCM, nhưng **không phải mẫu đại diện theo dân số hay traffic search toàn Việt Nam**.

---

## 3. Taxonomy biến thể truy vấn

### 3.1. Macro families

| Family | Query | Tỷ lệ | Severity | Mục tiêu |
| :--- | ---: | ---: | :--- | :--- |
| `ORTHOGRAPHIC_IME` | 316 | 29.26% | SINGLE | Không dấu, partial diacritics, Telex leftover, nhầm tone |
| `ALIAS` | 273 | 25.28% | CLEAN | Tên rút gọn, area/address alias, abbreviation, category form |
| `CLEAN` | 180 | 16.67% | CLEAN | Canonical anchor |
| `MECHANICAL_TYPO` | 132 | 12.22% | SINGLE | Adjacent key, lặp/chèn/xóa/đảo ký tự |
| `PHONOLOGICAL` | 103 | 9.54% | SINGLE | Các confusion ngữ âm được kiểm soát |
| `ADDRESS_VARIANT` | 46 | 4.26% | CLEAN/SINGLE | Naturalization và omission trong địa chỉ |
| `TOKEN_EDIT` | 18 | 1.67% | SINGLE | `space_merge`, `space_split` |
| `STRUCTURAL` | 12 | 1.11% | CLEAN | Đảo trật tự từ nhưng giữ nghĩa |
| **Tổng** | **1,080** | **100%** | | |

Tỷ lệ CLEAN/valid variant so với perturbation có lỗi là **46.2% : 53.8%**.

### 3.2. Operator coverage

| Operator | Family | N | % |
| :--- | :--- | ---: | ---: |
| `canonical` | CLEAN | 180 | 16.67 |
| `telex_leftover` | ORTHOGRAPHIC_IME | 138 | 12.78 |
| `strip_diacritics` | ORTHOGRAPHIC_IME | 127 | 11.76 |
| `name_area` | ALIAS | 111 | 10.28 |
| `phonological_confusion` | PHONOLOGICAL | 103 | 9.54 |
| `name_address` | ALIAS | 72 | 6.67 |
| `adjacent_key` | MECHANICAL_TYPO | 44 | 4.07 |
| `short_name` | ALIAS | 39 | 3.61 |
| `double_letter` | MECHANICAL_TYPO | 36 | 3.33 |
| `tone_confuse` | ORTHOGRAPHIC_IME | 26 | 2.41 |
| `char_delete` | MECHANICAL_TYPO | 26 | 2.41 |
| `partial_diacritics` | ORTHOGRAPHIC_IME | 25 | 2.31 |
| `abbreviation` | ALIAS | 25 | 2.31 |
| `char_transpose` | MECHANICAL_TYPO | 22 | 2.04 |
| `address_component_omission` | ADDRESS_VARIANT | 21 | 1.94 |
| `street` | ADDRESS_VARIANT | 16 | 1.48 |
| `category` | ALIAS | 15 | 1.39 |
| `slash_normalize` | ADDRESS_VARIANT | 12 | 1.11 |
| `token_order_variant` | STRUCTURAL | 12 | 1.11 |
| `space_merge` | TOKEN_EDIT | 11 | 1.02 |
| `code_short` | ALIAS | 8 | 0.74 |
| `space_split` | TOKEN_EDIT | 7 | 0.65 |
| `char_insert` | MECHANICAL_TYPO | 4 | 0.37 |

**Lưu ý:** operator có N rất nhỏ, đặc biệt `char_insert`, chỉ nên dùng cho diagnostic định tính hoặc stress check; không nên dùng riêng để kết luận model A tốt hơn model B.

---

## 4. Family × POI stratum

Ma trận này dùng để kiểm tra liệu một family có vô tình tập trung vào một loại POI cụ thể hay không.

| Stratum | CLEAN | ORTHO | ALIAS | MECH | PHONO | ADDR | TOKEN | STRUCT | Tổng |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `brand_branch` | 36 | 47 | 47 | 57 | 15 | 6 | 5 | 3 | 216 |
| `named_clear` | 36 | 66 | 43 | 40 | 15 | 5 | 9 | 2 | 216 |
| `address_street_building` | 28 | 50 | 34 | 5 | 17 | 29 | 4 | 1 | 168 |
| `building_code` | 22 | 39 | 43 | 18 | 10 | 0 | 0 | 0 | 132 |
| `category_local` | 20 | 37 | 34 | 5 | 16 | 4 | 0 | 4 | 120 |
| `explicit_area_cross_region` | 20 | 40 | 37 | 3 | 16 | 2 | 0 | 2 | 120 |
| `code_transit_landmark` | 18 | 37 | 35 | 4 | 14 | 0 | 0 | 0 | 108 |
| **Tổng** | **180** | **316** | **273** | **132** | **103** | **46** | **18** | **12** | **1,080** |

### Nhận xét

- `PHONOLOGICAL`, `ORTHOGRAPHIC_IME` và `ALIAS` có mặt trên toàn bộ 7 strata, phù hợp cho phân tích robustness ở mức family.
- `MECHANICAL_TYPO` tập trung nhiều hơn ở `brand_branch` và `named_clear`; nên đọc score family cùng score theo stratum.
- `ADDRESS_VARIANT` tập trung chủ yếu ở `address_street_building`, phù hợp với mục tiêu của family.
- `TOKEN_EDIT` và `STRUCTURAL` có số lượng thấp; nên xem là diagnostic slices thay vì headline metrics.

---

## 5. Severity và tính kiểm soát perturbation

| Family | CLEAN | SINGLE | Tổng |
| :--- | ---: | ---: | ---: |
| `CLEAN` | 180 | 0 | 180 |
| `ALIAS` | 273 | 0 | 273 |
| `STRUCTURAL` | 12 | 0 | 12 |
| `ADDRESS_VARIANT` | 34 | 12 | 46 |
| `ORTHOGRAPHIC_IME` | 0 | 316 | 316 |
| `MECHANICAL_TYPO` | 0 | 132 | 132 |
| `PHONOLOGICAL` | 0 | 103 | 103 |
| `TOKEN_EDIT` | 0 | 18 | 18 |
| **Tổng** | **499** | **581** | **1,080** |

Không có query `COMPOUND`. Điều này giúp attribution rõ hơn: nếu model fail ở một perturbation, nguyên nhân dễ truy ngược về operator/family hơn so với query chứa nhiều lỗi đồng thời.

---

## 6. Biên độ phép biến đổi

- `char_edit_distance`: Levenshtein distance ở mức ký tự.
- `norm_char_edit_distance`: `Lev(canonical, query) / max(len(canonical), len(query))`.
- `token_retention_ratio`: tỷ lệ token canonical còn xuất hiện trong query.
- `token_count_delta`: chênh lệch số token giữa variant và canonical.

| Family | Char edit mean / max | Norm edit mean / max | Token retention mean / min | Token delta mean |
| :--- | :---: | :---: | :---: | ---: |
| `MECHANICAL_TYPO` | 1.17 / 2 | 0.042 / 0.154 | 82.4% / 66.7% | 0.00 |
| `TOKEN_EDIT` | 1.28 / 3 | 0.043 / 0.100 | 75.8% / 60.0% | -0.17 |
| `PHONOLOGICAL` | 1.60 / 3 | 0.049 / 0.154 | 85.7% / 66.7% | 0.00 |
| `ORTHOGRAPHIC_IME` | 3.66 / 11 | 0.109 / 0.312 | 63.4% / 0.0% | 0.00 |
| `ADDRESS_VARIANT` | 8.65 / 28 | 0.259 / 0.800 | 77.6% / 37.5% | -1.09 |
| `STRUCTURAL` | 12.75 / 16 | 0.377 / 0.538 | 97.9% / 75.0% | -0.08 |
| `ALIAS` | 15.55 / 33 | 0.453 / 0.955 | 59.6% / 0.0% | -0.60 |
| `CLEAN` | 0 / 0 | 0 / 0 | 100% / 100% | 0.00 |

Các chỉ số này cho phép phân tích `Recall@K` theo mức perturbation thay vì chỉ theo nhãn family.

**Lưu ý:** edit distance là thước đo hình thức; với alias/structural variant, edit distance cao không đồng nghĩa intent thay đổi nhiều về ngữ nghĩa.

---

## 7. Độ khó so với corpus

Hardness được xác định dựa trên mức cạnh tranh của target trong corpus: trùng tên chuẩn hóa, quy mô brand và cụm địa chỉ/mã hiệu tương tự.

| Tier | POI | Query | % | Diễn giải |
| :--- | ---: | ---: | ---: | :--- |
| `EASY` | 84 | 504 | 46.67 | Target tương đối đặc trưng/ít collision |
| `MEDIUM` | 11 | 66 | 6.11 | Khoảng 2 candidate tương tự |
| `HARD` | 38 | 228 | 21.11 | Cụm khoảng 3–9 candidate cạnh tranh |
| `VERY_HARD` | 47 | 282 | 26.11 | Chuỗi lớn hoặc cụm có >=10 candidate/branch cạnh tranh |
| **Tổng** | **180** | **1,080** | **100%** | |

Gần một nửa benchmark (**47.22%**) nằm trong `HARD + VERY_HARD`, nên benchmark có đủ candidate collision để phân biệt các retriever chứ không chỉ kiểm tra exact-name lookup.

### Yêu cầu tái lập

Rule tạo hardness tier nên được version hóa trong script/manifest, bao gồm:
- normalization dùng cho `name_fold`;
- định nghĩa `brand size`;
- ngưỡng EASY/MEDIUM/HARD/VERY_HARD;
- cách xử lý POI thiếu brand hoặc address.

---

## 8. Qrels và multi-positive intent

| Số acceptable POI | Query | Tỷ lệ |
| :--- | ---: | ---: |
| 1 | 1,063 | 98.43% |
| 2 | 9 | 0.83% |
| 3–5 | 6 | 0.56% |
| >5 | 2 | 0.19% |

Max cardinality là **10 POIs**.

17 multi-positive query gồm:
- `brand_branch`: 10;
- `category_local`: 7.

Khi benchmark, nên report song song:
- **StrictTargetRecall@K**: target cụ thể phải xuất hiện;
- **AcceptableRecall@K**: bất kỳ POI nào trong `acceptable_poi_ids` được tính đúng.

Điều này tránh phạt Stage 1 trong trường hợp query text thực sự mơ hồ, nhưng vẫn giữ metric nghiêm ngặt để phân tích branch-level retrieval.

---

## 9. Độ dài và ngôn ngữ

### 9.1. Độ dài query

- Character length: min **11**, median **32**, mean **31.70**, Q1 **27**, Q3 **36**, max **56**.
- Token count: min **3**, median **7**, mean **6.85**, Q1 **6**, Q3 **8**, max **12**.

Benchmark này chủ yếu chứa query có đủ tín hiệu nhận diện POI. Prefix/autocomplete nên được đánh giá bằng prefix deterministic sinh từ query đã khóa.

### 9.2. Ngôn ngữ

| Ngôn ngữ | Query | Tỷ lệ |
| :--- | ---: | ---: |
| `lang_vi` | 714 | 66.11% |
| `lang_mixed` | 348 | 32.22% |
| `lang_en` | 18 | 1.67% |

18 query `lang_en` đến từ 3 POI: `Harley-Davidson of Saigon`, `Old Propaganda Posters`, `The Adora Center`.

**Diễn giải:** nhóm này đủ làm English smoke test, nhưng **chưa đủ để dùng như benchmark độc lập cho năng lực retrieval tiếng Anh**. Khả năng Việt–Anh nên đọc chủ yếu từ `lang_mixed` và English-only như một slice nhỏ.

---

## 10. Query-type tags

| Tag | N |
| :--- | ---: |
| `street` | 870 |
| `name_area` | 784 |
| `lang_vi` | 714 |
| `partial` | 581 |
| `typo` | 581 |
| `landmark` | 408 |
| `lang_mixed` | 348 |
| `brand` | 276 |
| `address` | 221 |
| `exact_name` | 180 |
| `category` | 128 |
| `code` | 121 |
| `name_address` | 72 |
| `short_name` | 59 |
| `abbreviation` | 25 |
| `lang_en` | 18 |

`partial` và `typo` cùng bằng 581 vì tương ứng với toàn bộ nhóm `SINGLE`; `exact_name=180` khớp đúng một canonical cho mỗi `case_id`.

---

## 11. Giao thức thống kê

1,080 query **không phải 1,080 quan sát độc lập**. Mỗi `case_id` chứa 6 variants có tương quan.

- statistical unit = **`case_id`**;
- confidence interval và bootstrap phải **cluster theo `case_id`**;
- không bootstrap độc lập trên 1,080 rows.

### Ba mức báo cáo

**Micro Query Score**

\[
Score_{micro}=\frac{1}{1080}\sum_{i=1}^{1080}Metric(q_i)
\]

**Macro-Family Score**

\[
Score_{macro-family}
=\frac{1}{8}\sum_{f=1}^{8}
\left(\frac{1}{|Q_f|}\sum_{q\in Q_f}Metric(q)\right)
\]

**Macro-Case Score**

\[
Score_{macro-case}
=\frac{1}{180}\sum_{c=1}^{180}
\left(\frac{1}{6}\sum_{v=1}^{6}Metric(q_{c,v})\right)
\]

**Lưu ý:** do mỗi case hiện có đúng 6 variants, Micro Query Score và Macro-Case Score có thể bằng nhau đối với metric tuyến tính ở cấp query. Macro-Case vẫn là đơn vị phù hợp cho bootstrap/CI và hữu ích nếu số variants/case thay đổi ở phiên bản sau.

---

## 12. Khuyến nghị sử dụng cho lựa chọn Stage-1 model

Phần này là **khuyến nghị benchmark**, không phải mô tả phân bố dữ liệu.

### Primary metrics — candidate retrieval

Vì Stage 1 chuyển candidate sang Stage 2, ưu tiên:
- `AcceptableRecall@100`
- `AcceptableRecall@500`
- `AcceptableRecall@1000`
- `K@95`
- `K@98`

### Diagnostic metrics

- `StrictTargetRecall@K`
- `SR@1/5/10`
- `MRR@10`
- score theo `family`, `stratum`, `hardness tier`, `language`
- `Recall@K` theo `norm_char_edit_distance`

### Prefix/autocomplete

Sinh prefix deterministic từ query frozen để tính:
- `FHC-char@1/5/10`
- `SHC-char@1/5/10`
- `PrefixAUC@5/10`

Không cần lưu mỗi prefix như một row độc lập trong gold set.

---

## 13. Giới hạn diễn giải

Benchmark này phù hợp để **screening và so sánh zero-shot Stage-1 retrievers**, nhưng không nên dùng để suy ra trực tiếp:

1. **Production accuracy tuyệt đối** — family/operator được curated, không theo traffic thật.
2. **Phân bố lỗi thực tế của người dùng** — tỷ lệ IME/typo/alias là design choice.
3. **English retrieval tổng quát** — chỉ có 18 English-only queries từ 3 cases.
4. **Geo/personalization quality** — benchmark cố ý không dùng origin, distance, time hay history.
5. **ANN serving quality** — nếu model selection dùng exact search, ANN cần benchmark riêng sau khi shortlist representation.

Khi có query/click logs thật, nên bổ sung một **naturalistic evaluation set** có distribution gần production và giữ gold set này làm **diagnostic stress set**.

---

## 14. Kết luận

`query_variants_v1` đã phù hợp để khóa làm **Stage-1 diagnostic gold benchmark**:

- 180 independent cases và 1,080 query variants;
- taxonomy 8 families / 23 operators;
- perturbation được kiểm soát, không có compound noise;
- qrels hỗ trợ multi-positive cho query mơ hồ;
- coverage theo stratum, region, corpus hardness và language;
- protocol thống kê xác định `case_id` là đơn vị độc lập.

Từ thời điểm này, giá trị thực nghiệm lớn hơn đến từ **chạy benchmark trên nhiều model và phân tích failure slices** hơn là tiếp tục chỉnh sửa benchmark. Chỉ nên thay đổi `v1.0 Frozen` khi phát hiện lỗi factual/qrel rõ ràng; các mở rộng coverage nên tạo phiên bản mới hoặc stress set bổ sung.
