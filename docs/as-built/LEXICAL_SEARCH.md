# Tìm kiếm lexical — as-built

Cập nhật: **2026-09-26**. Policy đang chạy: `search-policy-stable-demo-v12`.

Tài liệu này mô tả nhánh lexical của Stage-1 POI search: cách query được
phân tích, field nào trên Elasticsearch được dùng, clause nào được bật, và
núm nào là hyperparameter theo hành vi gõ. Đây là runtime as-built, không
phải contract địa chỉ đích (`ADDRESS_NUMERIC_FALLBACK.md`) và không phải
báo cáo Gold.

Code: `apps/poi-search/api/lexical.py`, `textnorm.py`, `search_policy.json`.
Index: `apps/poi-search/scripts/index_vn_poi.py`. Ranker đọc tín hiệu tên
từ cùng bộ chuẩn hóa: `ranking.name_match_class`.

## 1. Vai trò trong hybrid

Mỗi `/v1/suggest` lấy tối đa `branch_depth` (50) ứng viên lexical và, nếu
query đủ dài, 50 ứng viên dense (mE5-small ANN). Hai danh sách gộp bằng
RRF `k=60`. Ranker heuristic (geo v6, name-match, nearby rescue) sắp xếp
lại trên tập đã gộp — không viết lại điểm BM25.

```text
query
  ├─ textnorm (fold, glue code, parse cấu trúc)
  ├─ lexical_body  → ES bool/should, size 50
  ├─ dense ANN     → chỉ khi compact_length ≥ dense_min_compact_chars (5)
  ├─ RRF
  └─ ranker (name_match_class, geo, rescue)
```

Ba profile: `hybrid` (mặc định), `lexical_only`, `dense_only`. Query ngắn hơn
5 ký tự compact (`ga`, `kfc`) đi `lexical_short_query` — dense tắt vì encoder
không ổn định trên chuỗi quá ngắn.

Lexical chịu: khớp exact/prefix tên, số nhà + đường, mã tòa (`S2.02`),
tên dính chữ (`vanhanhmall`), typo nhẹ trên token chữ. Dense chịu:
alias/nghĩa gần, nhiễu do người gõ, brand khi token đường át tên.

## 2. Nguyên tắc

1. **Không hardcode tên POI.** Không danh sách “Vạn Hạnh”, “Jollibee”,
   không cặp bigram cố định. Mọi nhánh extra dựa trên *hình thái* token
   (chữ / số / mã) hoặc khóa đã materialize từ chính name/alias.
2. **Parse topology, không lexicon loại đường.** `ngõ`, `/`, `-` giữa hai
   atom số nhà là keo. Số nằm giữa hai cụm chữ (`đường 3 tháng 2`) là số
   trong tên, không phải house path.
3. **Số và mã không được fuzzy, không vào IDF.** Số nhà exact trên field
   catalog. Mã letter+digit đi `codes_compact`. Số thuần cạnh chữ là
   `constant_score` bonus, không phải term BM25.
4. **MSM = 1.** Một clause `should` đủ để vào tập ứng viên. MSM ≥ 2 từng
   làm rỗng nhiều query Gold.
5. **Núm boost là hành vi user.** `fuzzy`, `name_compact`, `exact`… chỉnh
   theo cách người gõ (dính chữ, typo, bỏ dấu), không fit vào Gold. Gold
   v2.1 / brand v1 là cổng “đừng làm hỏng”; 36k train-v6 là diagnostic
   authored, không phải test khóa.

## 3. Chuẩn hóa query

Toàn bộ nằm trong `textnorm.py`. Encoder dense nhận query gốc (sau
NFKC/space); rewrite chỉ thêm clause lexical, không thay input model.

| Hàm | Việc |
|---|---|
| `fold` | NFKC, `đ→d`, bỏ dấu, lowercase, gộp space |
| `glue_code_spans` | `s10.2` / `s1-02` → một token `s102`. Gạch chéo **không** dính: `16/2` vẫn `16/2` |
| `text_tokens` | Tách token; giữ `/` `-` trong số nhà và mã |
| `_token_kind` | `letter` · `number` · `code` (vừa chữ vừa số) · `other` |
| `parse_query_structure` | House path đầu câu / trong câu, cụm chữ tên đường, số medial |
| `query_code_compacts` | Mỗi token letter+digit → một khóa `s202` |
| `query_name_compacts` | Chỉ khi query *trông như* dính chữ (xem §6) |
| `query_fuzzy_terms` | Token chữ dài ≥ 4. Bỏ số, mã, âm tiết 1–3 chữ |
| `expand_query` | `bv`→bệnh viện, `dh`→đại học, `thpt`/`thcs` — một alternative |

Phân loại atom số nhà: digit-leading (`15`, `15A`) là house. Letter-leading
(`B12`, `s10`) là code.

## 4. Analyzer và field index

Analyzer `vi_folded`: char filter `đ→d` + `standard` + `lowercase` +
`asciifolding`. Prefix name dùng `vi_prefix` (edge-ngram 1–20, search bằng
`vi_folded`).

| Field | Type | Dùng để |
|---|---|---|
| `search_label` / `.prefix` | text | BM25, phrase, prefix n-gram |
| `search_aliases` / `.prefix` | text | Như trên, boost thấp hơn |
| `label_folded` / `aliases_folded` | keyword | Exact cả chuỗi đã fold; prefix cả query |
| `address` | text | Phrase slop 2, cross-field |
| `street` / `place` | text | Cụm đường / khu |
| `street_folded` / `place_folded` | keyword | Exact cụm đường đã fold |
| `housenumber` | keyword | `259/15` nguyên dạng |
| `housenumber_path_key` | keyword | `259 15` — slash và `259 ngõ 15` chung khóa |
| `codes_compact` | keyword | Alnum fold: `S2.02` = `s202` |
| `names_compact` | keyword | Letter-only fold cả name/alias, dài ≥ 6: `vanhanhmall` |
| `context_text` | text | Cross/best OR phụ |
| `destination_searchable` | boolean | Filter bắt buộc |

Không có synonym graph, không có pair-index, không có street-type word list.

`names_compact` luôn được ghi từ name + alias lúc index (hoặc backfill
`scripts/backfill_names_compact.py`). Query *chỉ emit* khóa đó khi thỏa
cổng dính chữ — index không tự biến `van hanh mall` thành hit compact.

## 5. Query DSL

`lexical_body(query, size)` là một `bool` + `filter: destination_searchable`
+ `should` + `minimum_should_match: 1`. Sort `_score desc`, `canonical_id
asc`. Không `_source` lúc retrieve.

Nhánh luôn có:

| Clause | Field / kiểu | Boost v12 |
|---|---|---:|
| Exact name | `term` `label_folded` | 20 |
| Exact alias | `term` `aliases_folded` | 16 |
| Phrase name | `match_phrase` `search_label` slop 1 | 10 |
| Phrase address | `match_phrase` `address` slop 2 | 6 |
| Cross-fields OR | label/alias/address/street/place/context, MSM 50% | 5 |
| Best-fields OR | label/address/street/context | 2 |

Nhánh có điều kiện:

| Khi nào | Clause | Boost |
|---|---|---:|
| Không phải house+street | Prefix n-gram trên name/alias | 8 |
| Folded query ≥ 2 ký tự và không house+street | `prefix` `label_folded` / `aliases_folded` | 10 / 8 |
| Có số thuần cạnh chữ | `constant_score` phrase số trên label/alias/address/context | 1.5 / số |
| Có letter-run ≥ 2 cạnh số | Phrase run đó trên label (nếu không house+street), address, street, place | 10 / 6 / 8 |
| Parse ra path keys | `term` `housenumber_path_key` + `housenumber` | 20 / 16 |
| `named_letters` ≥ 2 | Phrase + term folded street/place | 8 |
| Token letter+digit | `terms` + `prefix` (≥3) trên `codes_compact` | 14 / 9.8 |
| Query dính chữ (§6) | `constant_score` `names_compact` | 24 |
| Rewrite khác query gốc | Cross-fields + (nếu có số) phrase/house/bonus trên bản mở rộng | 2 + như trên |
| Có token chữ ≥ 4 | Fuzzy `best_fields` name/alias, fuzziness 1, `prefix_length` 1, max 40 expansions | 3 |

House+street **tắt** prefix trên name và hạ `search_label` trong cross-fields
(`^8` → `^3`) để POI mang số nhà trong *tên* không đè exact member trên
cùng đường.

BM25 letters-only khi house path đang chạy: số nhà không vào IDF. Số medial
trong tên (`đường 3 tháng 2`) **ở lại** BM25, không nhận `number_bonus`.

Fuzzy không đụng số, mã, house key, address field. Boost 3 < exact (20) và
`name_compact` (24) nên typo không thắng tên đúng.

## 6. Các dạng query

Phân theo topology, không theo tên thương hiệu.

### Tên / alias sạch

`Vạn Hạnh Mall`, `van hanh mall` → exact/phrase/BM25. Không emit
`names_compact` vì mọi token chữ đều ngắn (âm tiết tiếng Việt).

### Tên dính chữ

`vanhanh mall`, `vanhanhmall`. `query_name_compacts` bật khi khóa letter-only
≥ 6 **và** (token chữ dài nhất ≥ 7, hoặc chỉ một token và khóa ≥ 8).

- `vanhanh` (7) + `mall` → emit `vanhanhmall`
- một token `vanhanhmall` (11) → emit
- `nguyen` (6) trong `23 nguyen trai` → **không** emit — tránh street compact
  đè house+street
- query có house atom (`11 vanhanh mall`) → ranker cũng không coi là
  tương đương tên

### Số nhà + đường

`259/15 Nguyễn Chí Thanh`, `259 ngõ 15 Nguyễn Chí Thanh` → path key `259 15`.
`30/48D` → `30 48d`. Prefix name tắt.

`Highlands 259` (số không dẫn đầu, không đủ chữ đường sau số) **không** vào
house path.

`WinMart 30/48D Nguyễn Văn Linh` — path nằm giữa câu vẫn được lấy nếu sau
path còn ≥ 2 chữ.

### Số trong tên đường

`Đường 3 Tháng 2` — số medial, BM25 giữ nguyên, không `housenumber_path_key`,
không `number_bonus`.

### Mã tòa / căn

`S2.02`, `s10.2`, `B12` → `codes_compact`. Prefix `s20` có thể kéo `s202`.
Không fuzzy.

### Typo nhẹ

`Hia Bạ Trưn` — token chữ ≥ 4 vào fuzzy edit-1, chỉ name/alias. Âm tiết 3
chữ (`dao`, `chi`) bỏ qua.

### Viết tắt cơ quan

`bv 108` → lexical thêm `bệnh viện 108`; encoder vẫn thấy `bv 108`.

## 7. Núm policy

Toàn bộ boost đọc từ `search_policy.json` → `POLICY["lexical"]`. Đổi JSON
rồi restart API (container demo không `--reload`). Không cần reindex trừ khi
đổi analyzer hoặc thêm field.

| Key | v12 | Ý nghĩa thực tế |
|---|---:|---|
| `exact` / `alias_exact` | 20 / 16 | Tên/alias gõ đúng (đã fold) |
| `name_compact` | 24 | Cứu query dính chữ; gần im trên query cách sẵn |
| `housenumber_path` / `_exact` | 20 / 16 | Exact member theo catalog |
| `code_compact` | 14 | Mã alnum |
| `phrase` / `phrase_address` / `phrase_street` | 10 / 6 / 8 | Thứ tự token |
| `prefix_field` / `leading_prefix` | 8 / 10 | Gõ dở |
| `fuzzy` | 3 | Typo 1 ký tự trên token chữ ≥ 4 |
| `cross_or` / `best_or` | 5 / 2 | Recall rộng |
| `number_bonus` | 1.5 | Cộng điểm số, không IDF |
| `minimum_should_match` | 1 | Sàn recall |

Chỉnh núm = giả thuyết về hành vi user, rồi đo:

- Gold v2.1 + brand v1: cổng lock (POI Hit@1/20/50 và q01 Hit@1 không tụt
  quá 1 điểm phần trăm so W2).
- `train_stage1_queries_v6` (36k, slot v01–v06): diagnostic authored,
  zero-shot. Runner:
  `apps/poi-search/bench/train_stage1_v6_36k_lexical_diag.py`.

Quan sát trên 36k (lexical raw, cùng index v3): compact gần như không
đổi điểm tổng; `fuzzy=3` kéo slot typo (`v03–v05`); `fuzzy=6` mất @1 trên
query sạch/`v06`. Đó là minh họa núm, không phải lý do khóa v12.

## 8. Ranker đụng lexical

`name_match_class` không phải retrieval. Nó quyết định khi nào hai POI
“cùng lớp tên” để geo được phép đảo thứ tự, và khi nào exact name được
bảo vệ.

- Phrase liền trên name/alias: level 3 (full), 2 (complete span), 1 (prefix
  token cuối).
- Letter-compact bằng nhau, không có house atom → level 3. Vì vậy
  `vanhanh mall` và `Vạn Hạnh Mall` cùng lớp sau khi compact đã kéo POI
  vào ứng viên.
- Match chỉ trên address, hoặc chỉ nhờ fuzzy, **không** tạo lớp tương đương.

Nearby name rescue (bán kính 5 km khi có origin) cũng lọc bằng exact/prefix
fold hoặc `name_match_class` — không dùng cross-field yếu trong bbox.

## 9. Việc lexical *không* làm

- Không resolve “số nhà chưa có trong catalog” thành fallback scope. Đó là
  contract đích: [`../specs/ADDRESS_NUMERIC_FALLBACK.md`](../specs/ADDRESS_NUMERIC_FALLBACK.md).
  Runtime hiện chỉ exact trên field đã index.
- Không rewrite query cho encoder; không train dense để bỏ qua số sai.
- Không synonym thương hiệu, không POI-name list, không identity-lock theo
  danh sách brand.
- Không thay Gold hay viết lại staging query 003–011.

## 10. Đổi và kiểm

```text
sửa textnorm / lexical     → unit: apps/poi-search/api/test_geo_algorithms.py
sửa boost JSON             → restart API; không reindex
thêm field / analyzer      → index_vn_poi.py (+ backfill nếu chỉ thêm keyword)
cổng lock                  → bench/gold_stage1_v21_docker_baseline.py
                             bench/gold_stage1_brand_v1_docker_baseline.py
diagnostic 36k             → bench/train_stage1_v6_36k_lexical_diag.py
```

Trace một query: `/v1/suggest` trả `stages.lexical` khi bật pipeline trace;
hoặc gọi thẳng `lexical_body` rồi `POST /{index}/_msearch`.

Lịch sử policy (v7 Photon-ish → v12 gated fuzzy) ghi trong
`search_policy.json` `notes` và evidence W1
[`11_ES_LEXICAL_POLICY.md`](../deliveries/w1_evidence/11_ES_LEXICAL_POLICY.md),
[`12_LEXICAL_ITERATE.md`](../deliveries/w1_evidence/12_LEXICAL_ITERATE.md).
Số liệu trong các file đó gắn snapshot cũ; không sửa để khớp v12.
