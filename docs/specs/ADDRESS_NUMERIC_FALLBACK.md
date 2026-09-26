# Lexical fallback cho địa chỉ và số/mã — Stage 1

**Status:** target design; runtime chưa triển khai resolver này tại 23/09/2026

**Contract version:** `address-scope-lexical-fallback-v1`

**Evaluation schema:** [`schemas/stage1_evaluation_v2.schema.json`](schemas/stage1_evaluation_v2.schema.json)

Tài liệu này là source of truth cho việc xử lý số nhà, chuỗi ngõ/hẻm/kiệt, unit
và building code khi catalog không có exact member. Bộ đánh giá dùng chung nằm
tại [`STAGE1_EVALUATION_SUITE.md`](STAGE1_EVALUATION_SUITE.md).

## 1. Quyết định

Sai hoặc chưa quan sát thấy số nhà không được biến thành positive training cho
một POI nguồn. Việc đó làm encoder học bỏ qua số và phá exact-address accuracy.

Fallback thuộc lexical/structured retrieval:

1. parse number/code và street/complex namespace;
2. kiểm tra exact member trong address snapshot đã pin;
3. nếu có exact member, bảo vệ exact evidence;
4. chỉ khi number/code không được quan sát trong một scope đã resolve chắc, bỏ
   ảnh hưởng của span đó trong **lexical fallback view** và mở rộng cùng scope;
5. dense branch tiếp tục nhận original query, không được train hoặc rewrite để
   coi wrong number là đúng POI;
6. mọi fallback được ghi `match_type=fallback`, không gọi là exact.

Không giảm trọng số số nhà toàn cục. Conditional fallback là một route riêng;
exact number vẫn là tín hiệu mạnh khi catalog có evidence tương thích.

## 2. Ranh giới sự thật

`number_unseen_in_observed_scope` chỉ có nghĩa snapshot hiện tại không chứa member
phù hợp. Nó không chứng minh địa chỉ không tồn tại ngoài đời.

| Term | Meaning |
|---|---|
| address scope | street/admin hoặc complex namespace đã version |
| member | POI thuộc scope với number/code nullable |
| strong identity | name/brand/complex đủ nhận POI độc lập với number |
| address-only | phần còn lại chỉ nhận ra street/area, không nhận một POI |
| exact observed | number/code tồn tại và tương thích trong resolved scope |
| valid collision | số/code gõ vào là member khác thật trong cùng namespace |
| lexical fallback view | original query bỏ đúng conflicting numeric span để chạy lexical lane |

Giữ raw hierarchy và parts: `30/48D` là `30`, `48D`, không phải `3048D`.
`S2.02` là code trong namespace, không phải số `202`. `QL1A`, `Quận 1`, `Đội
11`, `Đường 3 Tháng 2` không được mutate như house number.

## 3. Ownership và artifacts

Logic nằm ngoài `apps/poi-search/api/app.py`. API chỉ pin release và gọi module:

```text
parse_address_evidence(query) -> AddressEvidence
resolve_address_scope(evidence, snapshot) -> AddressDecision
build_lexical_address_plan(query, decision) -> LexicalAddressPlan
expand_address_scope(scope_id, lexical_candidates, policy) -> CandidateSet
```

Artifacts:

| Artifact | Role |
|---|---|
| `address_scope_members_v1.parquet` | membership sidecar từ corpus đã pin |
| `address_scope_scenarios_v1.parquet` | exact/fallback/collision eval queries |
| `address_scope_qrels_v1.parquet` | graded POI/scope relevance |
| `manifest.json` | source, normalizer, scope, qrels và artifact hashes |

Các record dùng schema chung `stage1-eval-suite-v2`. Sidecar join bằng `poi_id`;
không thêm resolver fields vào POI core.

## 4. Address scope và identifier role

Pilot dùng hai tier:

- strong: normalized street + `subdistrict_region_id` + `province_region_id`;
- weak alternate: normalized street + `province_region_id`, không được promote
  thành exact nếu thiếu evidence.

Complex/building namespace dùng ID riêng khi source xác nhận. Thay membership key
phải tạo resolver version mới; không đổi group ngầm.

Mọi numeric/alphanumeric span được phân loại:

- `house_number`
- `alley_chain`
- `unit`
- `building_code`
- `branch_ref`
- `road_number`
- `admin_number`
- `unknown`

Chỉ năm role đầu có thể tham gia exact/fallback decision. Ba role còn lại bất
biến.

Resolver trả một trong:

- `exact_observed`
- `number_unseen_in_observed_scope`
- `valid_other_member_collision`
- `ambiguous_scope`
- `unresolved_scope`
- `coverage_unknown`

Chỉ `number_unseen_in_observed_scope` trong strong scope được mở lexical
fallback chắc chắn. Ambiguous/unresolved/coverage-unknown giữ broad retrieval.

## 5. Online policy

| Query state | Lexical/structured behavior | Dense behavior |
|---|---|---|
| Exact observed | exact number+scope được boost/protect | original query |
| Strong POI identity + numeric conflict | giữ name/brand candidates; đánh dấu conflict | original query |
| Address-only + unseen number | bỏ đúng numeric span trong lexical fallback view; expand same scope | original query, không scope-positive training |
| Valid other-member collision | giữ member thật hoặc ambiguity | original query |
| Ambiguous/unresolved scope | broad retrieval, không hard fallback | original query |
| Building/unit conflict | fallback trong complex namespace trước street | original query |

Lexical fallback không strip mọi digit bằng regex. Original query luôn được giữ
cho audit. Same-number khác street/complex không được thắng chỉ nhờ numeric match.

Scope expansion dùng fixed candidate budget; không inject target từ qrels. Trong
scope, rank bằng remaining name/category/address evidence và policy đã version.

## 6. Qrels và multi-accept

Address fallback không dùng binary multi-positive như bare brand:

- exact member/entity-equivalent: relevance 3, `positive`;
- resolved address scope: relevance 3 ở target type `address_scope`;
- same-scope POI expansion: relevance 1–2, `compatible`;
- same-number wrong-scope: relevance 0, `negative`;
- ambiguous/unjudged: relevance 0, `ignore`.

Query đúng số không coi mọi POI cùng street là positive. Query unseen-number
không giữ source POI làm hidden gold. Valid collision không tự “sửa” về source
POI nếu thiếu strong identity độc lập.

`address_scope_eval_v1` là evaluation/router data, không được đưa vào encoder
training, in-batch positives hoặc negative mining.

## 7. Evaluation

Chạy cùng corpus, candidate budget và frozen model:

1. `B0`: hybrid baseline hiện hành;
2. `B1`: thêm parser/resolver nhưng chưa scope expansion;
3. `B2`: conditional lexical fallback view;
4. `B3`: B2 + bounded same-scope expansion.

Không có numeric fine-tuning arm trong contract này. Nếu B2/B3 không cứu được
fallback, sửa resolver, membership hoặc lexical policy trước; không dạy dense
model bỏ qua số.

Metrics:

- exact observed: Hit@1/5, MRR@10, CandidateHit@20/50, exact preservation;
- unseen number: AddressScopeHit@K, SameScopeCoverage@K;
- valid collision: correct-member và ambiguity rate;
- slash/alley/building-code namespace;
- wrong-scope same-number hijack;
- strict-to-fallback rescue và harm;
- latency p50/p95 dưới cùng candidate budget.

Exact-number non-inferiority là guardrail. Fallback result không được báo exact.

## 8. Thứ tự triển khai

1. Build/audit `address_scope_members_v1.parquet` từ frozen corpus.
2. Publish manifest và schema validation report.
3. Author/lock `address_scope_eval_v1` trước khi mở model output.
4. Implement parser/resolver/lexical plan ngoài `app.py`.
5. Chạy B0–B3 và khóa lexical policy thắng gate.
6. Chỉ sau đó mới tích hợp release và monitoring.
