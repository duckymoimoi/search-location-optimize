---
name: search20-stage1-query-variants
description: >-
  Author and validate Vietnamese Stage-1 POI/branch training-query coverage
  from a user-selected set of locked train_stage1_20k targets. Use for
  manual_authored_v6 production: six recoverable variants per POI, per-query
  qrels, mutation traces, serialization, validation, repair, and QA reporting.
  Bare-brand intents belong to search20-stage1-brand-queries. Prefix sampling,
  negative mining, model training, evaluation, and serving are downstream.
---

# Stage-1 POI query authoring

## Mục tiêu

Tạo một **coverage pool** các cách người dùng có thể gõ để tìm đúng POI hoặc
đúng chi nhánh. Sáu row của một POI dùng để phủ các tín hiệu khác nhau; chúng
không biểu diễn tần suất traffic và không mặc định được lấy mẫu ngang nhau khi
train.

Stage 1 chỉ dùng văn bản tên, địa chỉ và mã. Không dùng vị trí người hỏi, thời
gian, lịch sử, độ phổ biến hoặc tín hiệu Stage 2 để quyết định intent.

Nguồn sự thật:

- target: `data/vietnam/train_stage1_20k/target_pois_20k.parquet`;
- corpus đối chiếu: `data/vietnam/poi_corpus_v1/pois.parquet`;
- brand membership: `data/vietnam/train_stage1_brand_v1/`;
- brand lookup: `data/vietnam/train_stage1_brand_lookup_v2/`.

Target row thắng khi corpus legacy mâu thuẫn. Không dùng web, không sửa tên
riêng cho “đúng hơn”, không bịa alias, landmark, địa chỉ, category, branch label
hoặc mã.

Skill này tạo intent tới một POI/chi nhánh. Bare brand, alias brand và lỗi chỉ
nằm trong tên brand thuộc
[`search20-stage1-brand-queries`](../search20-stage1-brand-queries/SKILL.md).
Brand vẫn xuất hiện trong query POI khi đi cùng discriminator đủ nhận ra chi
nhánh.

## Quy trình

### 1. Khóa phạm vi và tạo authoring packet

Xác nhận target subset, work directory và output trước khi author. Tạo packet
một lần cho toàn phạm vi:

```text
python -X utf8 tools/build_stage1_authoring_packet.py \
  --target <target_subset.parquet> \
  --corpus data/vietnam/poi_corpus_v1/pois.parquet \
  --brand-lookup data/vietnam/train_stage1_brand_lookup_v2 \
  --output <work_dir>/authoring_packet.jsonl \
  --manifest <work_dir>/authoring_packet_manifest.json
```

Đọc `authoring_contract` trong manifest, sau đó chỉ mở packet rows của batch
đang xử lý. Chỉ tra corpus có mục tiêu khi packet thiếu match, collision bị
truncate, brand cần review hoặc fact mâu thuẫn. Không quét lại toàn corpus cho
từng POI.

Nếu fact cần thiết không được xác minh, đặt `needs_review`; không đoán.

### 2. Xác định identity và qrels trước khi viết

Với mỗi target, xác định:

- identity anchor: proper name, brand, ref, building code hoặc địa chỉ;
- discriminator tối thiểu: street, area, housenumber, branch label hoặc ref;
- component bất biến: digit, letter suffix, slash, ref và code;
- collision/equivalent entity và tập `acceptable_poi_ids` ban đầu;
- ownership của intent: POI/branch hay bare-brand dataset.

Với `brand_context`:

- membership yêu cầu branch discriminator: giữ brand cùng discriminator tối
  thiểu trong mọi query POI;
- membership chưa adjudicate: đặt `needs_review` nếu lookup có review hoặc
  alternative chưa khóa;
- excluded membership không được dùng làm brand family;
- `bare_brand_owner=brand_dataset`: không materialize bare-brand intent trong
  pack POI.

### 3. Viết đúng sáu slot

| Slot | Vai trò | Contract |
|---|---|---|
| v01 | source anchor | Canonical có official name và discriminator tối thiểu |
| v02 | natural identity core | Cách gõ ngắn, tự nhiên, đủ giữ intent |
| v03 | controlled coverage | 2–3 operator tương thích, bề mặt khác v02 |
| v04 | controlled coverage | tag set và realization khác v03 |
| v05 | controlled coverage | phủ họ lỗi/biến thể khác v03–v04 |
| v06 | controlled coverage | alternate recoverable, không lặp công thức |

`v01` giữ official spelling. Chỉ thêm descriptor hoặc admin khi cần phân biệt.

`v02` ưu tiên tên/brand/mã/số và discriminator ngắn nhất. Có thể bỏ type label
không mang identity như `đường`, `phố`, `phường`, `quận`, `cửa hàng`, `cây
xăng`, `nhà hàng`, `trường`, `bệnh viện`, `tòa nhà`, `siêu thị`, `quán` hoặc
`số`. Không bỏ nếu label thuộc proper name hoặc phần còn lại trở nên generic.
Address-only ưu tiên `{housenumber} {street}`.

`v02–v06` không dùng dấu chấm câu. Chỉ compact dấu chấm trong abbreviation/code
khi thứ tự chữ-số được bảo toàn và form không tạo mã khác.

`v03–v06` dùng parent v02, trừ operator cần thành phần chỉ có trong v01. Mỗi row:

- dùng 2–3 tag pairwise-compatible trong [`operators.md`](operators.md);
- có 2–4 mutation points được trace đầy đủ;
- tác động identity hoặc discriminator, gồm một biến đổi cục bộ ở token chữ đầu
  tiên sau mọi số/code bất biến;
- giữ skeleton đủ để người đọc vẫn suy ra intent;
- không sửa digit, letter suffix, ref, building code hoặc thứ tự thành phần địa
  chỉ;
- không lặp tag set hay cùng `source → mutated` trong một case.

Độ khó đến từ biến đổi phần nhận dạng, không từ việc kéo dài query bằng admin.
Ưu tiên transpose, adjacent-key substitution, delete bên trong token, raw
Telex/VNI, mất ranh giới token và omission tự nhiên. Double-tap ở cuối token là
tín hiệu yếu, chỉ dùng khi hợp lý và không lặp thành mẫu hàng loạt.

### 4. Phủ yêu cầu Stage 1 ở cấp batch

Một POI không cần mang đủ mọi loại lỗi. Một batch đủ lớn phải phân phối coverage
theo khả năng áp dụng của source:

- **Identity tự nhiên:** canonical, short name, verified name fragment, acronym
  quen dùng, full address paste, street-only/address-only và building code.
- **Dấu và bộ gõ:** full/partial diacritic drop, nhầm thanh, raw Telex/VNI,
  orthographic equivalent đã xác minh.
- **Gõ nhanh:** adjacent key, transpose, delete/insert, double-tap và
  `token_boundary_error` cho dính/rời token.
- **Cấu trúc:** token order, bỏ cụm chung, abbreviation/expansion có mapping.
- **Địa chỉ/mã:** số nhà + street, street-only, ngõ/ngách/hẻm/kiệt, slash spoken,
  địa chỉ dán nguyên và mã tòa/lô.

Prefix giữa ký tự và prefix theo biên từ được sinh tự động từ query hoàn chỉnh ở
pipeline train/eval. Không author toàn bộ prefix thành sáu slot. Prefix training
view nên lấy chủ yếu từ v01/v02 và các controlled row còn tự nhiên, rồi sample
theo ngưỡng ký tự/rành giới từ của sản phẩm.

Coverage map đầy đủ và điều kiện từng operator nằm trong
[`operators.md`](operators.md). Chỉ mở [`examples.md`](examples.md) khi cần xử lý
ca khó; không sao chép typo hoặc cấu trúc của ví dụ hàng loạt.

### 5. Kiểm tra intent và qrels sau từng biến đổi

- Query đủ định danh dùng singleton hoặc entity-equivalent IDs đã khóa.
- Query trở nên mơ hồ phải có đủ multi-positive qrels đã xác minh hoặc được viết
  lại.
- Recompute qrels sau omission, abbreviation, no-diacritic, name fragment,
  token boundary và token order.
- Bare brand nhiều chi nhánh không được gán cho một branch trong pack POI.
- Chỉ viết cụm tìm kiếm điểm đến; không viết câu hỏi, voice/chat, action intent,
  recommendation hoặc `gần tôi/quanh đây`.

### 6. Serialize, validate và sửa

Ghi schema và slot contract từ `authoring_packet_manifest.json`:

- `generator_version=manual_authored_v6`;
- đúng thứ tự `v01…v06`;
- `canonical_query` bằng v01 trong cả sáu row;
- `query_types={primary_sampling_stratum}|{slot_tag}|{language_tag}`;
- `acceptable_poi_ids`, `n_acceptable`, `is_multipositive` phải khớp;
- trace v03–v06 phải ghi parent, ordered error tags, toàn bộ affected spans,
  before/after text và review status.

Chạy:

1. `tools/serialize_stage1_v6.py`;
2. `tools/validate_stage1_train_v6.py --ban-acronym-case` với target, corpus,
   gold và published sets đúng phạm vi;
3. sửa query/trace gây lỗi rồi chạy lại đến khi không còn error.

Không nới validator hoặc sửa source để ép PASS. Validator kiểm tra invariant máy;
agent vẫn chịu trách nhiệm naturalness, factuality, identity và qrels completeness.

### 7. Báo cáo

Báo số POI/rows, authored/needs-review, trạng thái serialize/validate, artifact và
packet hash, brand lookup version, tag distribution, mutation-point distribution,
identity-target rate, token-boundary coverage, raw-IME coverage, warning được giữ
và danh sách case cần adjudicate.

Không publish immutable release nếu phạm vi chỉ yêu cầu thử nghiệm.

## Hard rejects

Reject hoặc đặt `needs_review` khi:

- official name bị respell/dịch hoặc target admin bị trộn với legacy admin;
- query chứa fact, alias, specialty, landmark hoặc branch label không có source;
- bare brand bị gán singleton cho một branch;
- code/digit/suffix bị đổi, slash bị phá hoặc địa chỉ bị đổi thứ tự;
- token được dính/rời nhưng không gắn `token_boundary_error`, hoặc phép dính/rời
  làm đổi ký tự ngoài whitespace;
- query noisy mất cả anchor và discriminator, trở thành chuỗi khó khôi phục;
- lỗi chỉ nằm ở admin/descriptor dù identity đủ điều kiện chịu lỗi;
- nhiều slot lặp cùng typo, cùng span hoặc cùng công thức;
- query prefix/chưa gõ xong bị dùng làm một trong sáu authored rows;
- qrels rỗng, thiếu intended POI hoặc ambiguity chưa được xử lý;
- sáu query trùng nhau sau NFKC + casefold + trim + collapse whitespace.

Không tạo dữ liệu gượng ép để đủ slot. Giữ case trong work queue nếu source
không cho phép tạo đủ sáu query tự nhiên và đúng contract.
