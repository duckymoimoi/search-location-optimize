# Quy trình xây Gold Stage 1 v2 — 200 POI

**Trạng thái:** hướng dẫn thi công; `gold_stage1_v2` chưa được author/khóa.  
**Phạm vi:** Gold POI/entity cho full-query, autocomplete và robustness. Không
bao gồm bare-brand hoặc sai số nhà chưa tồn tại.  
**Hợp đồng:** [`STAGE1_EVALUATION_SUITE.md`](STAGE1_EVALUATION_SUITE.md),
[`stage1_evaluation_v2.schema.json`](schemas/stage1_evaluation_v2.schema.json),
hai tài liệu gốc [`search2.0.md`](search2.0.md) và
[`SEARCH_2.0_TONG_HOP_TASK.md`](../deliveries/SEARCH_2.0_TONG_HOP_TASK.md).

Tài liệu này đủ để một agent lập plan và làm bộ Gold; không cần tạo skill riêng.
Nếu dùng skill train
[`search20-stage1-query-variants`](../../.cursor/skills/search20-stage1-query-variants/SKILL.md)
để tra hiện tượng gõ, **chỉ mượn taxonomy và điều kiện factuality**. Không áp
sáu slot, định mức số lỗi/vị trí, early-mutation bắt buộc hoặc phân bố train
vào Gold. Gold đo trải nghiệm tìm kiếm có thể gặp thật, không phải kho stress
test.

## 1. Trạng thái đầu vào và ranh giới bất biến

- Corpus/index Docker hiện hành là `vn-poi-core-v3-semantic-address-dedup50`,
  179.209 POI. Gold v2 được pin trên snapshot v2
  [`poi_corpus_v2/manifest.json`](../../data/vietnam/poi_corpus_v2/manifest.json);
  v3 giữ nguyên mọi Gold/eval ID (0 merge). Dùng `pois_core.parquet`,
  `search_documents.parquet` và `poi_id_migration.parquet` cùng version. Không
  đánh giá query v2 trên index v1.
- 180 POI Gold v1 đã được remap sang corpus v2 tại
  [`gold_stage1_v1_corpus_v2/`](../../data/vietnam/gold_stage1_v1_corpus_v2/README.md).
  Hai target ID được chuyển sang POI sống sót; đây là **nguồn ID/metadata kế
  thừa**, không phải bộ query Gold v2. Không sao chép 1.080 query v1 để đủ 800
  query mới. Gold v1 gốc giữ nguyên cho replay lịch sử.
- Pool train đang có 19.939 target tại
  [`train_stage1_20k/manifest.json`](../../data/vietnam/train_stage1_20k/manifest.json).
  Checkpoint 500 POI/3.000 query đã khóa là artifact lịch sử, không được lấy
  target từ đó để chuyển sang Gold.
- `gold_stage1_v2` mới gồm đúng **200 target**, **4 completed query sessions
  mỗi target**, tổng **800 sessions**. Prefix checkpoint là view sinh khi eval,
  không phải 800 × số ký tự hàng query author thêm.
- Gold POI chỉ chấm query đủ intent của một POI/entity. Bare brand hoặc alias
  thương hiệu chưa có chi nhánh thuộc `gold_stage1_brand_v1`. Street-only,
  wrong-number, số/tòa chưa có trong catalog thuộc `address_scope_eval_v1`.
  Không gán một POI ngẫu nhiên làm positive cho các intent này.

## 2. Trình tự công việc — không đảo thứ tự

### Bước 0 — Khóa source và tạo sổ provenance

Ghi hash/version của corpus v2, index, migration map, Gold v1 mapped snapshot,
train target list, train queries đã publish, brand lookup, normalizer và policy
đánh giá. Chạy:

```powershell
python tools/verify_clean_poi_corpus_v3.py --scope artifacts
python tools/reissue_gold_stage1_v22.py verify
```

Current tooling: [tools/README.md](../../tools/README.md). Corpus-v2-only migration commands are no longer available; they do not validate the active corpus/release.


Đối chiếu `/_count` của index v2 bằng 184.135. Nếu source thay đổi, dừng selection
và lập version mới; không vừa author vừa đổi corpus. Sổ provenance cho từng case
phải có `case_id`, `poi_id`, `source_path`, `source_hash`, `case_origin`, lý do
chọn, người/review status, thời điểm duyệt và mọi ID tương đương.

### Bước 1 — Chọn 200 target, tách train trước khi viết query

Giữ 180 `case_id`/POI đã remap trong `gold_stage1_v1_corpus_v2/target_pois.parquet`.
Kiểm tra lại chúng còn searchable, tên/địa chỉ đúng source và không trùng
entity với target train. Không thay POI vì model hiện tại xếp hạng kém; chỉ thay
khi fact hoặc eligibility sai, có audit và version mới.

Chọn thêm 20 target từ corpus v2 để lấp lỗ hổng coverage: địa chỉ slash/ngõ,
mã tòa có namespace, tên/mã giống nhau giữa vùng, POI tên rõ, chi nhánh brand
có discriminator, đoạn tên giữa/cuối có thể tìm được. Giữ cân đối bảy stratum
hiện có nhưng không ép quota dẫn đến chọn POI kém thực tế. Mỗi candidate cần
có source name, address/region đáng tin, identity anchor và dấu hiệu phân biệt
tối thiểu; không chọn tên rác hoặc collision chưa adjudicate.

**Được chuyển target từ train sang Gold**, nhưng chỉ khi POI chưa thuộc
checkpoint 500, chưa có query train đã publish/khóa và không thuộc một family
đã được dùng làm positive train. Trước khi author Gold, xóa target chuyển đi
khỏi train list; kiểm tra `poi_id`, `entity_group_id`, retained duplicate IDs
và toàn bộ Gold `acceptable_poi_ids` không giao target/positive train. Không
cần lấy POI khác bù vào train. Nếu target đã có query train, chọn candidate
khác; không âm thầm xóa query đã khóa. Khi chuyển, cập nhật manifest/hash và
ghi `train_to_gold_transfer` theo case; không chỉ xóa CSV mà quên Parquet hoặc
packet mới.

Nguồn ngoài train không cần bước chuyển. Dù lấy ở đâu, **không gọi namespace
brand/street là held-out** nếu cùng namespace đã xuất hiện trong train. Gắn
`case_origin=inherited_v1|heldout_supplement` và
`exposure_class=poi_heldout_namespace_seen|poi_heldout_namespace_unseen` dựa
trên audit thực tế. Không dùng 1.080 query Gold v1, query Gold brand hoặc
address-scope làm ví dụ/prompt cho agent author Gold v2.

### Bước 2 — Lập case card và qrels nháp trước query

Mỗi target có một case card ngắn: official name, aliases đã xác minh, brand và
brand namespace nếu có, category, số nhà, phố/ngõ, admin, building/ref/code,
`entity_group_id`, collisions cùng tên/mã/đường, component không được sai,
discriminator tối thiểu và operator nào áp dụng được. Tra corpus v2 theo batch;
chỉ mở rộng collision lookup khi case cần. Metadata trống thì đánh dấu
`needs_review`, không tự bịa fact.

Lập `qrel_set_id` và danh sách POI/entity tương đương bằng evidence từ corpus,
migration map và review thủ công. **Không mở rộng qrels cho mọi chi nhánh cùng
brand.** Nếu tên/số/địa chỉ có nhiều cách hiểu, ghi rõ ambiguity và quyết định
author query có thêm discriminator, multi-positive có kiểm chứng, hay handoff
sang suite khác. Mỗi thay đổi omission/no-diacritic/fragment phải kiểm tra qrels
lại sau khi có query thật.

### Bước 3 — Author bốn completed sessions/POI

Làm theo batch nhỏ 10–20 POI, nhưng chỉ chốt phân bố và coverage khi xem toàn
bộ 200. Mỗi case có đúng bốn `query_role` sau:

| Role | Ý định | Điều kiện |
|---|---|---|
| `q01` | natural short intent — baseline người dùng | Cụm ngắn tự nhiên mà người dùng thường gõ và vẫn giữ được intent POI/chi nhánh; tên, mã hoặc số nhà + đường với discriminator thật sự cần. Không cần tên đầy đủ/canonical hay địa chỉ hành chính dài. |
| `q02` | cách gõ thay thế | Một đường vào khác có khả năng gặp thật: rút/bỏ context, đoạn tên đủ nhận dạng, viết tắt có mapping, địa chỉ, đổi thứ tự khối hoặc lỗi gõ. Có thể có nhiều lỗi cùng lúc. |
| `q03` | biến thể nhiều vị trí | Kết hợp các hiện tượng tương thích trên tên/brand/đường hoặc ranh giới token; sai ở nhiều vị trí nếu vẫn đọc ra intent. Không bị khóa vào một “single variation”. |
| `q04` | biến thể khó nhưng phục hồi được | Có thể kết hợp nhiều loại lỗi và nhiều vị trí trên identity lẫn discriminator; không có quota mild/compound/challenge hay trần số mutation points. |

`q01` là traffic-core baseline (200 sessions), **không** là query canonical dễ
đoán. Nó phải giữ đủ bằng chứng cho POI hoặc tập entity-equivalent đã adjudicate;
bare brand không được gán một chi nhánh chỉ vì nó là target. Nếu tên ngắn bị
trùng, thêm discriminator ngắn nhất người dùng thường gõ. Có thể bỏ `đường`,
`phố`, `phường`, `cây xăng`, `nhà thờ`… khi từ đó không thuộc proper name hoặc
identity.

`q02–q04` là ba bề mặt khác nhau, **không phải thang một lỗi → hai lỗi → ba
lỗi**. Mỗi row noisy cần ít nhất hai điểm biến đổi có ý nghĩa ở các vị trí
khác nhau, trong đó có một điểm trên token nhận dạng đầu tiên sau mọi số/code
bất biến. Được kết hợp nhiều lỗi hơn khi tự nhiên; không đặt số lỗi tối đa.
Lỗi rải trên tên/brand, giữa tên và tên đường; trong mỗi batch phải có cả
`space_merge` (dính hai từ) và `space_split_inside_token` (chen khoảng trắng
giữa chữ của một từ), không gộp hai hiện tượng thành một nhãn khó kiểm toán.
Loại chèn space **hiếm hơn nhiều**: dùng vài ca có lý do gõ thật, không rải
đều vào mọi POI/slot chỉ để có độ khó.
điểm dừng là tính tự nhiên và khả năng khôi phục intent khi người gõ vội nhìn
lại. Mỗi lỗi phải giải thích được như một thao tác gõ/biến thể thật, không phải
chèn ký tự ngẫu nhiên. q01 vẫn sạch; q02–q04 không được giữ phần nhận dạng đầu
hoàn hảo để chỉ làm hỏng context phía sau. Cả batch còn cần lỗi ở giữa và cuối
identity.

Trên **toàn bộ batch**, `q02–q04` cần phủ dính/rời space, typo trong
tên/brand/đường, raw Telex/VNI, omission/token order hợp lý và slash-address
spoken **chỉ khi địa phương/cấu trúc xác nhận**. Rụng toàn dấu đơn độc là ca
dễ, không tự coi là robustness khó. Lỗi chỉ ở descriptor/admin trong khi phần
tên giữ nguyên là dữ liệu yếu. Không sửa digit, hậu tố chữ, ref, mã tòa hoặc
đổi thứ tự chuỗi số ngõ/hẻm. Không dùng dấu `.` như thói quen mặc định. Query
phải là cụm tìm điểm đến, không phải câu hỏi, “gần tôi”, recommendation hoặc
lịch sử di chuyển.

Sau khi author, gắn `difficulty=clean|mild|compound|challenge` **theo query
thực tế**, không suy ra từ role hay ép phân bố 100/70/30. Báo số vị trí biến
đổi trên identity/discriminator và tỷ lệ row chỉ có lỗi ngoại vi; nếu ba
variant của nhiều POI đều quá dễ hoặc quá rác, sửa theo review chứ không đạt
quota bằng thủ thuật.

Lưu `query_text` là phiên gõ **đã hoàn chỉnh theo intent của role**. Các đoạn
gõ dở ở giữa token được expander tạo sau; không viết một prefix thành `q03` hay
`q04` chỉ để đủ coverage autocomplete.

### Bước 4 — Coverage 22 yêu cầu và ownership

Tag chỉ khi row/trace/source thật sự chứng minh yêu cầu. Một row có thể có nhiều
tag; không thêm biến thể giả để đạt quota. Minimum là gate cho toàn shared suite:

| # | Hiện tượng | Minimum | Chủ sở hữu |
|---:|---|---:|---|
| 1–4 | Không dấu, sai dấu, raw Telex, raw VNI | 40 / 12 / 12 / 8 | Gold POI |
| 5–9 | Phím kề, dấu nửa vời, chính tả tương đương, double-tap, dính/rời space | 20 / 25 / 8 / 10 / 24 | Gold POI |
| 10–13 | Đảo token, omission, bỏ type/context đầu, acronym có mapping | 12 / 16 / ≥80 `q01` phù hợp / 16 | Gold POI |
| 14–15 | Prefix giữa token, prefix biên từ | derived trên `q01` sessions | Gold POI prefix view |
| 16–17 | Đoạn giữa/cuối tên, số nhà + đoạn tên đường | 20 / 20 | Gold POI nếu còn entity intent |
| 18 | Chỉ tên đường | 12 | `address_scope_eval_v1`, ngoài 800 row |
| 19–22 | Ngõ/ngách/hẻm/kiệt, slash number, dán địa chỉ đầy đủ, mã tòa/lô | 10 / 10 / 12 / 12 | Gold POI khi có exact entity; nếu scope-only thì address suite |

Không thể phủ một requirement bằng source hiện có thì thay supplement target
trước lock hoặc báo shortfall rõ trong report. Bare-brand coverage được chấm
trong brand suite, không đổi `q01` của chi nhánh thành bare brand singleton.

### Bước 5 — Adjudicate qrels từng query và prefix evidence

Mỗi `query_id` có `intended_poi_id`, tập `acceptable_poi_ids` và `qrel_set_id`.
Full-query đủ định danh thường singleton; nhiều POI positive chỉ khi cùng entity
thật hoặc ambiguity đã được adjudicate. `qrels_v2.parquet` dùng record
`evaluation_qrel` theo schema: `target_type=poi|entity_group`,
`label=positive|compatible|negative|ignore`, relevance 0–3, lý do và
`evidence_source`. Qrels không được rỗng, thiếu intended hoặc trỏ ID không có
trong index v2. Query bị mất discriminator phải viết lại hoặc gán qrels đủ;
không tự nhận “gõ hết thì chỉ có một POI”.

Với autocomplete, lưu **session gốc** và policy/state để expander suy ra
checkpoint theo grapheme NFC, không chép từng ký tự thành gold row. Gắn
`pre_identity → group_ready → entity_ready` theo bằng chứng thực của mỗi session:

- `pre_identity`: chưa thể đòi đúng một POI; không tính exact-entity Hit/MRR;
- `group_ready`: đã rõ brand/tên/address group nhưng chưa rõ branch; handoff
  group qrels nếu có, nếu không chỉ báo diagnostic;
- `entity_ready`: đủ discriminator để dùng POI/entity qrels.

Headline autocomplete lấy `q01` (200 natural-short sessions). `q02–q04` báo
riêng theo role **và** difficulty thực tế; không gộp mọi variant vào một score
headline và không gọi `q02` là clean chỉ vì số slot nhỏ.
Sinh mọi grapheme checkpoint để tính FHC/SHC nhưng không xem checkpoint là
observations độc lập; lọc checkpoint chỉ whitespace và báo sensitivity theo
`min_chars=1/2/3`. `SHC(w=3)` chỉ hợp lệ khi có **ba checkpoint liên tiếp đủ
cửa sổ**; hit ở ký tự cuối đơn độc không được tính SHC. Báo riêng prefix ở biên
từ và giữa token, normalized FHC, keystroke saving.

### Bước 6 — QA theo batch và audit toàn bộ

1. Sau mỗi batch, xác nhận 4 role/case, provenance, naturalness, exact intent,
   qrels và coverage tags. `needs_review` không được serialize thành accepted.
2. Double-review **100% row compound/challenge ở `q02–q04`**, mọi multi-positive,
   brand-branch ambiguous, name fragment, địa chỉ slash/mã khó và case có
   query gần street-only. Blind-review ngẫu nhiên tối thiểu 20% `q01` và các
   variant còn lại chưa double-review.
3. Scan duplicate/leakage: NFKC, casefold, whitespace, accent-fold và
   token-boundary-fold. Kiểm tra trong Gold v2, với Gold v1, train queries,
   checkpoint 500, brand/address suites. Exact/fold collision phải adjudicate,
   không tự động coi hai intent khác nhau là tương đương.
4. Kiểm tra target và toàn bộ positive qrels không giao train target/positive
   còn publish, kể cả POI chuyển từ train. Kiểm tra `entity_group_id`, retained
   duplicate và các record cùng entity, không chỉ so exact ID.
5. Report coverage 22 tách `owned_coverage`/`handoff_coverage`, difficulty,
   query role, stratum, case origin, exposure class, prefix eligibility,
   duplicate/leakage và unresolved review. Không dùng model output để sửa Gold.

### Bước 7 — Validate, khóa rồi mới benchmark

Output duy nhất cho Gold mới:

```text
data/vietnam/stage1_eval_suite_v2/
  suite_registry.json
  gold_stage1_v2/
    target_pois_v2.csv
    target_pois_v2.parquet
    query_sessions_v2.csv
    query_sessions_v2.parquet
    qrels_v2.parquet
    coverage_22_report.json
    coverage_22_report.md
    selection_and_leakage_audit.json
    manifest.json
    LOCKED.json
    verify_gold_lock.py
```

`query_sessions` phải theo `$defs.poiQuerySession`, qrels theo
`$defs.evaluationQrel`, manifest theo `$defs.suiteManifest`; CSV và Parquet
cùng row/order/ý nghĩa. Manifest pin corpus/index count + hashes, migration
map, source Gold 180 + supplement selection, train-exclusion sau transfer,
entity/brand snapshot nếu qrels dựa vào chúng, normalizer, prefix expander,
qrels policy, authoring rule, benchmark code, counts và hash mọi artifact.
Nếu brand/address suite chưa sẵn sàng, lock **Gold POI riêng** và ghi trạng thái
suite registry tương ứng là pending; không tuyên bố cả shared suite hoàn tất.

`verify_gold_lock.py` phải fail nếu sai count 200/800/4-per-case, schema,
hash, qrel coverage, ID ngoài corpus/index, overlap train, `needs_review` còn
lại, coverage shortfall không được chấp thuận hoặc prefix contract/SHC test
chưa pass. Chỉ khi validator và blind review pass mới đặt `status=locked` và
`LOCKED.json`. Sau đó mới chạy baseline cố định candidate budget/config; report
full-query CandidateHit@20/50, Hit@1/5, MRR@10 và prefix FHC/SHC/AUC@5/10/50,
p50/p90/failure rate theo slice. Không gộp 800 rows và hàng nghìn prefix
checkpoints thành cùng một mẫu thống kê.

Mọi sửa target/query/qrels sau khi đã xem output model phải ra version/lock mới,
không ghi đè Gold đã khóa. Gold v1 và snapshot remap v2 vẫn là artifact lịch sử.

## 3. Chỉ thị ngắn cho agent thực thi

Đọc tài liệu này, schema và `STAGE1_EVALUATION_SUITE.md`; đọc manifest corpus
v2, Gold mapped 180, train pool và checkpoint 500 trước khi lập plan. Chạy
hai verifier ở Bước 0. Trình bày selection 20 target, transfer/exclusion audit
và case-card mẫu trước khi author; sau đó làm batch 10–20 POI, tự QA và tiếp
tục đến 200. Không hỏi duyệt từng batch trừ khi fact hoặc ownership không thể
adjudicate từ source. Không chạy model hoặc chỉnh qrels theo kết quả model trước
khi lock. Chỉ báo hoàn tất khi 200 target, 800 sessions, coverage report,
qrels, leak audit, hashes và lock validator đều PASS.
