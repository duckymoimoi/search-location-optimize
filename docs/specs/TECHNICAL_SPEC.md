# Đặc tả kỹ thuật triển khai — POI Search v1

Revision: 15/09/2026. Đọc [trạng thái as-built](../as-built/CURRENT_STATE.md) và [thiết kế hệ thống](SYSTEM_DESIGN.md) để phân biệt phần đã chạy với kiến trúc đích; file này chốt hành vi mục tiêu. OpenAPI, config và schema baseline hiện nằm trong [`contract-package-v1`](../contract-package-v1/README.md). Config có thể đổi sau benchmark nhưng mỗi lần đổi phải tạo policy/release version.

**Phạm vi contract:** các interface đích bên dưới không tự thay đổi API demo `app.py` v6. Demo hiện dùng cùng SuggestRequest cho query-only/personalized, `top_k=1..50`; query-only bỏ qua context trong ranking. Demo đã có Goong road preview, events in-memory; router, PostgreSQL/history/time features và một số validation/deadlines vẫn là kế hoạch. Giữ HTTP schema hiện tại khi thử thuật toán; không triển khai API-breaking changes từ config/spec cũ. Không coi files OpenAPI/config trong gói v1 cũ đã được cập nhật bởi revision tài liệu này.

[Training và nâng cấp retrieval](TRAINING_AND_RETRIEVAL_PROTOCOL.md) chốt mining, loss/masks, MRL, late interaction và evaluation. Những lựa chọn thí nghiệm chưa có artifact phải tắt mặc định.

## 1. Stack và cấu trúc code

| Thành phần | Lựa chọn v1 |
|---|---|
| API / orchestration | Python 3.12, FastAPI/Pydantic, asyncio; model work chạy trong bounded executor |
| Lexical / ANN serving | OpenSearch, client opensearch-py; benchmark exact chạy riêng bằng NumPy |
| Model | PyTorch + Transformers/Sentence Transformers; E5-small; LightGBM cho ranker đầu tiên |
| Data | PyArrow Parquet, PyOsmium, Shapely; ETL streaming/checkpoints |
| History và exposures | PostgreSQL; migrations có version; không cần PostGIS ở MVP |
| UI | React + TypeScript, MapLibre; style/tile URL qua config |
| Deployment | Docker Compose: UI/API/OpenSearch/PostgreSQL; job train/index chạy profile riêng |
| Quan sát / kiểm tra | Structured JSON logs, metrics histograms, pytest, HTTP/load-test harness |

Phiên bản package/image cụ thể phải resolve, test và khóa vào lockfile + image digest trong mốc M0; tài liệu không giả vờ đã kiểm thử một bộ dependency mới. PyArrow 25.0.1 và Shapely 2.1.2 là phiên bản builder corpus hiện có. Không dùng tag `latest` trong release. Không mặc định public tile/routing demo server đáp ứng workload.

Đề xuất module trong repo: `apps/api`, `apps/web`, `src/contracts`, `src/query`, `src/scope`, `src/retrieval`, `src/context`, `src/ranking`, `src/events`, `src/releases`, `jobs/corpus`, `jobs/index`, `jobs/train`, `jobs/eval`, `tests/contracts`, `tests/integration`. Contract và feature/text builders là package dùng chung; notebook Kaggle/Colab chỉ import package và config, không copy logic xử lý riêng.

## 2. Hợp đồng dữ liệu

### 2.1 Corpus và derived index

Input chính là 18 cột của stable v1: `poi_id, name, aliases, category, brand, ref, address, address_status, context, ranking_point, routing_point, destination_searchable, origin_search_eligible, pickup_access_verified, entity_group_id, branch_id, complex_id, preserve_individual_access_point`.

Mọi join dùng poi_id; không join bằng tên. Không ghi nguồn/ranker flags vào bảng POI. Lưu corpus version một lần trong manifest, đưa version vào mọi request/event/dataset manifest có tham chiếu POI.

| Derived artifact | Key / fields bắt buộc |
|---|---|
| `poi_regions.parquet` | poi_id, region_osm_id, admin_level, admin_scheme_version, membership_method, boundary_hash; nhiều dòng nếu overlap |
| `region_catalog.parquet` | region_osm_id, label, aliases, parent_ids, bbox, geometry_ref, admin_scheme_version |
| `index_documents.parquet` | poi_id, corpus_version, field text theo mapping, ranking_point, region_ids, entity flags |
| `vectors.npy` và `vector_ids.parquet` | matrix float32 [M,D], D=384 baseline hoặc serving_dim trong manifest, contiguous row_index → poi_id duy nhất |
| `candidate_snapshots.parquet` | case/request ID, release_id, stage, scope plan hash, candidate IDs/ranks/sources, timings, degraded flags |
| `dataset_manifest.json` | corpus hash, query/qrels/eligibility hashes, split policy, provenance, label semantics |

Region membership là derived artifact, không diễn giải admin name v8 thành một region ID đã xác minh. Chưa có region sidecar thì chỉ chạy radius/global; request preferred region không resolve được trả 422. Ngoài corpus coverage trả empty/alternatives có nhãn phạm vi, không bịa POI.

### 2.2 Lexical fields

| Field | Xử lý / boost khởi đầu |
|---|---|
| name_exact, alias_exact | NFKC + lowercase + trim; accent-preserving; boost 12 / 10 |
| name_text, aliases_text | Text tokens, giữ original; boost 5 / 4 |
| name_folded, aliases_folded | Accent-folded riêng, không ghi đè original; boost 3 / 2 |
| name_prefix, aliases_prefix | Index edge n-gram min=1,max=20; search không n-gram; boost 3 / 2 |
| ref_exact, housenumber_exact | Keyword giữ slash/hyphen; boost 8 / 8 khi parser có evidence |
| street_text, place_text | Text field địa chỉ; boost 3 / 2 |
| context_text | Nearby/container/admin có nguồn; boost 0.5, không dùng exact address guard |

Các boosts là một cấu hình khởi đầu trong ma trận dev nhỏ. Exact name không đồng nghĩa unique entity. Với mã/địa chỉ, so match trên nhiều fields; không dùng fuzziness làm đổi số nhà. Fuzzy tối đa edit distance=1 cho token chữ dài ≥4, chỉ khi route cho phép; không fuzzy prefix 1–2, ref, số nhà. Token giữ `/` trong field structured; name tokenizer và structured tokenizer không dùng chung một policy phá dấu slash.

Query >max_gram vẫn đi qua full-name fields. Không truncate toàn query xuống 20 ký tự. Telex/VNI raw chưa xác minh engine giữ diagnostic; MVP không tự coi một transliteration rule là canonical IME. Xử lý frontend composition theo mục UI, không tự tắt IME người dùng.

### 2.3 Dense và ANN

E5-small dimension=384, attention-mask mean pooling, L2-normalized, similarity dot product của normalized vectors. Prefix `query: ` / `passage: ` được thêm đúng một lần trong encoder adapter. Query max_length=64 và passage max_length=192 là initial config; bundle phải khai báo và đo truncation rate. Không thay length khi load model mà vẫn dùng cùng embedding-space ID.

`embedding_space_id = SHA256(checkpoint_hash + tokenizer_hash + pooling + normalize + query/passage_prefix + length_limits)` theo canonical JSON. `passage_builder_hash` riêng trong index manifest. Cả hai phải khớp runtime query encoder/index; encoder dimension giống nhau chưa đủ.

ANN profile ban đầu HNSW cosine, M=16, ef_construction=128; search effort thử theo engine/version được khóa. Dùng filter bên trong supported k-NN query cho lane có scope, không lấy top-K quốc gia rồi post-filter radius. Adapter phải có integration test chứng minh có ≥K eligible records thì không thiếu K vì đặt filter sai. Không cung cấp mapping JSON engine-specific chưa chạy và gọi đó là cấu hình production đã kiểm chứng.

## 3. Module contracts và thứ tự xử lý

Interface tối thiểu (Python Protocol hoặc tương đương):

```python
parse(query: str) -> QueryEvidence
plan_scope(evidence, resolved_context, coverage, policy) -> ScopePlan
encode_query(query: str, deadline) -> Vector | Unavailable
retrieve_lexical(evidence, scope, depth, release, deadline) -> BranchResult
retrieve_dense(vector, scope, depth, release, deadline) -> BranchResult
assemble_candidates(branch_results, evidence, budget) -> CandidateSet
get_history(subject, cutoff, snapshot_seq, limit=50) -> HistorySnapshot
rescue(candidates, evidence, context, history, release, deadline) -> CandidateSet
build_features(candidates, evidence, context, history) -> FeatureBatch
rank(feature_batch, ranker_bundle, deadline) -> list[Score]
```

BranchResult gồm status=`ok|timeout|error|disabled`, IDs, ranks, raw scores, scope ID, source, elapsed_ms. Disabled theo policy không phải error. Candidate gồm poi_id, per-branch evidence/scores/masks, scope membership, protected flags; raw score không phải xác suất đúng.

Request pipeline:

1. Validate payload và session, pin immutable release. expected_corpus_version mismatch →409; không đổi corpus âm thầm.
2. Capture server request time, history snapshot sequence và context revision. Production không nhận arbitrary user/time override. Resolve origin POI từ cùng corpus; GPS/map là tọa độ, không cần ép vào origin pool.
3. Parse query và scope. `/v1/suggest` luôn global query-only; personalized mới chạy scope router/history. Query rỗng sau trim →200, results=[], exposure=null, không model/history rescue.
4. Nếu bật dense, encode query một lần. Lexical và history có thể chạy trong lúc encoder đang xử lý; dense branches dùng chung vector.
5. Hợp branch bằng RRF, cap candidate budget. Deadline shared, có semaphore giới hạn pending work. Radius retry chỉ một lần và khi còn ≥40 ms.
6. Chạy bounded rescue nếu bật và đủ ≥40 ms; build features, score, apply evidence constraints, dedup display theo entity policy, backfill từ danh sách đã rank. Không lén fetch target từ qrels.
7. Persist exposure nếu có results. Nếu exposure store lỗi, có thể trả kết quả đọc-only với `selectable=false`, exposure=null, degraded reason. Không cấp một exposure ID chưa lưu được.
8. Response chứa snapshot versions và timings. Query cancellation phải hủy tác vụ con khi backend hỗ trợ; inference CPU đang chạy có thể không preempt được, giữ semaphore đến khi task thực sự xong và bỏ output muộn; requests quá tải trả 429, không xếp queue vô hạn.

### RRF và budget

Trong lane: `rrf(p)=sum_b 1/(60+rank_b(p))`; rank bắt đầu 1, branch không chứa p đóng góp 0. `lane_score=rrf / (2/61)` với denominator cố định 2 branches. Không dùng score này như xác suất. Khi chỉ lexical bật, thứ tự vẫn đúng; feature masks ghi dense absent. Giữa lanes dùng max(lane_score), tie-break poi_id.

Protected explicit tối đa 5 theo joint address/ref + namespace evidence, tie-break text score rồi poi_id. Tiếp global reserve tối đa 10 ID khác protected, sau đó primary, global remainder tới N=50. Candidate guard không tự tạo thứ hạng top-1. Rescue bỏ tối đa 10 ID thấp nhất không protected/reserved; nếu thiếu slots thì giảm rescue, không tăng N. Nếu match ít thì trả ít hơn N/K.

N=50 là budget nội bộ mặc định; UI hiển thị 5, API demo hiện chấp nhận top_k=1..50 và phải giữ tương thích. Eval harness có final K=5/20/50 và access internal snapshots; không mở candidate depth/model choice cho public client.

## 4. Context và feature schema

[`contracts/features.json`](../contract-package-v1/contracts/features.json) là thứ tự input cho tabular models. Feature factory dùng cùng code cho offline replay và serving. Missing numeric biểu diễn value=0 + missing flag riêng; không diễn giải khoảng cách thiếu là 0 m. Raw BM25 được giữ debug, model dùng reciprocal rank/bounded score và mask; không coi BM25 từ các scopes là cùng scale.

Geo distance tính geodesic giữa anchor và ranking_point. Time lấy local hour/day theo Asia/Ho_Chi_Minh; lưu timestamps UTC có offset. Không dùng opening-hours feature khi corpus chưa có field đã parse/kiểm chứng. History lấy tối đa 50 events hợp lệ, trước context_time và thuộc snapshot_seq; compute POI/brand/category frequency, recency và same-hour affinity. Không dùng raw user_id, target ID, simulator persona, distance stratum, query family hoặc dataset case_type làm model feature.

History events khác corpus chỉ resolve qua mapping release migration có nguồn. POI đã xóa/không resolve được bỏ khỏi features và ghi missing count; không join bằng tên. Demo fixtures và live selections có namespace riêng; replay frozen eval không đọc live history. Cold user/null origin là đường xử lý bình thường, không degraded.

Heuristic v6: giữ Stage 1 order; khi anchor hợp lệ chỉ hoán đổi vị trí các ứng viên cùng lớp khớp cụm name/alias với head. Full name, cụm hoàn chỉnh, prefix cuối và mức khớp dấu phân biệt; số/mã phải khớp nguyên. Default window=10, RRF ratio so head≥0.5, distance bands=500m; các slots ngoài nhóm giữ nguyên. Thiếu head coordinates/không đủ equivalence thì identity. Đây không phải model hiểu ý định hay bảo đảm non-regression; cần counterfactual/explicit/remote evaluation. Không cộng trực tiếp distance với RRF. Chi tiết và hạn chế ở training protocol.

Nếu text reranker được bật thì v6 nhận thứ tự text mới; phải đánh giá lại head/cohort, không kế thừa kết quả v6 cũ. Learned ranker cần same candidate policy/features và qua gate riêng.

## 5. HTTP API và trạng thái UI

OpenAPI trong gói chốt types/required fields. All IDs string; coordinates object lat/lon trong API, GeoJSON coordinate order lon/lat. Distance mét, duration giây. Errors gồm code, message, request_id nullable; không trả stack trace.

| Endpoint | Vai trò |
|---|---|
| POST /v1/sessions | Tạo session demo và cookie; rate-limited, không nhận subject từ client |
| GET /v1/demo/users | Danh sách fixture users cho panel, chỉ server demo |
| GET /v1/status | Active versions, coverage, capabilities, readiness |
| GET /v1/origins | Search origin demo; q, limit≤50, opaque cursor, corpus_version |
| GET /v1/pois/details | poi_id và corpus_version qua query params, tránh ambiguity slash trong OSM ID |
| POST /v1/suggest | Query-only: demo nhận cùng schema nhưng không dùng origin/user/time để ranking |
| POST /v1/suggest/personalized | Query + anchor/vùng + demo context được phép |
| POST /v1/exposures/displayed | UI xác nhận exposure được hiển thị; không mặc định generated=seen |
| POST /v1/select | Ghi lựa chọn từ exposure, idempotent |
| POST /v1/route-preview | Preview sau selection, độc lập suggest |

### Context request

Origin là một trong: `{kind:poi, poi_id}`; `{kind:gps, point, accuracy_m, observed_at}`; `{kind:map, point}`; hoặc null. POI origin phải origin_search_eligible và cùng corpus. GPS quá 120 s hoặc accuracy>200 m bị bỏ cho scope/geo, ghi context note; future observation>30 s trả422. Đây là thresholds khởi đầu. `preferred_region_id` là vùng người dùng chọn rõ; không lấy arbitrary region string làm ID.

UI khởi tạo bằng POST /v1/sessions, server tạo opaque session ID/cookie và namespace demo. Cookie HttpOnly, SameSite=Lax, Secure khi HTTPS; mọi session_id trong body phải khớp cookie. GET /v1/demo/users trả registry ID/label, không trả history. Khi triển khai ngoài demo phải tích hợp auth của ứng dụng. Authenticated subject lấy từ server session/token. `demo_user_id` và `context_time` chỉ được dùng khi server bật demo, chọn trong registry fixtures; production có các fields này khác null →403. Không để public client giả user để đọc history. Query-only benchmark gửi context=null và giữ fixed scope; demo vẫn chấp nhận các fields context trong shared schema, không dựa additionalProperties=false để chứng minh context đã bị chặn.

### Selection và exposures

DB tables tối thiểu:

| Table | Khóa và fields |
|---|---|
| sessions | session_id PK, subject_id/namespace, latest_context_revision, created_at |
| exposures | exposure_id PK, session_id, request_id, context_revision, release tuple JSON, resolved_context JSON, shown_ids JSON, created_at, expires_at, displayed_at nullable |
| selections | selection_id PK, session_id, idempotency_key, payload_hash, exposure_id FK, selected_poi_id, recorded_at, occurred_at, source; UNIQUE(session_id,idempotency_key) |
| history_events | monotonic ingest_seq, subject/namespace, event_time, selected_poi_id, origin snapshot, corpus_version, event_source |

Suggest cập nhật latest_context_revision bằng max, tránh request cũ ghi đè mới. Exposure TTL 15 phút. Selection chỉ hợp lệ khi ID trong shown_ids, session/subject khớp, revision bằng exposure và latest session, release còn đọc được, exposure chưa hết hạn. UI phải gửi displayed trước select; select trả409 nếu exposure chưa được xác nhận hiển thị. Retry cùng idempotency key/payload trả cùng selection; payload khác →409. Trong transaction, persist selection và append history event; không ghi history nếu selection chưa commit. Retry event không tăng count history lần hai.

Server lấy user/origin/time/versions từ exposure, không tin fields do client chèn vào select. Lưu recorded_at và demo occurred_at riêng; không gọi click demo là ground truth. Chưa chọn không tự thành negative. API không cung cấp endpoint ghi tùy ý history production.

### Response, degraded và errors

Response luôn có request_id, context_revision, exposure_id nullable, selectable, versions, scope_summary, resolved_context_time, history_version nullable, candidate_count, results, degraded_reasons và timings_ms. Mỗi result có poi_id/name/address_text/context_text, rank, ranking_point, routing_point nullable, pickup_access_verified và ranking_distance_m nullable. Không public raw model score như confidence.

200 degraded khi một nhánh cần thiết lỗi nhưng còn kết quả hợp lệ; disabled theo profile không degraded. 401 thiếu/sai session; 422 payload/origin invalid; 404 ID không có; 409 corpus/exposure/revision/idempotency conflict; 403 demo/auth violation; 429 overload; 503 không có search dependency usable. Null-origin/zero matches là 200 bình thường. Reason enum trong OpenAPI; trả cả fallback chất lượng vào eval mẫu số.

### UI flow

Chọn origin → nhập destination → top-5 list/map → displayed ack → chọn destination → show hai điểm và preview. Panel demo đổi riêng origin/user/time; mỗi lần tăng context_revision, xóa selection/exposure cũ, giữ query rồi request lại. Debounce 120 ms; sequence/request ID loại response cũ; abort request trước khi được phép. Không dispatch raw composition khi IME đang composing; gửi committed text ở compositionend. IME diagnostic mode riêng có thể gửi raw_keys nhưng không trộn metric với committed text.

Query-only tab khóa origin/user/time controls và ghi rõ fixed scope. Map dùng ranking points, hiển thị “chưa xác minh điểm đón” ở details khi cần chọn; không rải metadata kỹ thuật vào luồng người dùng. Debug panel riêng mới hiển thị candidates/scope/version/latency.

### Route preview

Thiết kế đích phân biệt straight_line/road; demo hiện đã implement Goong road với tọa độ hoặc POI ID và allow_fallback, bên cạnh straight_line. Không gỡ functionality này khi thay retrieval/rerank. Input origin/destination POI ID cùng corpus; origin null →status missing_origin. Geometry GeoJSON LineString giữa ranking points; geodesic_distance_m có giá trị, route_distance_m/route_duration_s=null. Demo RouteRequest có mode straight_line|road, không có auto. Road preview hiện dùng tọa độ supplied hoặc ranking_point theo code gốc, chưa chứng minh pickup access. Chuẩn routing/access verification là yêu cầu triển khai tiếp theo; không diễn giải road result như pickup verified. Road strict không fallback →unavailable. allow_fallback →straight_line với lý do. Không gọi route cho mỗi candidate/keystroke; deadline riêng 1.000 ms. Road adapter phải giữ input/snapped points và graph version; car profile không tự được coi là xe máy.

## 6. Model delivery và training parallel

### Encoder bundle

Thư mục gồm weights/tokenizer, manifest theo model_bundle.schema.json, file checksums, eval_report.json và smoke_vectors.npz. Training bàn giao thêm 10 fixed query/passages với expected vectors để adapter kiểm tra float tolerance; không dùng vectors mock. CPU/ONNX/int8 export là artifact khác có precision metadata, phải so quality/latency với bản gốc trước activate.

Vòng train đầu: E5-small, max 3 epochs, lr=2e-5, effective batch 32 là initial config; seed, precision, device, actual batch và checkpoint selection lưu đầy đủ. Ghi microbatch và negative-pool size riêng; gradient accumulation không tự tăng số in-batch negatives trong mỗi forward pass. Không train lại toàn20k bằng default eligibility cũ sau đổi corpus. Trước train phải migrate evidence/eligibility, loại 4 qrel links không còn searchable, audit query dựa vào address đã bị bỏ; version dataset mới.

Train positives có thể Hà Nội trong khi index toàn quốc. MNRL/in-batch negatives chỉ dùng khi đã mask known-compatible/same-entity collisions; nếu implementation không mask được, construct batches không xung đột hoặc dùng explicit-negative loss. Broad brand/prefix không được ép single-target từ origin ẩn. Hard negatives lấy từ lexical/dense corpus mở rộng sau pass đầu; unknown/unjudged không gắn0 vô điều kiện.

### Training và representation contract bổ sung

Áp dụng [Training và nâng cấp retrieval](TRAINING_AND_RETRIEVAL_PROTOCOL.md): mixed negatives có positive/ignore masks, strict holdout exclusion, mining manifest; optional teacher offline; MRL 96/192/384 có loss/normalization riêng từng prefix; late-interaction chỉ thử trên fixed top-50 trước context. Không coi các lựa chọn này là triển khai xong.

Model manifest mới có representation_type, full_dim, serving_dim, nested_dims (nếu MRL), checkpoint/passage/tokenizer hashes. Single-vector index assert D theo manifest, không hardcode 384 cho mọi model. Late interaction dùng token-vector sidecar/adapter riêng; không nạp như một vector field E5.

Default `text_reranker=none`. Khi bật phải có model hash, deadline, original/text/context ranks trong internal trace và fallback identity có degraded flag. Public response keys giữ nguyên. Không đưa teacher/mining metadata vào request schema hoặc bảng POI chính.

### Ranker bundle

LambdaMART fit theo group=request, feature order/hash, label rubric, candidate policy và embedding-space ID được khóa. Group train/dev/test nguyên request/family; warm-user temporal và cold-user disjoint tracks riêng. Initial grid tối đa num_leaves={15,31}, lr=0.05, max rounds=300, early stopping theo dev trong trainer đã pin. Không chọn attention trước khi baseline có kết quả.

Feature/time/user/candidate snapshots cho training phải dùng được qua cùng feature factory online. Model chỉ thắng synthetic được gắn synthetic evidence; không tự nâng thành human behavior verified. Khi encoder đổi, ranker dựa embeddings hoặc candidate distribution cũ cần re-evaluate/retrain, không hot-swap mù.

### Model-independent integration gate

Serving team có thể pass M1 bằng lexical-only và heuristic. Training team pass adapter khi hashes/shape/prefix/pooling/normalization/fixture vectors đúng. Quality gate riêng: model phải có report trên fixed corpus/query protocol, không chỉ training loss. Release registry chỉ chọn các bundles tương thích; config example chứa placeholder không được dùng như manifest model thật.

## 7. Evaluation và acceptance

Ma trận E0–E5, margins non-inferiority đề xuất và paired CI ở [Training và nâng cấp retrieval](TRAINING_AND_RETRIEVAL_PROTOCOL.md). Quality dùng exact trước ANN; đo riêng MRL truncation, compression và ANN loss. Rerank trên fixed top-50 không thể tự cải thiện CandidateHit@50.


Metric single-target: Hit@K=1[target thuộc topK], MRR@K=1/rank nếu rank≤K, ngược lại0. Multi-positive: dùng rank của positive đầu tiên cho reciprocal rank; known-compatible recall=|topK∩known positives|/|known positives|, ghi rõ qrels incomplete. CandidateHit cho context là target/acceptable set có mặt trước ranker; không chèn target để cứu metric.

Kiểm tra scope: C0 global query-only, C1 router+Stage1, C2 C1+rescue, rồi từng ranker trên same snapshots. Rescue rate=#(miss C1, hit C2)/all eligible cases; harm rate=#(hit C1, miss C2)/all; báo thêm denominator conditional khi dùng. Có target trong geographic scope chưa đủ: cap/ANN có thể vẫn làm miss.

ANN recall@K vs exact = overlap(topK_ann, topK_exact)/K trên cùng vector space, eligible pool, metric và tie policy. Nếu eligible pool<K, denominator=min(K,pool_size); empty pool n/a. Đo riêng filtered/global; ANN recall không thay relevance metrics.

| Gate | Điều kiện pass trước tích hợp |
|---|---|
| Corpus/import | ID unique; searchable label; tọa độ finite; FK đầy đủ; vector↔ID bijection; source hashes đúng |
| Model adapter | Bundle schema/hash/space khớp; vector dim/norm đúng; fixture cosine deviation≤1e-5 cho cùng FP32 runtime hoặc tolerance riêng được ký trong report |
| Geo/remote | Null/stale origin xử lý đúng; global lane không bị filter; explicit remote fixture không bị policy hard-exclude |
| Candidate budget | N≤50; rescue≤10; không duplicate; không phá protected slots; mọi source flag trace được |
| Events | Select ngoài exposure bị chặn; stale revision bị chặn; retry idempotent; history không chứa future/request outcome |
| Quality | Chọn config bằng dev; frozen comparison không tune; so baseline cùng K; human/golden gate do chủ dự án khóa sau pilot |
| Serving | Report p50/p95/p99, offered/achieved QPS, errors/degraded, cache hit/miss và hardware; pass budget đã đăng ký hoặc giữ profile baseline |
| Release | Hai lane và details cùng release; rollback không mix vectors/model; expired exposure trả đúng error |

Thêm contract fixtures cho: `highlands`+hai origins (không yêu cầu query-only chọn duy nhất), địa chỉ explicit xa, `16/2` không mất slash, mã S702 có/thiếu namespace, lỗi dấu, one-character prefix, null history, model timeout, empty corpus match, race UI, future event, same-label separate platforms. Fixtures synthetic chỉ test hành vi đã nêu, không giả golden relevance thực tế.

## 8. Vận hành và release contract

Config initial: request deadline180 ms; encoder soft timeout60 ms, retrieval branch70 ms, ranker20 ms; đều clamp theo thời gian còn lại. Deadline không phải phép cộng durations bảo đảm p95. Model queue max32 tasks, overflow429; API phải đo queue time. Query cache LRU 10.000 entries keyed by exact normalized accent-preserving query + encoder space + preprocessing version. Không cache personalized response ở MVP. Retrieval cache nếu thêm phải include concrete release/scope/coordinates/policy; không chỉ query.

Liveness chỉ kiểm process; readiness yêu cầu corpus/release/lexical/search connection load được. Lexical-only profile không yêu cầu encoder. Personalized readiness chấp nhận heuristic nếu đúng configured ranker. Unavailable ranker/model cần fallback với flags, không trả nhầm model_id learned.

Metrics: request_total by profile/status/degraded/length_bucket; stage duration histograms; candidate counts by source; protected/rescue counts; embedding cache hit; queue/rejections; exposure/selection errors; corpus/model mismatch. Logs operational mặc định không ghi raw location/history/query; debug fixtures trong namespace demo có retention cấu hình. Truy cập details/history phải cùng session/subject policy; OpenSearch/PostgreSQL không public ra ngoài API.

Release activation đọc registry atomically. Retain old release ít nhất bằng exposure TTL + longest active request; remove sau drain. Bất kỳ đổi passage/normalizer/scope/feature/order đều versioned; giữ manifest hash trong benchmark. Full reindex bằng staging là đường đầu tiên; incremental/upsert chỉ sau khi có delete/tombstone, entity split/merge và rollback tests.

OpenSearch filtered-ANN behavior, E5 adapter conventions và LGBMRanker group semantics tham chiếu các nguồn chính thức ở SYSTEM_DESIGN.md. Các giá trị radius/boost/deadline/hyperparameter trong gói là quyết định khởi đầu của dự án, cần đo trên corpus và workload thực.
