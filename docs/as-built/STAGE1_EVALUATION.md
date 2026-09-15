# Báo cáo đánh giá Stage 1 — OSM stable v1

Ngày chạy: 2026-09-14. Corpus: `hn-poi-stable-v1`. Dataset eval: `hnq20k-stable-v1-eval1`.

> **Biên snapshot:** các số retrieval/exact/ANN là artifact frozen; phần API/geo được đo trên policy v4 tại thời điểm báo cáo. Runtime hiện đã chuyển sang `search-policy-stable-demo-v5`/`heuristic-geo-v5`. Xem [Current state](CURRENT_STATE.md); phải replay benchmark trước khi gán các số v4 cho v5.

## Kết luận

Stage 1 đủ để chạy demo thật trên corpus OSM Hà Nội. Cấu hình khóa từ dev:

- Lexical: OpenSearch `L1_prefix_heavy`.
- Dense: checkpoint E5 fine-tuned v4, `passage_context`, dot product trên vector L2-normalized.
- ANN: HNSW Lucene, `M=32`, `ef_construction=512`, `candidates=200`.
- Hybrid: RRF, depth 50, constant 60.
- Router: độ dài query sau NFKC và bỏ khoảng trắng ≤4 dùng lexical; dài hơn dùng hybrid. Không dùng track, case type hoặc nhãn lỗi.

Không train Stage 2. Demo chỉ dùng heuristic:

`final = relevance_blend * relevance + geo_blend * exp(-distance_m/geo_decay_m)` sau evidence/category gate; exact name/alias được bảo vệ.

Không có origin hợp lệ thì geo term bằng 0. Chưa dùng history/user model.

## 1. Migration và tính hợp lệ dữ liệu

- 20.000/20.000 intended targets tồn tại và searchable.
- Loại 4/4.575.413 qrel links trỏ tới một record không còn searchable. Chúng đều thuộc query `w` rất mơ hồ; intended target không đổi.
- Audit 3.147 query có generation-time address qualifier. Có 22 query không còn đủ bằng chứng stable; vẫn giữ diagnostic nhưng loại khỏi supervised/main.
- Còn 6.060 query train hợp lệ và 9.847 main-metric candidates.
- Architecture holdout từng được đọc khi QA dữ liệu nên chỉ gọi là **architecture validation**, không phải blind final.

Xem `HANOI_QUERIES_20K/hanoi_queries_20k_stable_v1/validation.json` và `audit/stable_address_evidence.parquet`.

## 2. Chọn passage bằng dev

Checkpoint fine-tuned được chạy exact trên cùng 45.692 POI.

| Passage | Main Hit@5 | Main Hit@50 | Main MRR@10 | Autocomplete compatible@50 | Ambiguity compatible@50 |
|---|---:|---:|---:|---:|---:|
| address | 0,94955 | 0,98341 | 0,90758 | 0,86577 | 0,95405 |
| context | 0,94955 | 0,98341 | **0,91144** | **0,88591** | **0,96718** |

Chọn `passage_context`. Corpus encode P100 mất 38,89 giây (1.175 passage/s), so với 23,32 giây của address; đây là chi phí offline, không tăng query latency.

## 3. Fine-tuned E5 so với E5 zero-shot

Cùng corpus, passage, pooling, normalization, similarity và exact search.

| Split / slice | Model | Hit@5 | Hit@20 | Hit@50 | MRR@10 |
|---|---|---:|---:|---:|---:|
| Dev main, n=1.447 | zero-shot | 0,74637 | 0,80442 | 0,83967 | 0,68942 |
| Dev main, n=1.447 | fine-tuned | **0,94955** | **0,97167** | **0,98341** | **0,91144** |
| Test main, n=387 | zero-shot | 0,74935 | 0,81137 | 0,86305 | 0,70997 |
| Test main, n=387 | fine-tuned | **0,98191** | **0,98708** | **1,00000** | **0,97416** |
| Dev IME, n=164 | zero-shot | 0,44512 | 0,52439 | 0,60366 | 0,36763 |
| Dev IME, n=164 | fine-tuned | **0,73780** | **0,83537** | **0,86585** | **0,69043** |

Dev main, fine-tune tăng Hit@5 +0,20318, Hit@50 +0,14375, MRR@10 +0,22202. Paired cluster bootstrap theo family, 10.000 lần, cho CI95 `[0,18011; 0,22658]`, `[0,12363; 0,16399]`, `[0,19952; 0,24535]`.

Fine-tune chưa chứng minh cải thiện autocomplete: dev MRR@10 delta -0,00251, CI95 `[-0,03678; 0,03070]`. Không dùng dense đơn độc cho autocomplete.

## 4. Lexical, dense và hybrid

### Dev — dùng chọn kiến trúc

| Method | Main Hit@5 | Hit@20 | Hit@50 | MRR@10 | Auto Hit@5 | Auto Hit@50 |
|---|---:|---:|---:|---:|---:|---:|
| Lexical L1 | 0,96475 | 0,98203 | 0,98687 | 0,93745 | **0,68792** | **0,97651** |
| Dense exact | 0,94955 | 0,97167 | 0,98341 | 0,91144 | 0,45973 | 0,75503 |
| Hybrid ANN | **0,97236** | **0,99516** | **0,99724** | **0,94791** | 0,60067 | 0,95638 |

Paired cluster bootstrap dev:

- Lexical − dense: Hit@5 +0,01520, CI95 `[0,00068; 0,02970]`; MRR@10 +0,02601, CI95 `[0,00929; 0,04263]`.
- Hybrid − lexical: Hit@20 +0,01313, CI95 `[0,00633; 0,02088]`; Hit@50 +0,01037, CI95 `[0,00468; 0,01737]`; Hit@5 CI cắt 0.
- Lexical − hybrid trên autocomplete: Hit@5 +0,08725, CI95 `[0,04575; 0,13043]`.

### Frozen synthetic test

Chỉ cấu hình đã khóa được chạy.

| Method | Main Hit@5 | Hit@20 | Hit@50 | MRR@10 | Auto Hit@5 | Auto Hit@50 |
|---|---:|---:|---:|---:|---:|---:|
| Lexical L1 | **1,00000** | 1,00000 | 1,00000 | **0,99139** | **0,72840** | **0,98765** |
| Dense exact | 0,98191 | 0,98708 | 1,00000 | 0,97416 | 0,48148 | 0,85185 |
| Hybrid ANN | 0,98191 | 1,00000 | 1,00000 | 0,97634 | 0,67901 | 0,95062 |
| Router length≤4 | 0,98191 | 1,00000 | 1,00000 | 0,97634 | 0,69136 | 0,97531 |

Test nhỏ và synthetic; lexical main 1,0 không đại diện production. Trên architecture validation không blind, router đạt main Hit@5 0,97316, Hit@50 0,99489, MRR@10 0,95092.

## 5. Ambiguity và typing sessions

Với query rộng, intended ID chỉ là intent khi sinh query. Target Hit là diagnostic; gate phù hợp hơn là coverage trên **tập compatible đã biết**, không coi qrels là toàn bộ đáp án đúng. Dev compatible coverage@50: lexical 0,99125; exact dense 0,96718; hybrid ANN 0,99344.

222 dev sessions, 4.550 events:

| Method | Ever found@5 | Stable found@5 | Final hit@5 | Retained after first | Stable step | Top-5 churn |
|---|---:|---:|---:|---:|---:|---:|
| Dense exact | 0,95946 | 0,93694 | 0,93694 | 0,73239 | 13,22 | 0,55825 |
| Lexical | 0,97297 | 0,97297 | 0,97297 | **0,87963** | **9,34** | **0,44577** |
| Hybrid ANN | **0,98198** | **0,97748** | **0,97748** | 0,75229 | 11,51 | 0,52554 |
| Router length≤4 | **0,98198** | **0,97748** | **0,97748** | 0,71560 | 11,42 | 0,52083 |

Lexical phản hồi sớm/ổn định hơn; hybrid tăng final/stable hit. Progressive lexical-first có thể thử sau nhưng phải eval churn và stale-response trước khi bật.

## 6. ANN và tốc độ

ANN/exact dùng cùng embedding, similarity và corpus filter.

- Top-50 overlap: dev 0,99855; test 0,99921; architecture validation 0,99855.
- Dev main ANN − exact tại Hit@5/20/50: 0/0/0.
- Dev hybrid ANN − hybrid exact tại Hit@5/20/50/MRR@10: 0/0/0/0.

OpenSearch Docker local, 1.000 request/method/top-50:

| Branch | Concurrency | Throughput | p50 | p95 |
|---|---:|---:|---:|---:|
| Lexical | 1 | 175,7 QPS | 5,13 ms | 10,90 ms |
| Lexical | 8 | 879,4 QPS | 7,74 ms | 19,23 ms |
| ANN | 1 | 246,1 QPS | 3,67 ms | 5,68 ms |
| ANN | 8 | 934,9 QPS | 8,16 ms | 12,18 ms |

P100 batch-1 encoder p95 13,66 ms. Docker CPU API ở một lượt warm ổn định, 10 request tuần tự: `ga` lexical mean 37,0 ms; `vincom` hybrid 52,9 ms; `pho bo nam dinh` hybrid 58,6 ms. Sau khi cold-start lại toàn bộ Docker/graph cache, một lượt 25 request hybrid khác cho mean 153,9 ms và p95 353,4 ms dù startup đã warm bốn query. Vì vậy latency CPU local còn biến động theo cache/tài nguyên; đây là demo measurement, không phải SLA. Production cần load test trên phần cứng đích, warm index có kiểm soát và cân nhắc GPU/ONNX hoặc lexical-first.

Đo end-to-end qua API app (2026-09-15), warm-up rồi 20 query × 5 rounds, GPS cố định, `POST /v1/suggest/personalized`:

| Profile | Client p95 | Server total p95 | Encode p95 | Lexical p95 | ANN p95 | API RAM mean | OpenSearch RAM mean |
|---|---:|---:|---:|---:|---:|---:|---:|
| Hybrid `:8000` | 64,2 ms | 42,7 ms | 19,5 ms | 15,1 ms | 9,2 ms | ~531 MiB | ~1,36 GiB |
| Dense-only `:8001` | 56,6 ms | 38,2 ms | 17,8 ms | 0 | 9,5 ms | ~525 MiB | ~1,36 GiB |

Chi tiết và lần đo runtime/load mới nhất: [`apps/poi-search/bench/results/QUALITY_RUNTIME_LOAD.md`](../../apps/poi-search/bench/results/QUALITY_RUNTIME_LOAD.md). Dense-only nhanh hơn chủ yếu vì bỏ lexical; encode+RAM gần như nhau — đổi model nhỏ hơn mới cắt rõ RSS/encode, không phải chuyển hybrid→dense.

## 7. Demo thật và Stage 2 heuristic

FE và API hiện nằm chung tại `apps/poi-search`; cấu hình thật dùng `VITE_USE_MOCK=0`. Docker port 8000 có session/status, suggest, exposure/display/select, GPS/map/POI origin, geo heuristic và straight-line preview.

Stage 2 không đọc data user và không train. Tại snapshot báo cáo, heuristic v4 áp dụng evidence gate, category intent và coverage của token phân biệt trước khi blend relevance với khoảng cách. Khoảng cách không còn sort tuyệt đối; exact name/alias được bảo vệ và kết quả dedup theo entity group. Không cố lấp đủ 5 kết quả bằng candidate yếu. Mọi rule/weight nằm trong policy JSON có version. Heuristic chỉ rerank candidate Stage 1, không bổ sung POI ngoài candidate set. Đây là mô tả lịch sử; runtime v5 hiện không còn category/evidence hard-gate. State demo chỉ ở memory; production cần PostgreSQL/auth/TTL/transaction và routing engine thật.

Live diagnostic sau UX review cho thấy hybrid relevance gate trả duy nhất `Bệnh viện Bạch Mai` cho `bệnh viện bạch mai`, duy nhất `Bệnh viện Hữu nghị Việt Đức` cho `bv việt đức`, và đưa `Trường Trung học cơ sở Đa Tốn` cách 985 m lên đầu cho prefix `trung học đa`. Bản dense-only không dùng lexical/rewrite/token/category filter: nó trả cả `Bến đò Văn Đức` cho `bv việt đức` và bỏ lỡ Đa Tốn trong dense top-10. Vì vậy dense-only được giữ làm diagnostic profile, chưa phải lựa chọn mặc định. FE đồng thời bỏ `fitBounds` khi results đổi: gõ query chỉ cập nhật markers, camera chỉ di chuyển khi chọn POI, bấm recenter hoặc GPS được gắn lần đầu.

## 8. Giới hạn

- Query/qrels là synthetic weak labels; vẫn cần 100 mẫu human review theo kế hoạch.
- Test synthetic nhỏ; architecture holdout không còn blind. Muốn claim final generalization phải tạo holdout mới sau khi đóng băng policy.
- Structured dev chỉ có 19 main candidates.
- Checkpoint được train trên bundle trước stable-v1. Nó thắng zero-shot rõ trên corpus stable; retrain stable phải là thí nghiệm mới, so exact trên dev trước khi thay.
- Build, HTTP, CORS và contract flow đã pass; visual behavior đã được rà qua các phiên sửa UI sau đó.

## 9. Artifact

- Dataset frozen: `HANOI_QUERIES_20K/hanoi_queries_20k_stable_v1/`.
- Encoder fine-tuned: `artifacts/models/e5-v4-finetuned/`.
- Vector/id-map để rebuild index: `artifacts/indexes/hanoi-poi-stable-v1-release1/`.
- Dev, test frozen, architecture holdout, typing, router, zero-shot comparison và OpenSearch load: `artifacts/evaluations/stage1-stable-v1/`.
- API quality/latency/RAM/load mới nhất: `apps/poi-search/bench/results/`.
