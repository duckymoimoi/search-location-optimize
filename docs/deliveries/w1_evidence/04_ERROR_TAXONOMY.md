# SEARCH 2.0 — Error Taxonomy (W1)

**Nguồn khung:** ba nguồn khó trong [`search2.0.md`](../../specs/search2.0.md) §2  
**Ánh xạ evaluation:** Stage 1 gold (`gold_stage1_v1`) + giả thuyết cho Stage 2 / data

Taxonomy lỗi dùng để: soi failure, chọn metric W2, ưu tiên experiment W3–W4.

---

## 0. Nguyên tắc

1. Một failure gắn **một primary class** (nguồn gốc), có thể kèm secondary.
2. Tách **lỗi mô hình** khỏi **lỗi dữ liệu** và **lỗi định nghĩa qrels**.
3. Stage 1 chỉ chịu trách nhiệm lớp **E1** (văn bản → candidate). Lớp **E2** không phạt Stage 1 nếu candidate đúng đã có trong top-K.

---

## 1. Lớp lỗi theo stage

```text
E0  Data / catalog          → thiếu POI, bẩn, near-dup, sai địa chỉ
E1  Stage-1 retrieval       → không đưa đúng POI vào candidate set (text)
E2  Stage-2 ranking         → có candidate đúng nhưng xếp sai chỗ / sai ngữ cảnh
E3  Business / UX           → dedup, filter, fallback, latency, empty state
E4  Eval / label            → qrels sai, multi-positive thiếu/thừa, query lệch intent
```

---

## 2. Chi tiết E1 — Stage 1 (trọng tâm W1–W3)

### E1.A — Surface / orthography miss
Query đúng intent nhưng hình thức lệch: không dấu, Telex, typo cơ học, phonological.  
**Gold slice:** `ORTHOGRAPHIC_IME`, `MECHANICAL_TYPO`, `PHONOLOGICAL`, `TOKEN_EDIT`.  
**Metric:** Recall@K theo family; Recall theo `norm_char_edit_distance`.

### E1.B — Alias / paraphrase miss
Người dùng dùng short name, viết tắt, name+area, category form, mã rút gọn.  
**Gold slice:** `ALIAS`, một phần `STRUCTURAL`.  
**Metric:** AcceptableRecall; StrictTarget khi alias vẫn unique.

### E1.C — Address / code structure miss
Sai hoặc yếu trên số nhà, ngõ/hẻm/kiệt, slash, mã tòa.  
**Gold slice:** `ADDRESS_VARIANT`, stratum `address_street_building`, `building_code`.  
**Metric:** Recall theo stratum + operator `slash_normalize` / `code_short`.

### E1.D — Ambiguity under-specified (text)
Query chữ **đúng nhưng chưa đủ** để chọn 1 POI (bare brand, generic).  
**Không phải lỗi model nếu** qrels multi-positive và bất kỳ acceptable nào vào top-K.  
**Là lỗi model nếu** không có member nào của acceptable set.  
**Gold:** 17 multi-positive rows; stratum `brand_branch`.

### E1.E — Wrong entity (intent drift)
Model kéo về POI khác nghĩa (sai số nhà, sai đường, brand khác).  
**Phân biệt với E1.D:** intended không vào top-K *và* các kết quả top không nằm acceptable.  
**Metric:** miss @K + qualitative audit.

### E1.F — Long-tail / rare surface
POI có tên hiếm, mixed VI–EN, digit trong tên; embedding/lexical chưa cover.  
**Gold slice:** `lang_en`/`lang_mixed`, `named_clear` HARD+.

---

## 3. Chi tiết E2 — Stage 2 (định nghĩa sớm, đo từ W4)

### E2.A — Geo mis-rank
Đúng chữ nhiều chi nhánh; xếp xa user lên trước gần user.  
**Ví dụ search2.0:** `sư vạn hạnh` đứng Q10.

### E2.B — Temporal mis-rank
Sai giờ mở cửa / pattern theo time-of-day.

### E2.C — Personalization miss
User cũ: không ưu tiên chi nhánh quen (`vincom` của họ).

### E2.D — Popularity bias
Over-weight head brand → đè long-tail đúng hơn về geo/text.

### E2.E — Missing context handled badly
Thiếu GPS mà hệ thống coi distance=0 hoặc trả empty sai.

---

## 4. Chi tiết E0 — Data

| Code | Mô tả | Bằng chứng corpus |
|---|---|---|
| E0.1 Missing address | Không `direct` / thiếu hn+street | 52.6% thiếu address_status |
| E0.2 Same-name collision | Nhiều POI một folded name | 27.7% POI in groups ≥2 |
| E0.3 Near-dup | Node–way / gần nhau cùng fold | 1,508 node–way ≤80m |
| E0.4 Junk / generic name | `a`, `sua xe`, `tap hoa`… | top ambiguous list |
| E0.5 Geo anomaly | Ngoài bbox / province unknown | 31 + 333 |
| E0.6 Coverage gap | POI thật chưa có trong OSM corpus | ngoài đo — giả thuyết |

---

## 5. Chi tiết E3 / E4

| Code | Mô tả |
|---|---|
| E3.1 Dedup fail | Hai bản ghi một chỗ hiện hai lần |
| E3.2 Over-filter | Business rule loại mất POI đúng |
| E3.3 Fallback gap | Tầng lỗi → trắng kết quả |
| E3.4 Latency abort | User thoát trước khi có gợi ý |
| E4.1 Bad qrel | Acceptable sai fact |
| E4.2 Under-labeled MP | Query mơ hồ nhưng chỉ 1 ID |
| E4.3 Over-labeled MP | Acceptable quá rộng → metric ảo |

---

## 6. Map family gold → error class (primary)

| Query family / tình huống | Primary error nếu fail Stage 1 |
|---|---|
| ORTHOGRAPHIC_IME / MECHANICAL_TYPO / PHONOLOGICAL | E1.A |
| ALIAS / STRUCTURAL | E1.B |
| ADDRESS_VARIANT / building_code / address stratum | E1.C |
| Bare brand + MP | E1.D (hoặc pass nếu bất kỳ acceptable∈top-K) |
| CLEAN canonical miss | E1.E hoặc E0.* |
| Đúng top-K nhưng user chọn nhầm chỗ (có GPS) | **E2.*** — không đổ Stage 1 |

---

## 7. Metric gợi ý theo lớp (W2)

| Lớp | Metric chính |
|---|---|
| E1.* | AcceptableRecall@100/500/1000, K@95/98, slice theo family/stratum |
| E1 vs nhầm nhãn | StrictTargetRecall song song |
| E2.* | MRR/SR@k, distance-to-selected, segment geo/time |
| E0.* | Tỷ lệ field missing, near-dup rate, coverage audits |
| E4.* | Audit mẫu qrels, MP cardinality distribution |

---

## 8. Giả thuyết ưu tiên (từ EDA)

1. **E1.D + E2.A** cùng xuất hiện trên brand/same-name — tách stage là bắt buộc.  
2. **E1.A** sẽ tách BM25 vs dense rõ trên gold (53.8% SINGLE).  
3. **E0.1/E0.3** đặt trần — cải model không thay thế cleaning/dedup.  
4. **E4.2** rủi ro thấp trên v1 (chỉ 17 MP) nhưng phải giữ dual recall.
