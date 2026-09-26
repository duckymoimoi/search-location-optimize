# Fast brand context for authoring

## Nguồn và version

Nguồn quyết định membership là release khóa:

```text
data/vietnam/train_stage1_brand_v1/
```

Lookup phục vụ agent là derived release:

```text
data/vietnam/train_stage1_brand_lookup_v2/
├── brand_lookup_v2.sqlite
├── brand_match_index_v2.parquet
├── brand_group_summary_v2.parquet
├── manifest.json
└── LOCKED.json
```

V2 thay v1 cho authoring mới. Nó chỉ đánh canonical surface `accepted` khi
family có accepted group thật; alias candidate luôn `needs_review`; generic đã
adjudicate như `tạp hóa`/`trạm xăng` trả về `excluded`.

Build và validate:

```text
python -X utf8 tools/build_brand_lookup_v2.py \
  --brand-release data/vietnam/train_stage1_brand_v1 \
  --output-dir data/vietnam/train_stage1_brand_lookup_v2

python -X utf8 tools/validate_brand_lookup_v2.py \
  --release-dir data/vietnam/train_stage1_brand_lookup_v2 \
  --brand-release data/vietnam/train_stage1_brand_v1
```

Lookup là cache khóa theo hash source. Nếu hash không khớp, tạo version lookup
mới; không sửa SQLite bằng tay.

## Lookup trực tiếp

```text
python -X utf8 tools/query_brand_lookup_v2.py \
  --db data/vietnam/train_stage1_brand_lookup_v2/brand_lookup_v2.sqlite \
  --text "Vietcombank ATM" --namespace atm

python -X utf8 tools/query_brand_lookup_v2.py \
  --db data/vietnam/train_stage1_brand_lookup_v2/brand_lookup_v2.sqlite \
  --poi-id <poi_id>
```

Chỉ dùng `decision_status=accepted`, `usable_groups` và
`accepted_memberships` làm quyết định. `review_alternatives`,
`review_memberships`, `excluded_memberships` không được tự nâng cấp.

## Combined POI authoring packet

Tạo một lần cho toàn target subset:

```text
python -X utf8 tools/build_stage1_authoring_packet.py \
  --target <target_subset.parquet> \
  --corpus data/vietnam/poi_corpus_v1/pois.parquet \
  --brand-lookup data/vietnam/train_stage1_brand_lookup_v2 \
  --output <work_dir>/authoring_packet.jsonl \
  --manifest <work_dir>/authoring_packet_manifest.json
```

Manifest chứa exact row/trace schema, slot specs, error tags và compound pairs.
Đọc manifest một lần; không mở source validator để khám phá contract.

Mỗi row chứa target/corpus fact, discriminator candidates, exact/accent/ref
collision, accepted/review/excluded brand context và authoring flags.

## Quy tắc sử dụng

1. Accepted membership có nhiều family/group member: dùng `brand + discriminator`.
2. Bare-brand intent thuộc dataset brand, không copy theo branch.
3. `needs_brand_review=true`: targeted lookup cho đúng case; chưa đủ bằng chứng
   thì giữ `needs_review`.
4. Collision count bằng 1 hỗ trợ standalone name nhưng không thay review của
   query sau mutation.
5. Candidate IDs bị truncate: viết query rõ hơn hoặc targeted lookup để có qrels
   đầy đủ; không scan lại toàn corpus cho mọi POI.
6. Packet là context tăng tốc, không thay target SoT và không tự chứng minh
   naturalness/qrels completeness.
