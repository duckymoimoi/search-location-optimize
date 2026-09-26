---
name: search20-stage1-brand-queries
description: >-
  Build and validate brand-family membership, namespace-aware brand groups,
  brand-only Stage-1 training queries, and normalized brand qrels for Vietnamese
  POI retrieval. Use when an agent must deduplicate bare-brand queries across
  branches, group POIs by verified brand identity/category, author brand-name
  typo or alias variants, or prepare brand compatibility masks. Do not use for
  branch-specific POI/address query packs; use search20-stage1-query-variants.
---

# SEARCH 2.0 — Brand groups and brand-only train queries

## Phạm vi

Query phải được author/review thủ công bởi một human hoặc agent đủ năng lực đã
đọc đầy đủ contract. Không khóa workflow vào sản phẩm, model hay giao diện cụ
thể. Chỉ một owner được ghi một artifact tại một thời điểm; mọi output phải qua
validator như nhau. Script Python chỉ chuẩn bị packet, serialize và validate;
không tự viết `query_text`.

Triển khai theo hai phase. Phase membership được khóa trước khi author brand query.

```text
data/vietnam/train_stage1_brand_v1/
├── brand_group_members_v1.parquet
├── brand_family_candidates_v1.parquet
├── brand_alias_candidates_v1.parquet
├── top_multibranch_review_v1.csv
├── brand_family_review_overrides_v1.csv
├── manifest.json
├── audit_report.json
└── LOCKED.json
```

`brand_intent_queries_v1.parquet` và `brand_query_qrels_v1.parquet` chỉ được tạo
ở phase query sau khi membership đã khóa và review queue cần thiết đã adjudicate.

Input cục bộ:

- `data/vietnam/poi_corpus_v1/pois.parquet`
- `data/vietnam/poi_corpus_v1/pois_core.parquet`
- query POI hiện có chỉ để phát hiện bare-brand duplicate và hand-off.

Không tạo branch/address query trong skill này. Không tạo negative mining, model,
metric hoặc runtime index. POI index hiện tại vẫn là retrieval target; brand
tables là metadata/qrels offline.

## Tài liệu bắt buộc

- Trước khi tạo/review group, đọc [references/group-contract.md](references/group-contract.md).
- Trước khi viết brand query, đọc [references/query-contract.md](references/query-contract.md).
- Trước khi merge/export train view, đọc [references/integration.md](references/integration.md).

## Hard rules

1. Một bare-brand intent chỉ tồn tại một lần trên mỗi brand family/namespace,
   không lặp theo từng branch POI.
2. Không group chỉ bằng string equality. Phải xét brand/name/alias, category
   namespace và evidence.
3. `WinMart` khác `WinMart+`; `Vietcombank ATM` khác office/bank khi query có
   token `ATM`.
4. Query bare brand không có `intended_poi_id` duy nhất. Relevance là group-level.
5. Same-group POI không bao giờ là negative cho query `FAMILY_ALL` hoặc
   `FAMILY_NAMESPACE` tương ứng.
6. Không cưỡng ép đủ số variants. Mỗi group có 2–6 query đã review, ưu tiên ít
   nhất 3 khi operator tự nhiên; brand quá ngắn/canonical đã chứa namespace có
   thể chỉ có canonical + một biến thể an toàn.
7. Brand query chỉ chứa brand/verified alias và namespace token cần thiết. Không
   thêm street, ward, branch, origin, action intent hoặc landmark.
8. Code được auto-accept membership có evidence mạnh theo group contract; generic,
   singleton, alias/name-pattern yếu và namespace ngoài whitelist phải
   `needs_review`. `query_text` brand vẫn phải author/review thủ công.
9. Không tra web hoặc bịa alias. Thiếu evidence thì `needs_review`.

Họ biến thể brand-only, ở mức loại:

- canonical và alias đã xác minh;
- casing/punctuation; space split/merge tự nhiên;
- một mechanical slip;
- orthographic/IME: strip, residual Telex, sai thanh;
- nhầm âm không tạo brand khác.

Không thuộc skill này: địa chỉ/chi nhánh, đảo token trong tên brand, prefix,
compound mặc định, dịch tự do, nhân cùng một brand typo theo số branch.

## Ranh giới lỗi brand và lỗi POI

| Trường hợp | Dataset sở hữu |
|---|---|
| `Vietcombank`, alias hoặc typo chỉ của `Vietcombank` | Brand |
| `Vietcombank ATM`, khi `ATM` xác định namespace | Brand |
| `Vietcombank Lạc Long Quân`, kể cả lỗi ở phần địa chỉ | POI/branch |
| Query có brand typo nhưng vẫn chứa discriminator branch | POI, nhưng không lặp cùng brand typo hàng loạt |
| Bare brand được copy từ mỗi branch | Reject; dedupe thành một brand intent |

Brand dataset học tính bền vững của identity thương hiệu trên toàn family. POI
dataset học định danh chi nhánh bằng name/address/ref. Không dùng brand dataset để
thay thế query chi nhánh và không dùng từng branch để nhân trọng số lỗi brand.

## Workflow

### 1. Tạo candidate brand families

Extract candidate từ `brand`, `name` và `aliases`; chuẩn hóa NFKC/casefold để tìm
candidate, không dùng normalized string làm quyết định cuối.

Mỗi family cần:

```text
brand_family_id
brand_canonical
brand_fold
```

Ví dụ: `brand:petrolimex`, `brand:vietcombank`, `brand:winmart_plus`.

### 2. Tách namespace và review membership

Tách group theo category semantics khi cần:

```text
brand:petrolimex:fuel
brand:vietcombank:bank
brand:vietcombank:atm
brand:winmart_plus:convenience_store
```

Review từng membership theo [group contract](references/group-contract.md). Chỉ
member `accepted` và `destination_searchable=true` mới vào positive pool.

Build deterministic phase membership bằng:

```text
python -X utf8 tools/build_brand_groups_v1.py \
  --corpus data/vietnam/poi_corpus_v1/pois_core.parquet \
  --review-overrides data/vietnam/brand_group_review_overrides_v1.csv \
  --output-dir data/vietnam/train_stage1_brand_v1
```

Builder phải từ chối overwrite release không rỗng. Candidate từ repeated
name/alias không có explicit-brand evidence giữ `needs_review`; descriptor generic
như `tạp hóa`, `trạm xăng`, `homestay` không được accept làm family. Chạy
`tools/validate_brand_groups_v1.py` sau khi build. Sau `LOCKED.json`, không sửa v1
tại chỗ; mọi thay đổi membership tạo version mới.

### 2b. Tra cứu nhanh cho agent

Không quét lại corpus khi author từng batch. Dùng lookup đã khóa:

```text
data/vietnam/train_stage1_brand_lookup_v2/brand_lookup_v2.sqlite
```

`brand_lookup_v1` là snapshot cũ đã lưu dưới `artifacts/`; không dùng cho
authoring mới vì chưa phân tách chặt accepted/review/excluded. V2 chỉ đánh
canonical accepted khi family có ít nhất một accepted group và không bao giờ
nâng alias candidate thành accepted.

Tra một brand/namespace:

```text
python -X utf8 tools/query_brand_lookup_v2.py \
  --db data/vietnam/train_stage1_brand_lookup_v2/brand_lookup_v2.sqlite \
  --text "Vietcombank ATM" --namespace atm
```

Với brand-only workflow, tạo brand-context packet:

```text
python -X utf8 tools/build_brand_authoring_packet_v1.py \
  --brand-release data/vietnam/train_stage1_brand_v1 \
  --brand-lookup data/vietnam/train_stage1_brand_lookup_v2 \
  --output-dir data/vietnam/train_stage1_brand_queries_v1
```

Packet có đúng một row cho mỗi accepted `brand_family_id + brand_namespace`.
Mỗi row chứa canonical brand, verified aliases, alias review candidates tách
riêng, namespace, accepted positive pool và sibling namespace context. Không
đưa `needs_review`/excluded member vào positive pool và không tự nâng alias.
Agent author chỉ đọc packet/manifest, không quét lại corpus hoặc membership
parquet cho từng brand.

Với POI query workflow, dùng `tools/build_stage1_authoring_packet.py` để gộp
brand context, collision context và exact output contract. Agent đọc packet thay
vì scan 186k POI. Chỉ `accepted_memberships`/accepted text hit được dùng làm
quyết định chính. Review/excluded chỉ là cảnh báo; không tự merge. Chi tiết tại
[references/authoring-index.md](references/authoring-index.md).

### 3. Author brand-only variants

Viết 2–6 rows theo eligibility, không theo quota cứng:

- canonical brand bắt buộc;
- namespace form sạch khi cần phân biệt group;
- verified alias nếu có;
- case/punctuation variant nếu khác có nghĩa;
- một mechanical typo;
- space variant nếu tự nhiên;
- orthographic/IME/phonetic variant nếu brand cho phép.

Không tạo compound noise mặc định vì brand thường ngắn. Chi tiết trong
[query contract](references/query-contract.md).

### 4. Resolve qrels

- Bare brand không có namespace token: resolve theo brand family và các namespace
  đã được product policy chấp nhận.
- Query có namespace token như `ATM`: chỉ resolve namespace tương ứng.
- Materialize một row `query_id × poi_id` trong `brand_query_qrels_v1.parquet`.
- Không nhét list hàng trăm/nghìn POI lặp lại vào query table.

### 5. Validate

Chỉ accept release khi:

```text
0 duplicate query_id
0 duplicate normalized query trong cùng intent_id
0 query trùng text nhưng khác intent không được adjudicate
0 group member thiếu evidence
0 accepted member non-searchable
0 qrel trỏ ngoài accepted group scope
0 query không có positive
0 same-brand member bị gắn negative
0 operator không áp dụng được
0 action/address/branch text trong brand-only query
```

Mọi file phải có row count, schema, SHA-256 và version trong manifest.

## Output versions

```text
group_version=brand_groups_v1
generator_version=manual_brand_authored_v1
qrels_version=brand_qrels_v1
```

Không đổi version cũ tại chỗ sau khi membership/qrels đã dùng để train; tạo
version mới.

## Handoff với POI skill

Skill sibling `../search20-stage1-query-variants/SKILL.md` chỉ giữ query
branch-specific. Khi gặp bare brand:

1. Viết lại POI v02 thành `brand + discriminator`.
2. Dedupe bare-brand query theo `brand_family_id + normalized_query_text`.
3. Chuyển đúng một intent sang brand dataset.
4. Không giữ bản bare-brand singleton trong POI dataset.

## Điều kiện dừng

Dừng và đặt `needs_review` khi:

- cùng brand string có nhiều entity không liên quan;
- namespace chưa rõ hoặc query bare brand có policy namespace chưa chốt;
- alias/typo có thể trở thành brand thật khác;
- membership chỉ dựa trên substring;
- group chứa duplicate/closed/non-searchable POI chưa xử lý;
- cần fact ngoài corpus để quyết định.
