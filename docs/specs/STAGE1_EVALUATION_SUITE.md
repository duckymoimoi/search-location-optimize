# Bộ đánh giá dùng chung cho Stage 1

**Status:** target contract. Gold POI `gold_stage1_v2_1` đã khóa trên corpus v3.
`gold_stage1_brand_v1` là suite còn lại để hoàn thành đánh giá Stage 1 hiện
hành. `address_scope_eval_v1` là suite độc lập, không phải điều kiện bắt buộc
của đợt này.

**Contract version:** `stage1-eval-suite-v2`

**Schema:** [`schemas/stage1_evaluation_v2.schema.json`](schemas/stage1_evaluation_v2.schema.json)

Tài liệu này là source of truth cho đánh giá text retrieval của Stage 1. Nó mở
rộng hai tài liệu gốc [`search2.0.md`](search2.0.md) và
[`SEARCH_2.0_TONG_HOP_TASK.md`](../deliveries/SEARCH_2.0_TONG_HOP_TASK.md) mà
không sửa nội dung hai file đó.

## 1. Ba suite và ranh giới trách nhiệm

| Suite | Đánh giá | Positive semantics | Không dùng để |
|---|---|---|---|
| `gold_stage1_v2` | POI/entity full query và autocomplete | một POI thật cùng entity-equivalent records | đo bare brand hoặc wrong-number fallback |
| `gold_stage1_brand_v1` | bare brand/alias/namespace | accepted brand group và các member tương thích | ép một chi nhánh đứng đúng từ brand-only text |
| `address_scope_eval_v1` | exact number/code và lexical scope fallback | exact member hoặc graded street/complex cohort | train model coi sai số là đúng POI |

Ba suite dùng chung corpus snapshot, entity/brand/address membership versions,
normalizer, candidate budget và evaluation code khi được build. Báo cáo luôn
tách suite; không gộp POI và brand thành một score duy nhất.

Đánh giá Stage 1 hiện hành hoàn thành khi Gold POI/entity và Gold brand đã khóa,
validator PASS và baseline đã pin hash. `address_scope_eval_v1` không chặn mốc
này. Số nhà/đường được xử lý bằng lexical trên các trường riêng; không đưa
wrong-number hoặc same-street fallback thành positive cho encoder.

Gold/eval artifacts không được đưa vào train, mining, distillation hoặc prompt
authoring. Workspace train có thể dùng cùng taxonomy nhưng không dùng query text,
target family hoặc qrels của các suite đã khóa.

Trước khi khóa Gold POI hoặc Gold brand, chạy cleaning audit trên corpus và
khóa `corpus_cleaning_policy_version` cùng migration map hoặc exclusion/equivalence
overlay. Cùng một eligibility view phải được áp dụng cho train, index, candidate
retrieval và eval. Các row tên một ký tự, duplicate gần và xung đột địa chỉ xa
được review theo [POI cleaning audit](../../data/vietnam/poi_corpus_v1/eda/poi_cleaning_audit.md);
không bỏ target hoặc đổi qrels sau khi đã xem model output.

Corpus `vn-poi-core-v2-address-name-dedup50` là snapshot Gold v2 pin tại
[`poi_corpus_v2`](../../data/vietnam/poi_corpus_v2/README.md). Docker demo đang
chạy corpus v3 (`vn-poi-core-v3-semantic-address-dedup50`, 179.209 POI); Gold và
train-500 IDs được giữ nguyên (0 merge). Gold v2 áp `poi_id_migration.parquet`
cho mọi target/qrels nguồn v1; mọi dependent membership được dùng cho qrels phải
kiểm tra/rebuild tương thích trước khi lock. Gold v1 vẫn được replay trên
corpus/index v1.

Quy trình thực thi Gold POI v2, cập nhật theo corpus/index v2 đã chạy và pool
train đã lọc, nằm tại
[`GOLD_STAGE1_V2_CONSTRUCTION_PLAYBOOK.md`](GOLD_STAGE1_V2_CONSTRUCTION_PLAYBOOK.md).
Nếu chuyển một POI chưa author từ train sang Gold supplement, xóa POI và các
entity-equivalent positive liên quan khỏi train trước khi khóa Gold; không lấy
từ checkpoint train đã khóa.

## 2. `gold_stage1_v2`

### Target và query sessions

- đúng 200 POI;
- 180 target kế thừa danh sách POI Gold v1 nhưng author query mới;
- 20 target held-out bổ sung để lấp coverage gap theo stratum/operator;
- đúng bốn completed query sessions mỗi POI, tổng 800 rows;
- không lưu từng prefix thành authored row.

| Role | Số row | Nội dung |
|---|---:|---|
| `q01` | 200 | natural short intent, đủ định danh POI/chi nhánh; traffic-core baseline |
| `q02` | 200 | cách gõ thay thế tự nhiên, có thể kết hợp nhiều lỗi |
| `q03` | 200 | biến thể nhiều vị trí trên identity/discriminator |
| `q04` | 200 | biến thể khó nhưng phục hồi được, không giới hạn cứng số lỗi/vị trí |

`q01` không bắt buộc canonical hoặc địa chỉ đầy đủ dễ khớp lexical. `q02–q04`
không bị khóa thành bậc một/hai/ba lỗi hoặc quota 100/70/30; được phép có nhiều
lỗi ở nhiều vị trí nếu cách gõ vẫn tự nhiên và giữ identity skeleton. Mỗi row
noisy cần ít nhất hai điểm biến đổi, gồm một điểm trên phần nhận dạng đầu tiên
sau số/code bất biến; cả batch phải có lỗi dính từ và một số ít ca chen space
giữa chữ, không dùng ca chen space như công thức đại trà.
Gắn
`difficulty` sau khi author theo row thực, review mọi compound/challenge và
không tạo độ khó bằng cách kéo dài admin hoặc phá số/code.

Full-query qrels mặc định là một entity. `acceptable_poi_ids` chỉ mở rộng cho
records cùng POI thật/entity-equivalent hoặc ambiguity được adjudicate. Bare
brand, street-only và prefix chưa đủ discriminator không được biến thành
singleton POI gold.

### Prefix view

Prefix là derived checkpoints của một typing session:

```text
pre_identity -> group_ready -> entity_ready
```

- `pre_identity`: chưa đủ text để gắn target; không tính exact-entity accuracy;
- `group_ready`: nhận ra brand/name/address group nhưng chưa đủ discriminator;
  dùng group qrels nếu có, nếu không chỉ diagnostic;
- `entity_ready`: đủ evidence để dùng POI/entity qrels.

Headline autocomplete lấy q01 natural-short. q02–q04 báo riêng theo role và
difficulty thực tế, không ép `q02` là mild hoặc `q04` là challenge. Expander có
thể sinh mọi grapheme để đo FHC/SHC nhưng training không được nhân mọi ký tự
thành row. Khi train prefix view, chỉ sample
3–5 checkpoint có nghĩa từ train families và không dùng gold sessions.

`SHC(w=3)` chỉ được tính khi đủ ba checkpoint liên tiếp; cửa sổ rút ngắn ở cuối
session không hợp lệ.

## 3. `gold_stage1_brand_v1`

Mỗi brand query trỏ tới `brand_group_id`/namespace đã khóa và có full compatible
member set hoặc compatibility mask. Các nhóm chính:

- canonical bare brand;
- verified brand alias/acronym;
- lỗi chỉ nằm trong tên brand;
- namespace-qualified brand như ATM khi membership xác nhận;
- prefix ở trạng thái `group_ready`.

Không lặp cùng bare-brand query theo từng chi nhánh. Branch query đã có
discriminator thuộc `gold_stage1_v2`, không thuộc brand gold.

Metric: AnyCompatibleHit@K, compatible coverage@K, group MRR và false-branch
exclusion theo namespace. Báo family-weighted metrics và paired confidence
interval; nhiều query/prefix của cùng family không phải mẫu độc lập. Prefix
headline chỉ chấm từ `group_ready`. Không dùng strict branch Hit@1 cho bare
brand. Gắn exposure `brand_query_heldout_branch_seen` /
`brand_query_heldout_branch_unseen` trên cột vận hành cạnh schema đã pin
(không đổi hash schema của Gold POI); chỉ công bố `cold_brand` khi family và
mọi member đã bị loại khỏi mọi positive train và distillation.

## 4. `address_scope_eval_v1`

Suite này **không thuộc phạm vi hoàn thành Stage 1 hiện hành**. Nó đánh giá
resolver và lexical/structured fallback theo
[`ADDRESS_NUMERIC_FALLBACK.md`](ADDRESS_NUMERIC_FALLBACK.md) khi được build
riêng. Nó không phải dữ liệu train encoder và không được hiểu là điều kiện
bắt buộc để khóa hoặc công bố đánh giá POI + brand.

Các scenario tối thiểu:

- exact observed house number/code;
- number unseen trong resolved street/complex scope;
- same-number wrong-street hijack;
- valid other-member collision;
- slash/alley chain;
- building/unit code có namespace;
- ambiguous/unresolved scope.

Exact scenario có POI/entity qrels. Unseen-number scenario dùng graded qrels:
address scope là target chính, same-scope POIs là compatible expansion, còn
same-number khác scope là negative. Không biến toàn bộ POI cùng phố thành binary
positive ngang nhau.

## 5. Coverage tối thiểu

Ba suite cùng nhau phải phủ 22 yêu cầu trong `search2.0.md`. Gold POI v2 sở hữu
các query còn đủ entity intent; bare brand/brand alias thuộc brand gold;
street-only hoặc scope ambiguity thuộc address-scope eval và được báo pending
cho đến khi suite đó có artifact. Shared suite 22/22 không phải cổng của đợt
POI + brand hiện hành. Một row có thể đóng
góp nhiều coverage tag nếu trace chứng minh từng phép. Prefix giữa token và biên
từ là derived coverage.

Coverage gate không phải quota để bịa lỗi. Nếu target không đủ điều kiện cho một
operator, thay target hoặc báo shortfall trước lock.

## 6. Metrics và headline

| Track | Metric chính |
|---|---|
| POI full query | CandidateHit@20/50, Hit@1/5, MRR@10 |
| POI autocomplete | FHC/SHC/PrefixAUC@5/10/50, normalized FHC, keystroke saving |
| Brand group | AnyCompatibleHit@K, compatible coverage@K, group MRR |
| Address exact | Hit@1/5, MRR@10, CandidateHit@20/50, exact preservation |
| Address fallback | AddressScopeHit@K, SameScopeCoverage@K, wrong-scope hijack, rescue/harm |

Headline POI/autocomplete chỉ dùng traffic-core rows/checkpoints. Mild,
robustness, brand và address báo riêng. Prefix chưa `entity_ready` không tham gia
exact entity Hit/MRR.

Mọi metric báo theo query family, stratum, origin/exposure class và p50/p90 hoặc
confidence interval phù hợp. Nhiều checkpoints của một session không được coi là
các mẫu độc lập khi bootstrap.

## 7. Shared manifest và lock

Mỗi suite có manifest riêng và một suite registry chung. Bắt buộc khóa:

- corpus/index and candidate-policy versions;
- entity equivalence, brand groups và address-scope snapshots;
- normalizer, prefix expander và qrels policy versions;
- source/artifact hashes, row counts và exclusion audit;
- benchmark code hash và candidate budget;
- trạng thái `draft|validated|locked|superseded`.

Không chạy model trước khi query/qrels của suite được khóa. Mọi sửa sau khi đã
xem model output tạo version mới; Gold v1 tiếp tục là historical regression set.

## 8. Artifact layout

```text
data/vietnam/stage1_eval_suite_v2/
  manifest.json
  LOCKED.json
  suite_registry.json
  gold_stage1_v2/
    target_pois_v2.parquet
    query_sessions_v2.parquet
    qrels_v2.parquet
    coverage_22_report.json
  gold_stage1_brand_v1/
    brand_queries_v1.parquet
    brand_qrels_v1.parquet
  address_scope_eval_v1/
    address_scope_members_v1.parquet
    address_scope_scenarios_v1.parquet
    address_scope_qrels_v1.parquet
```

Prefix checkpoints và candidate snapshots là derived benchmark artifacts; không
phải authored gold source.
