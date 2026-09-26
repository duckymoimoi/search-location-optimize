# Thiết kế hệ thống tìm kiếm địa điểm gọi xe — v1

Revision: 23/09/2026. Đây là **thiết kế đích**, không phải mô tả nguyên trạng code. Demo hiện có Stage 1 hybrid và `heuristic-geo-v6`; chưa triển khai đầy đủ router/history/learned Stage 2 hoặc address-numeric resolver. Đọc [trạng thái as-built](../as-built/CURRENT_STATE.md), [đặc tả kỹ thuật](TECHNICAL_SPEC.md), [training/nâng cấp retrieval](TRAINING_AND_RETRIEVAL_PROTOCOL.md), [bộ đánh giá Stage 1](STAGE1_EVALUATION_SUITE.md) và [address/numeric fallback](ADDRESS_NUMERIC_FALLBACK.md). API đang chạy được giữ nguyên khi cải thiện thuật toán; contract mở rộng chỉ có hiệu lực sau khi được triển khai và tạo release/version rõ ràng.

## Quyết định retrieval hiện hành

Hybrid lexical + E5 single-vector + RRF đủ làm baseline triển khai, chưa được coi là tối ưu cuối cùng. Ưu tiên sửa negative sampling/masks; Matryoshka là nhánh giảm vector/index cost; late interaction là thử nghiệm text ranking khi error audit biện minh. Không tự thay E5 bằng ColBERT hoặc thêm model vào request path khi chưa qua quality/serving gates.

```mermaid
flowchart TD
    Q["Query và scope"] --> A["Address evidence và lexical fallback plan"]
    M["Address membership sidecar"] --> A
    A --> L["Lexical / structured"]
    A --> D["Single-vector dense: original query"]
    L --> F["RRF và fixed candidate budget"]
    D --> F
    A --> E["Address-scope expansion khi fallback"]
    E --> F
    F --> T["Text adapter: identity mặc định"]
    T --> C["Context: geo-v6 hiện tại hoặc learned đã qua gate"]
    X["Origin, time, history hợp lệ"] --> C
    C --> O["Top-K"]
```

Late-interaction adapter, nếu đạt gate, nằm ở text adapter trước context. Đây vẫn là Stage 1b hiểu chữ; không đổi định nghĩa Stage 2 cá nhân hóa. Protocol thí nghiệm kiểm tra cả conditional ranking và toàn pipeline; nhánh query-only không dùng origin/history.

## 1. Mục tiêu và giới hạn

Người dùng chọn điểm đón, gõ tên/địa chỉ điểm đến, nhận top-5 trên danh sách và bản đồ, rồi chọn địa điểm. Hệ thống phải xử lý prefix, thiếu/sai dấu, lỗi phím, tên viết tắt có nguồn, địa chỉ ngõ/ngách và mã tòa; dùng không gian, thời gian, lịch sử để phân biệt các lựa chọn còn mơ hồ.

AI học biểu diễn chuỗi và cách xếp hạng theo context. Hai model được train offline, suy luận online. Cập nhật history online không phải cập nhật trọng số. Không có LLM sinh câu trả lời, agent hoặc gọi Codex trên đường xử lý một lần gõ. Lexical và các ràng buộc địa chỉ là thành phần của hệ thống AI này.

MVP không tạo booking, không cam kết điểm đón tiếp cận được, không suy ETA từ đường thẳng. Golden context và bằng chứng hành vi thật triển khai sau; không ngăn bắt đầu code các interface và baseline.

### Dữ liệu thực sự sẵn có

| Artifact | Trạng thái |
|---|---|
| PBF Việt Nam `vietnam-260910.osm.pbf` | Snapshot 10/09/2026; hash nguồn trong corpus manifest |
| `vn-poi-core-v1` | 186.322 POI searchable toàn quốc; trạng thái `raw_nationwide_core_not_deduped`; admin và access enrichment là sidecar |
| `gold_stage1_v1` | 180 case · 1.080 query khóa; evaluation snapshot, không phải train set 20k |
| `train_stage1_queries_v6` | Workspace target 20k; checkpoint `003_hard_noise_500` có 500 POI · 3.000 query đã validate/lock cục bộ |
| Brand membership/lookup | `train_stage1_brand_v1` và `train_stage1_brand_lookup_v2` đã khóa; brand query là track riêng |
| Stage 1 evaluation suite v2 | Target contract gồm POI/autocomplete, brand group và address scope; chưa build/lock |
| Address membership/numeric fallback | Chưa build/ship; lexical fallback contract nằm tại `ADDRESS_NUMERIC_FALLBACK.md` |
| Dense baseline | `intfloat/multilingual-e5-small` 384d đang dùng cho nationwide demo; fine-tune mới chưa được promote |
| Demo runtime | FastAPI + Elasticsearch 9 + React/MapLibre; hybrid lexical+dense+RRF, geo-v6 mặc định (v5 regression), Goong route tùy cấu hình |
| Golden có context, learned Stage 2 | Chưa hoàn thành |

POI core được giữ ổn định; brand, address membership và access/routing enrichment là sidecar có manifest/version riêng. Không thêm tùy tiện trường train, resolver hoặc fallback vào bảng POI chính. Pipeline quốc gia phải giữ provenance và coverage; không suy một địa chỉ có thật chỉ từ việc POI khác cùng đường có số gần đó.

## 2. Ba khối logic trên đường search

| Khối | Nhận gì? | Làm gì? | Không chịu trách nhiệm |
|---|---|---|---|
| Scope router | Query structure, loại pickup/destination, anchor, vùng người dùng chọn | Lập kế hoạch nhánh ưu tiên + nhánh rộng | Đoán chắc ý định từ GPS hoặc quyết định model cá nhân hóa |
| Stage 1 retrieval | Query và search scope đã chọn | Lexical/structured + dense, fusion, top-N | Học history/time hoặc buộc chọn một branch từ query thiếu thông tin |
| Stage 2 context | Candidates, query evidence, origin/time/history | Bounded rescue và contextual ranking | Sinh POI không tồn tại, gán routing point hoặc sửa ý định explicit |

Model Stage 1 là query-only. Trong pipeline thực tế, **candidate set sau scope router đã phụ thuộc vị trí**. Vì vậy chỉ gọi Stage 1 độc lập là query-only khi chạy trên phạm vi cố định, không router, không history và không geo boost.

## 3. Kiến trúc triển khai

MVP là modular monolith: một Python API điều phối router, address resolver, retrieval, encoder, feature builder và ranker qua các module thuần có contract riêng. Elasticsearch phục vụ lexical/ANN; PostgreSQL lưu exposures, selections và history. UI React + TypeScript + MapLibre. ETL/train/eval và việc build membership sidecar là jobs riêng, không chạy chung trong phép đo serving. `app.py` là wrapper/orchestrator, không phải nơi sở hữu schema, normalizer, membership hoặc label policy.

```mermaid
flowchart TD
    U["UI: nhập và chọn điểm"] --> A["Search API"]
    A --> S["Elasticsearch"]
    A --> D["Address resolver + membership snapshot"]
    A --> M["Encoder và ranker adapters"]
    A --> H["PostgreSQL: history và events"]
    J["Jobs: corpus, train, index"] --> S
    J --> B["Model và release artifacts"]
    B --> M
    A --> R["Route preview adapter"]
```

Chọn PostgreSQL ngay để tránh đổi contract ghi sự kiện khi thêm worker; PostGIS, Redis, Kafka, Kubernetes và model RPC riêng chưa là dependency của MVP. Exact dense evaluator dùng vector matrix/chunks ngoài Elasticsearch. ANN được thêm vào serving sau khi có mốc chất lượng exact.

## 4. Luồng dữ liệu offline

```mermaid
flowchart TD
    P["PBF và metadata snapshot"] --> E["Extract toàn quốc và kiểm tra geometry"]
    E --> C["Canonical POI và audit"]
    C --> G["Region membership sidecar"]
    C --> Q["Query dataset có evidence"]
    Q --> T["Train encoder offline"]
    C --> D["Dựng passage và lexical fields"]
    T --> V["Encode toàn corpus"]
    D --> V
    D --> I["Index staging"]
    G --> I
    V --> I
    I --> K["Kiểm tra và publish release"]
```

### Corpus quốc gia

1. Xác minh byte size, SHA-256, source timestamp của PBF. Giữ source ID/type/version/timestamp và extraction-policy hash.
2. Extract node/way/relation bằng pipeline có geometry đầy đủ. Tách raw objects, canonical objects, searchable objects; report coverage/tag theo vùng.
3. Áp dụng sanitizer thống nhất trên direct tags và mọi nguồn enrich. Tombstone trường bị loại ngăn phục hồi mã nội bộ từ chính node gần nhất. Không dùng số nhà của hàng xóm làm địa chỉ.
4. Kế thừa tuple số nhà–đường từ building chỉ khi geometry và fields không xung đột. Consensus node cần định danh đầy đủ nguồn và kiểm tra mọi địa chỉ mâu thuẫn; khi chưa có bằng chứng, để audit.
5. Giữ address, nearby context và admin context riêng. Point-on-surface không phải pickup point; origin eligibility không phải pickup verification.
6. Dedup bảo thủ theo bằng chứng node/way; giữ branch, platform, entrance khi policy yêu cầu. Không merge chỉ vì trùng tên/bán kính gần.
7. Tạo `poi_regions.parquet` qua point-in-polygon; sử dụng relation ID và admin scheme version, không dùng tên phường làm khóa. Lưu tập membership khi overlap, không chọn phần tử theo thứ tự STRtree. Unknown membership không làm POI biến mất khỏi nhánh toàn quốc.
8. Publish immutable corpus. Hà Nội là subset theo boundary của corpus quốc gia; nếu policy/data khác stable v1, lưu migration map và report, không ép số lượng phải bằng bản cũ.

Sau khi publish corpus, build `address_scope_members_v1.parquet` như sidecar từ
street/admin/complex evidence đã pin. Mọi absence chỉ là
`number_unseen_in_catalog`; không ghi “địa chỉ không tồn tại”. Schema và rules
phân loại house number/alley/unit/code nằm trong
[`ADDRESS_NUMERIC_FALLBACK.md`](ADDRESS_NUMERIC_FALLBACK.md), không nằm trong ETL
POI core hoặc API app.

Job ETL phải chạy được theo checkpoint/batch, có exclusion report và đủ bằng chứng rerun. Không load toàn bộ PBF/geometry/vectors quốc gia vào list Python không giới hạn.

## 5. Luồng online

```mermaid
sequenceDiagram
    participant U as UI
    participant A as API
    participant S as Search
    participant H as History
    participant R as Ranker
    U->>A: query, anchor, context revision
    A->>A: pin release, parse, scope plan
    par Truy hồi
        A->>S: ưu tiên và toàn corpus
        S-->>A: candidates và evidence
    and History snapshot
        A->>H: user và cutoff
        H-->>A: events trước request
    end
    A->>S: bounded rescue nếu bật
    S-->>A: candidates bổ sung
    A->>R: feature matrix của tối đa 50 POI
    R-->>A: scores
    A->>H: persist exposure
    A-->>U: top-5, exposure, versions
    U->>A: select từ exposure đã hiển thị
    A->>H: idempotent selection event
```

Ở profile mặc định, query encoder gọi tối đa một lần/request và luôn nhận original query. Address resolver chỉ tạo lexical fallback view; không rewrite dense query hoặc gọi encoder lần hai. Nếu bật late-interaction thí nghiệm, encoder bổ sung của nó phải được khai báo và tính đầy đủ latency; không tuyên bố profile đó chỉ có một lần encode. Khi route lexical-only, Stage 2 không gọi encoder lại để che chi phí. Feature missing được biểu diễn bằng mask.

### Scope policy v1

Ưu tiên: vùng được người dùng chọn rõ → địa danh trong query được parser xác định chắc → anchor hợp lệ → toàn corpus. Gazetteer phải nhận dạng span/alias có nguồn; chỉ thấy một từ trùng tên tỉnh bên trong tên quán chưa đủ để hard-route. Tín hiệu mơ hồ giữ nhiều khả năng trong diagnostic và dùng nhánh rộng.

Anchor của destination là điểm đón đã chọn hoặc GPS khi chưa chọn; anchor của pickup là GPS/tâm người dùng chủ động chọn. Không tự dùng POI người dùng tìm làm vị trí đứng. Anchor null, stale hoặc accuracy kém được bỏ khỏi geo policy; không chuyển thành tọa độ 0,0.

MVP chạy tối đa hai lane ban đầu: primary và global. Primary là vùng explicit hoặc radius quanh anchor; global không có geo filter. Default radius: pickup 5 km, destination 15 km. Nếu primary không đủ candidates, được một lần mở lên 20/60 km khi còn deadline; query explicit-region không tự chuyển sang vòng bán kính. Các số là config khởi đầu, không phải tối ưu đã đo.

Nhánh toàn corpus luôn được giữ, kể cả pickup; location là prior, không phải biên giới ý định. Trường hợp có tên/địa chỉ xa rõ ràng được ưu tiên evidence explicit và không bị ép về gần. Nếu corpus chỉ Hà Nội thì “global” hiện có nghĩa toàn corpus Hà Nội; response phải công bố coverage, không giả tìm toàn quốc.

Một geo filter chỉ giảm tập ứng viên logic; không tự bảo đảm giảm số shard/RAM. Đầu tiên dùng index logic thống nhất và filtered ANN phù hợp. Chỉ chia vật lý theo vùng khi benchmark cho thấy cần; luôn có đường cross-region/global lookup.

### Stage 1

- Chuỗi gốc được giữ để hiển thị/audit. NFKC, khoảng trắng, lowercase và accent-fold tạo các biểu diễn riêng; giữ dấu `/`, số nhà, mã. Không tự sửa query có dấu thành tên khác.
- Lexical gồm exact/name, alias, accent-folded, prefix và address/ref fields. Prefix 1–2 ký tự ưu tiên lexical; query dài/lỗi/ngữ nghĩa chạy hybrid. Structured query vẫn giữ field-aware lexical. Các route là config thử nghiệm, không dùng nhãn dataset để routing.
- E5-small là model khởi đầu; POI encode offline, query encode online. RRF dùng thứ hạng, không cộng BM25 và cosine trực tiếp.
- Address resolver phân biệt exact observed, unseen-in-catalog, valid collision, ambiguous và unresolved. Chỉ span số/mã đã phân loại mới được bỏ khỏi lexical fallback view; không strip mọi digit bằng regex. Dense giữ original query. Address-only unseen dùng scope fallback, còn strong POI identity + numeric conflict vẫn giữ POI mang tên đúng trong candidates nhưng không gọi exact address.
- Baseline chất lượng chạy lexical / exact dense / hybrid exact ở final K=5/20/50. Serving ANN được đo loss so với exact sau đó.

### Candidate assembly và Stage 2

Trong mỗi lane: lexical depth=100, dense depth=100, RRF c=60 với weights 1/1; dedup theo poi_id. Lanes có thể trả cùng POI: dùng max lane score đã chuẩn hóa, không cộng lợi thế vì POI xuất hiện hai lần.

Candidate budget cuối N=50. Chọn tối đa 5 POI có evidence địa chỉ/mã có namespace rõ; tiếp đến tối đa 10 global candidates chưa chọn; tiếp đến primary, rồi global remainder cho đủ 50. Nếu không có primary, lấy global top-50. Trong lexical address fallback, expansion cùng street/complex dùng budget đã đăng ký và không chèn target từ qrels. “Bảo vệ explicit” không áp dụng cho exact brand/name nhiều chi nhánh; nó bảo vệ không bị loại khỏi candidates, không bắt buộc đứng top-1.

Stage 2 rescue được thử ngay trong plan: tối đa 5 geo và 5 history candidates mới, mỗi source retrieve tối đa 20. Chỉ nhận candidate khớp query evidence hoặc compatibility rule đã khóa, không lấy nearest/history bất kể query. Thay tối đa 10 slots thấp nhất không được bảo vệ; giữ protected explicit và global reserved, N không đổi. Không nhân đôi cùng một nguồn geo đã có: đo marginal rescue trên candidates sau router.

Ranker ladder: Stage 1 order → **geo-v6 hiện hành** theo nhóm tên tương đương → LightGBM LambdaMART → AggregateMLP → attention khi có bằng chứng. Geo-v5 blend text relevance với distance decay được giữ làm regression comparator, không phải policy mặc định. Geo-v6 không cộng distance vào RRF, chỉ hoán đổi slots cùng lớp khớp trong window cấu hình; việc đã có code/unit fixture không thay thế benchmark uplift. Attention phải được so với baseline có cùng thông tin; encoder frozen ở vòng Stage 2 đầu tiên.

Guardrails dùng evidence rõ: exact observed number/street/ref hoặc vùng explicit không được history/nearby tự ghi đè. Numeric conflict không tự biến source POI thành positive: strong identity có thể cứu POI theo tên; address-only phải fallback theo scope; valid collision phải giữ ambiguity. Khi parser không chắc, không áp hard constraint. Chưa có log thật thì learned ranker được ghi rõ synthetic-trained; không gọi việc đổi kết quả theo user là đã hiểu hành vi thật.

## 6. Model training và serving song song

```mermaid
flowchart TD
    C["Khóa API, passage và feature contract"] --> S["Serving: lexical, UI, events"]
    C --> T["Training: migrate labels, train, eval"]
    S --> A["Adapter acceptance fixtures"]
    T --> B["Versioned model bundle"]
    A --> I["Integration và benchmark"]
    B --> I
    I --> P["Publish release hoặc giữ baseline"]
```

Serving không chờ fine-tune: lexical-only là profile hợp lệ; tiếp đến pretrained E5 được pin; fine-tuned model thay qua adapter. Không dùng vector ngẫu nhiên/mock để báo chất lượng. Stage 2 identity/heuristic chạy được trước learned ranker; response công bố ranker_id và pipeline profile.

Model bundle là đầu ra training, không phải một file weight rời. Bao gồm tokenizer/checkpoint hashes, pooling, normalization, length limits, passage builder hash, training dataset manifest và eval report. Query vector, corpus vectors và model revision phải cùng một không gian embedding; cùng 384 chiều vẫn có thể không tương thích.

Thêm POI không bắt buộc train lại: encode POI bằng model đang dùng, cập nhật index theo release mới. Đổi checkpoint hoặc passage policy bắt buộc encode lại các document bị ảnh hưởng và kiểm tra quality. Không quảng bá một checkpoint cũ sang corpus/passage mới chỉ dựa trên báo cáo v1.

### Luồng dữ liệu train Stage 2

```mermaid
flowchart TD
    E["Events và fixture histories"] --> H["Snapshot trước cutoff"]
    Q["Requests có context"] --> C["Frozen candidate retrieval"]
    H --> F["Feature factory dùng chung"]
    C --> F
    L["Nhãn ý định độc lập"] --> T["Train và eval ranker"]
    F --> T
    T --> B["Ranker bundle có feature hash"]
    B --> R["Release registry"]
```

Exposure/selection logs chỉ là quan sát có thiên lệch hiển thị; không tự biến unclicked thành negative. Nhãn scenario độc lập với ranker dùng để sinh features. Snapshot history được cố định trước request, không đưa lựa chọn của request đó trở lại làm input.

## 7. Đánh giá không trộn mục tiêu

| Track | Điều kiện | Metric chính |
|---|---|---|
| Stage 1 độc lập | Fixed corpus/scope, không router/context | CandidateHit@20/50, Hit@1/5, MRR@10 trên query đủ định danh |
| Brand group | Bare brand/alias/namespace đã khóa | Any-compatible hit, compatible coverage, group MRR |
| Address exact | Number/code observed trong resolved scope | Hit@1/5, MRR@10, exact preservation |
| Address fallback | Unseen/conflict theo contract; không hidden single target | AddressScopeHit@K, SameStreetHit@K, wrong-street hijack, rescue/harm |
| Autocomplete | Session/prefix có qrels thích hợp | Hit@5, MRR@5, prefix-length slices, ký tự tối thiểu target vào top-K |
| Ambiguity | Nhiều địa điểm phù hợp | Any-compatible hit và known-compatible recall; không bắt đoán một branch |
| IME | Raw keys chưa engine-verified | Diagnostic, không quality gate |
| Structured code | Có/thiếu namespace tách riêng | Case study và metric khi đủ mẫu, không gộp tên POI thông thường |
| Scope router | So global retrieval và scoped retrieval cùng N | CandidateHit delta, explicit remote miss, latency; đo actual candidates sau cap |
| Stage 2 fixed candidates | Cùng candidate snapshot | Ranking uplift, conditional Hit/MRR/nDCG theo rubric |
| Toàn pipeline | Router + rescue + ranker | End-to-end Hit, wrong branch, remote preservation, pair accuracy, latency |

Corpus càng lớn, positive/negative càng cần theo đúng query: một branch ngoài Hà Nội vẫn có thể phù hợp với query “Highlands”. Train positive có thể vẫn ở Hà Nội; hard negatives lấy toàn quốc nhưng phải loại known-compatible/entity siblings, không mặc định mọi object mới là negative. Stage 1 không được học “gần origin” từ nhãn single-target khi input không có origin.

Giữ `gold_stage1_v1` như frozen comparison/regression set W1; không dùng nó để tune lại policy sau khi đã xem kết quả. Workspace train 20k và checkpoint 500 không phải architecture holdout hoặc human-gold. Target đánh giá chung gồm `gold_stage1_v2`, `gold_stage1_brand_v1` và `address_scope_eval_v1` theo `STAGE1_EVALUATION_SUITE.md`; từng suite phải khóa label trước khi mở model output. Golden context tạo sau: gồm origin-sensitive/invariant, null-origin, explicit far destination, time/user intervention. Có thể bắt đầu 100–150 diagnostic pairs và 2.000–5.000 synthetic pairs để phủ điều kiện; không suy số mẫu lớn là bằng chứng thực tế.

Sampler origin có sorted IDs, RNG/version/seed, pool hash, distance strata `[0,1), [1,3), [3,10), [10,30), >=30 km`, null-origin riêng; origin/target/candidates cùng corpus. Target-distance-bin chỉ là audit, không phải feature. Audit target-is-nearest trên comparison pool query-compatible độc lập với retrieval.

Chọn cấu hình bằng dev; khóa trước comparison/holdout. Paired cluster bootstrap theo query_family_id cho Stage 1, theo independent user/scenario cluster cho Stage 2; không coi nhiều keystroke cùng phiên là mẫu độc lập. Unknown/unjudged không tự thành relevance 0. Timeout/degraded vẫn nằm trong mẫu số end-to-end.

## 8. Performance, failure và cập nhật

Mục tiêu ban đầu để đo: API Stage 1 p95 ≤100 ms; personalized p95 ≤150 ms, p99 ≤300 ms ở profile 10 QPS, 8 vCPU/32 GiB, một API worker/model instance, Elasticsearch local single-node, không chạy ETL/train đồng thời. Đây là budget thử nghiệm, không SLA hoặc benchmark đã có. Client debounce 120 ms đo riêng; không cộng p95 các bước thành p95 tổng.

Server deadline 180 ms; branch deadline và admission control mô tả trong config. Khi model/search branch hết hạn, trả fallback hợp lệ với degraded flags; không kéo dài vô hạn để đủ 5 POI. Không có dependency nào trả kết quả hợp lệ thì 503. Query hợp lệ nhưng không match trả 200 với empty results. Track timeout, cache, route và query length riêng.

Một triệu vector 384 chiều FP32 có 1,536 GB thập phân dữ liệu vector thô; 10 triệu có 15,36 GB, chưa gồm ANN, text index, heap, bản sao. Quy mô thật phải audit và load-test. Không suy QPS từ công thức dung lượng.

Release registry pin một tuple corpus/index/encoder/passage/feature/ranker/policy. Build staging → kiểm tra hash/ID/vector/norm → quality/latency gate → warmup → đổi active release pointer → giữ release cũ cho requests đang chạy và rollback. Mỗi request resolve index name cụ thể từ tuple, không đọc alias có thể đổi giữa hai nhánh. Không tái sử dụng ranker có feature schema hoặc candidate policy không tương thích.

## 9. Thứ tự triển khai

| Mốc | Serving / data | Training song song | Hoàn thành khi |
|---|---|---|---|
| M0 contract | Import stable POI, API models, release registry, text builder | Giữ audit migration stable-v1; đồng bộ release/policy IDs với code | Contract tests, IDs/versions, sample request pass |
| M1 demo chạy được | Lexical, query-only UI, details/select, map/distance | Exact dense baseline và fine-tune Stage 1 | Không cần trained model để chạy demo; ghi đúng lexical profile |
| M2 scale và retrieval | National ETL/audit, region sidecar, router/global lane | Hard negative mining và eval corpus mở rộng | Có C0/C1 snapshots, fallback, remote cases; không tune test |
| M3 hybrid serving | Nạp model bundle, ANN, cache/latency | Khóa encoder và quality config | Exact-vs-ANN report, no mixed releases |
| M4 Stage 2 | History snapshots, rescue, feature builder, heuristic | Context sampler/eval, LambdaMART → MLP | Candidate/ranking gains tách riêng, cutoff đúng |
| M5 integrated demo | User/time/origin panel, trace/debug, release switch | Golden/independent evaluation | Cả thiếu context và đích xa hoạt động; quyết định model bằng evidence |

Gates correctness phải pass trước khi tích hợp. Mốc metric chất lượng tuyệt đối được khóa sau pilot khi biết rubric/golden; không bịa một mức Hit@1 cho query mơ hồ. Kỹ thuật và train chạy song song, nhưng công bố chất lượng Stage 2 chờ candidate policy và encoder snapshot đã khóa.

## 10. Cơ sở kỹ thuật và nguồn

Bốn nghiên cứu bổ sung, giới hạn bằng chứng, training/mining contract và gates được chốt trong [Training và nâng cấp retrieval](TRAINING_AND_RETRIEVAL_PROTOCOL.md). Các con số uplift trên passage benchmarks không phải kết quả POI Việt Nam.


E5-small có embedding 384 chiều; retrieval dùng prefix query/passsage tương ứng, pooling và normalization phải khớp giữa train và inference. [Model card chính thức E5-small](https://huggingface.co/intfloat/multilingual-e5-small/raw/main/README.md).

Filtered vector search cần đặt filter đúng cơ chế của engine; post-filter có thể thiếu top-K dù vùng còn nhiều POI phù hợp. [Elasticsearch kNN pre-filter và post-filter](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-knn-query).

Edge n-gram dùng ở index, search analyzer đơn giản hơn; cần field full-name để không mất query vượt max_gram. [Elasticsearch edge n-gram](https://www.elastic.co/guide/en/elasticsearch/reference/current/analysis-edgengram-tokenizer.html).

LambdaMART triển khai bằng LGBMRanker với group theo request; không chia candidate rows của một request qua nhiều splits. [LightGBM LGBMRanker](https://lightgbm.readthedocs.io/en/stable/pythonapi/lightgbm.LGBMRanker.html).

Các bài Baidu Maps người dùng đưa là tham khảo nghiên cứu lịch sử. Bản v1 không lấy số latency/uplift trong bài làm cam kết, không bắt buộc sao chép attention/prefix model để bắt đầu code. Lựa chọn hiện tại là quyết định thiết kế của dự án cần được benchmark trên corpus của dự án.
