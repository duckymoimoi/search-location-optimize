# Đặc tả training và nâng cấp retrieval — revision 2026-09-15

Tài liệu này chốt protocol thí nghiệm cho thiết kế hệ thống và đặc tả kỹ thuật hiện hành. Các quota, dimensions và gates dưới đây là lựa chọn của dự án, chưa phải kết quả thực nghiệm. Không thay đổi API hoặc tự kích hoạt model mới.

## 1. Quyết định kiến trúc

Giữ OpenSearch lexical + E5 fine-tuned single-vector + RRF làm baseline triển khai. Chưa đủ bằng chứng kết luận đây là model tối ưu; cũng chưa có bằng chứng cần thay bằng multi-vector. Tách ba lỗi: target vắng khỏi corpus/candidates; target có nhưng text relevance xếp sai; text còn mơ hồ cần context. Dùng đúng thí nghiệm cho từng lỗi.

Ưu tiên: (1) negatives/nhãn và replay benchmark đúng, (2) MRL khi vector/index là nút thắt, (3) late-interaction text reranker khi CandidateHit tốt nhưng thứ hạng text còn sai. Nếu encoder CPU là nút thắt, thử runtime/quantization hoặc student Việt–Anh; giảm chiều output không tự giảm số layers hay vocabulary của encoder.

AI không đồng nghĩa classifier học thuộc mọi POI, và online serving không đồng nghĩa online weight updates. Model frozen có thể encode POI mới; chỉ train lại khi cần thích nghi domain/quality. Khi thay weights, re-encode corpus cho embedding space mới.

## 2. Cơ sở nghiên cứu và mức áp dụng

| Nguồn | Điều được hỗ trợ bởi bài | Giới hạn áp dụng |
|---|---|---|
| [ColBERT, SIGIR 2020](https://arxiv.org/html/2004.12832v2) | Encode query/document riêng thành vectors theo token; MaxSim cộng mức khớp tốt nhất cho từng query token. Có thể rerank hoặc retrieve. | Passage retrieval không chứng minh hiệu quả trên prefix Việt, số nhà hoặc geo. Không chuyển số speedup so với BERT pairwise sang E5 hiện tại. |
| [ColBERTv2, NAACL 2022](https://arxiv.org/html/2112.01488v3) | Kết hợp supervision được khử nhiễu, teacher cross-encoder, hard negatives và residual compression. Bài báo báo giảm footprint 6–10 lần so với late-interaction trước đó. | Không phải giảm 6–10 lần so với single-vector E5. Không mặc định checkpoint/teacher trong bài phù hợp Việt–Anh. |
| [Negative Sampling Survey, 2026](https://arxiv.org/html/2603.18005v1) | Phân loại random/in-batch, static/dynamic hard mining và false-negative mitigation; trang arXiv ghi accepted Findings EACL 2026. | Dùng taxonomy, không lấy bảng uplift làm so sánh có kiểm soát: phần Limitations thừa nhận thiếu benchmark thống nhất. Văn bản còn lặp RQ1/RQ2; không vì một lỗi biên tập mà bác bỏ toàn bộ, nhưng cần đối chiếu nguồn gốc cho tuyên bố định lượng. |
| [Matryoshka Representation Learning](https://arxiv.org/html/2205.13147v4) | Huấn luyện các prefix chiều của cùng vector bằng loss ở nhiều kích thước, phục vụ trade-off chất lượng/chi phí downstream. | Không được cắt tùy ý checkpoint E5 thường rồi gọi là MRL. Không suy giảm encoder latency/weights tương ứng với giảm số chiều. |

Bốn bài bổ sung retrieval/training; không bài nào trong nhóm này chứng minh geo/history rerank v6 đúng. Quyết định dưới đây là adaptation cho POI, phải qua benchmark riêng.

## 3. Negative sampling contract — thực hiện trước

### Nhãn theo đúng thông tin đầu vào

- `tiểu học đại`: Đại Mỗ/Đại Hưng/Đại Từ có thể cùng hợp lệ về chữ. Không gán Đại Mỗ là negative chỉ vì scenario chọn Đại Hưng gần origin; Stage 1 không thấy origin.
- `tiểu học đại mỗ`: Đại Hưng có thể là hard negative sau kiểm tra tên/alias thực. Tên xa rõ ràng vẫn positive.
- `Highlands`: nhiều branches hợp lệ; `Highlands + địa chỉ/branch rõ`: branch khác mới có thể là negative.
- `B12`, `16/2`: namespace và địa chỉ quyết định mức đủ định danh. Một ký tự khác không mặc định là negative nếu đó là alias hợp lệ/nhãn chưa rõ.

Positive/negative/ignore là quan hệ query–POI, không phải nhãn cố định của POI. `intended_poi_id` là nguồn sinh, chưa tự tạo negative set. `origin_search_eligible` không tham gia Stage 1 sampling.

### Pipeline tái lập

1. Freeze corpus, query families, qrels/eligibility, split manifest và encoder seed. Strict cold-POI holdout loại toàn bộ POI held-out khỏi positive, negative, distillation và model adaptation; vẫn index để eval bằng model frozen. Với known-catalog track cho phép exposure khác, khai báo riêng.
2. Mine chỉ train queries: lexical top-100 và exact dense top-100 từ checkpoint đã pin. Cache raw pools, source rank/score và hashes; không mine dev/test để tạo training tuples.
3. Loại positives đã biết, cùng entity đã xác nhận, alias-compatible và unjudged mơ hồ. Cùng complex/brand chưa đủ để merge, cũng chưa đủ để negative. Mẫu chưa xác định chuyển ignore, không cưỡng ép đủ quota.
4. Baseline mỗi query rõ tối đa 8 negatives: 2 random, 3 lexical-hard, 3 dense-hard sau dedup. Quota là cấu hình khởi đầu. Thiếu nguồn thì giảm actual count; log fill rate. Random cũng phải qua eligibility/compatibility checks.
5. Tập challenge có nguồn riêng cho wrong number/slash/branch/street; dùng POI thật, không tự tạo destination giả. Sampling theo family, không để chuỗi prefix dài nhân trọng số một ý định.
6. Train một vòng; chỉ một lần refresh mining bằng checkpoint train nếu dev cho thấy còn lợi ích. So static/mixed/refreshed với cùng query budget và training compute công bố; không luôn lấy negatives khó nhất.
7. In-batch candidates qua cùng positive/ignore mask. Kiểm tra collision trong batch và distributed gather nếu dùng; gradient accumulation không tự mở rộng pool trong một forward.

### Artifact tối thiểu

`training_pairs.parquet`: `query_id`, `poi_id`, `label` (positive/negative/ignore), `negative_source` nullable, `source_rank` nullable, `label_reason`, `sample_weight`. `label_reason` ghi nguồn nhãn/evidence; teacher score không biến unjudged thành gold.

`mining_manifest.json`: corpus/query/qrels/split hashes, miner checkpoint, lexical config, pool depths, seed, quota, mining iteration, timestamp, duplicate/compatible exclusions, pool fill stats và data version. Teacher scores/provenance nếu có nằm trong sidecar theo query–POI + teacher version; không thêm hàng loạt trường vào bảng query hay 18 cột POI chính.

### Loss và teacher

Dùng masked multi-positive contrastive loss: với P là positives, N là negatives đã chấp nhận, bỏ ignore khỏi denominator:

`L(q) = -log(sum_{p in P} exp(s(q,p)/T) / sum_{d in P union N} exp(s(q,d)/T))`.

Mask không được làm mất mọi positive; query không có positive hoặc không có negative hữu ích bỏ khỏi batch và đếm lý do. Objective tập positives này chỉ khuyến khích tổng mass, không bảo đảm recall mọi branch; theo dõi known-compatible recall riêng, có thể thử average-positive objective trong thí nghiệm tách biệt.

Teacher chỉ là tùy chọn offline. Chọn model có bằng chứng Việt–Anh, kiểm tra trên audit slice trước khi dùng; không mặc định MiniLM tiếng Anh của bài phù hợp. Nếu teacher mâu thuẫn nhãn hoặc không chắc, giữ ignore/review. Distill phân phối trên cùng candidate list, cùng masks, lưu temperature và trọng số KL; không dùng raw RRF làm probability hoặc ép student học khoảng cách từ teacher có origin khi student chỉ thấy query. So có/không teacher trên cùng negatives để tách đóng góp.

## 4. Matryoshka experiment — single-vector

Giữ một checkpoint baseline 384d thường. Train một checkpoint khác với nested dimensions `{96,192,384}` và trung bình masked contrastive losses tại ba chiều; mỗi prefix vector phải L2-normalize riêng trước cosine. Đây là adapter MRL của dự án, không phải kết quả từ bài gốc trên POI.

Đối chứng: E5 thường 384d, E5 thường truncate 192/96d (control), MRL 384/192/96d. Dùng cùng pairs, mining pools, epochs/optimizer budget; ghi overhead training. Kiểm tra exact retrieval trước; sau chọn dimension mới xây ANN tương ứng. Nếu full dimension bị hại, không chỉ báo bản nhỏ thắng kích thước.

Manifest phải có `representation_type=single_vector`, full_dim, serving_dim, nested_dims, normalization, dtype, checkpoint/tokenizer/passage hashes và embedding_space_id. Checkpoint MRL mới cần re-encode; đổi dimension trong cùng checkpoint có thể slice cached full vectors rồi normalize/reindex, không cần forward corpus lại. Không trộn vectors từ checkpoint cũ.

Với 45.692 POI, FP32 thô 384d ≈70,18 MB; 192d ≈35,09 MB; 96d ≈17,55 MB, đơn vị thập phân. Đây chỉ là N×d×4, chưa gồm graph/text/metadata/replica hoặc weights encoder. Toàn quốc lợi ích có thể lớn hơn, phải đo count thực. Báo RAM API, OpenSearch và vector files riêng.

Thử coarse-to-fine 96d retrieve 100 → rescore 384d → final 50 chỉ như nhánh phụ, cùng total-budget accounting. Báo miss do low-dim pruning riêng; không gọi pipeline này là Stage 2 cá nhân hóa. Khi còn lưu full vectors, không quảng bá giảm toàn bộ storage bằng tỷ lệ 96/384.

## 5. Late interaction — nhánh nghiên cứu có điều kiện

Chỉ mở nếu CandidateHit@50 tốt nhưng text Hit@1/MRR yếu và error audit cho thấy mất chi tiết tên/địa chỉ. Thử `text_reranker=none|late_interaction` trên cùng 50 candidates trước context; đây là Stage 1b hiểu chữ. Không thêm origin/history/time vào model này ở phép so text.

POI token vectors được encode offline vào sidecar; query dùng encoder late-interaction riêng online. Không coi hidden states của E5 trained bằng mean pooling tự động là ColBERT. Cần token-level training/projection/pooling/masking và checkpoint có bằng chứng Việt–Anh. Ban đầu full-precision cached token vectors để xác nhận chất lượng; residual compression là thí nghiệm sau, không mặc định OpenSearch single-vector index thực thi MaxSim.

Candidate set không đổi nên reranker không tăng CandidateHit@50; nó chỉ đổi thứ hạng bên trong. End-to-end multi-vector retrieval là nhánh khác, chỉ xét sau nếu lỗi recall và chi phí vận hành biện minh được. Với late interaction cần thêm query encoder, token-vector lookup và MaxSim; đo hết vào latency. Không gọi đó là “miễn phí vì POI đã encode offline”.

Sidecar manifest: corpus/POI IDs, model/passage hashes, token offsets/lengths, vector_dim, dtype, token masks, compression codebook/version nếu có. Index/storage mới là optional dependency; serving mặc định không cần tải chúng.

So identity RRF, text reranker, context reranker và text+context riêng. Khi text adapter timeout trả original Stage 1 order, flag degraded và tính cả chất lượng fallback. Traces internal có original rank, text rank, context rank, matched evidence; không thêm raw scores vào public UI.

## 6. Geo-v6 dự kiến và hướng learned Stage 2

Geo-v6 là **ứng viên chưa triển khai**, không phải ranker của demo hiện tại. Đề xuất này chỉ hoán đổi các slots cùng lớp khớp name/alias với đầu bảng trong window 10, RRF ratio≥0.5 và distance bands 500m. Đây là rule, không phải relevance calibration. Có thể bỏ lỡ synonyms/typos, lệ thuộc top-1 và ranh band; cùng phrase chưa chứng minh cùng ý định. Unit tests logic không chứng minh uplift thực.

Khi triển khai, so geo-v6 với Stage 1 order và `heuristic-geo-v5` hiện hành trên cùng candidates. Bước learned tiếp theo là LambdaMART dùng text evidence, ranks/masks, geo/accuracy/missingness; bổ sung time/history khi có nhãn đúng cutoff. So trên same candidates và same information. Không dùng nearest làm gold hoặc target-distance stratum làm input.

Đánh giá counterfactual đổi origin gồm query mơ hồ, explicit xa, null/poor GPS, nearby wrong category, branch và address. Query có location rõ phải giữ remote target. Chưa có bằng chứng learned thắng thì giữ v6; ColBERT/MRL không thay thế kiểm chứng này.

## 7. Ma trận và gate quyết định

| Nhánh | Giữ cố định | Điều cần chứng minh |
|---|---|---|
| E0 baseline | Corpus/checkpoint/query sets; lexical/exact dense/hybrid | Mốc chất lượng có thể replay |
| E1 negative sampling | Model/passage/fusion; matched training budget | Data cải thiện noisy retrieval, không tạo false negatives |
| E2 MRL | E1 pairs/pools, tuning budget | Pareto chất lượng so dimension/index cost |
| E3 late interaction | Candidate IDs=E1 top-50, không context | Text ranking gain đủ trả additional latency/storage |
| E4 context | Fixed candidates/text profile, origin/user/time snapshots | Context rescue đúng, không phá explicit |
| E5 serving | Frozen winner của từng nhánh | ANN loss và API performance trên workload thật |

Không chạy Cartesian grid E1×E2×E3×E4. Chọn sequential trên dev, preregister config và selection rule trước holdout; test v3 đã xem là frozen regression, không blind. Architecture holdout tách cả POI/query families và không dùng để sửa miner/teacher.

Metrics: core CandidateHit@20/50, Hit@1/5, MRR@10; autocomplete Hit/MRR@5 theo prefix và minimum typed chars; ambiguity any-compatible hit/known-compatible recall; code có/thiếu namespace tách riêng; IME chưa verified chỉ diagnostic. Báo rescue/harm và n/mẫu số; không gộp mọi track thành một score.

Paired cluster bootstrap theo family (context theo independent scenario/user cluster), cùng queries; dùng 95% CI. Gate đề xuất khóa trên dev trước test: nâng text model khi lower CI của ΔMRR@10>0 và ΔHit@1 explicit lower CI≥−0.01; Δwrong-branch upper CI≤+0.005. Với tối ưu dimension, yêu cầu lower CI của ΔCandidateHit@50≥−0.005 và ΔMRR@10≥−0.01, cùng explicit gate; các margins tính trên thang 0–1 và là đề xuất sản phẩm, không chuẩn từ bài báo. Chưa đủ mẫu/CI rộng: inconclusive, giữ baseline.

Geo dùng ΔHit@1 trên origin-sensitive scenarios; explicit/invariant/remote có non-inferiority riêng, không dùng raw nearest rate làm accuracy. Báo conditional ranking và end-to-end gồm candidate misses. Thay text order phải kiểm tra lại v6 vì cohort dựa head candidate.

ANN overlap so exact cùng representation/dimension/scope/tie policy; tách quantization loss, MRL dimension loss và ANN approximation loss. Serving đo p50/p95/p99, offered/achieved QPS, errors/degraded, queue/encode/retrieval/text/context timings, API RAM và search RAM; không cộng p95 thành p95 tổng. Budget theo system spec chỉ là mục tiêu, phải khóa hardware/load/cache profile trước khi đo. Không suy chất lượng hoặc chi phí Hà Nội từ benchmark passage của bài.
