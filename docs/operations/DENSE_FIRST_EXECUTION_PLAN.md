# Quy trình đánh giá và chuyển sang dense-first

Ngày lập: 2026-09-28. Trạng thái: **đã thực hiện P0–P5 ở mức nghiên cứu; P7–P8 chưa qua gate**. Xem [báo cáo thực thi và quyết định](DENSE_FIRST_EXECUTION_STATUS_2026_09_28.md) để phân biệt cấu hình đã đo với cấu hình đang phục vụ demo.

Ràng buộc thực thi của người dùng: tác vụ train nặng chạy trên **Kaggle**. GPU local chỉ dùng inference/benchmark sau khi checkpoint đã tải về; không chạy optimizer/training trên local. Trạng thái từng bước được cập nhật trong execution report, không suy từ kế hoạch thành hoàn thành.

Cơ sở: [Review kiến trúc retrieval, train và benchmark](RETRIEVAL_ARCHITECTURE_REVIEW_2026_09_28.md). Tài liệu này chuyển các phát hiện thành thứ tự công việc, đầu ra và điều kiện nghiệm thu. Các profile, schema và artifact mới bên dưới là đề xuất cần xây dựng, không phải tính năng đã có.

## 1. Mục tiêu và phạm vi

Trả lời bốn câu hỏi bằng các phép đo có thể tái lập:

1. Dense-first có cải thiện chất lượng và tốc độ đầu cuối so với hybrid hiện tại không?
2. Lexical cần giữ ở đâu: retrieval rộng, lookup có điều kiện, prefix hay fallback vận hành?
3. Ở quy mô corpus hiện tại, nên dùng dense ANN hay exact GPU?
4. Sau khi loại ảnh hưởng của serving, model còn thiếu gì và có cần train tiếp không?

Thành công không được định nghĩa là phải bỏ lexical. Kết quả hợp lệ có thể là giữ một phần lexical nếu có lợi ích đo được. Giữ Elasticsearch trong vòng đầu vì API còn dùng document lookup, map catalog và geo search.

Không sửa Gold đã khóa để cải thiện điểm. Không ghi đè evidence cũ. Không gộp việc đổi model, normalizer, retrieval, ranking và candidate budget vào một phép so sánh rồi quy kết cho riêng lexical.

## 2. Thứ tự và điểm dừng

| Bước | Công việc | Phụ thuộc | Đầu ra bắt buộc | Điều kiện qua bước |
|---|---|---|---|---|
| P0 | Khóa baseline và protocol | Không | Manifest, inventory, bảng ngưỡng | Tái hiện được đúng cấu hình baseline |
| P1 | Chuẩn hóa trace và evaluator | P0 | Per-query trace, summary, kiểm tra tính đúng | Tính lại summary từ trace khớp |
| P2 | Tách normalizer/retrieval/ranking để ablate | P1 | Profile độc lập, kiểm thử hành vi | Dense thuần giữ nguyên dense order |
| P3 | Đo chất lượng và đóng góp lexical | P2 | Ma trận ablation, rescue/harm report | Định vị được nguyên nhân regression |
| P4 | Thử lookup và backend phù hợp | P3 | Candidate dense-first được khóa trên dev | Đạt quality gate trên dev |
| P5 | Đo tải và latency đầu cuối | P4 | Load report, tài nguyên, error rate | Nếu chưa có SLA, chỉ đặc trưng hóa đường cong tải và lỗi; chưa kết luận production |
| P6 | Train bổ sung nếu cần | P3; chỉ khi có gap | Weight/mask audit, checkpoint dev-lock | Đạt POI và brand dev gates |
| P7 | Khóa ứng viên, đánh giá holdout | P5; P6 nếu có train | Holdout report, quyết định release | Đạt toàn bộ gate |
| P8 | Triển khai, theo dõi, rollback | P7 | Release manifest, smoke, rollback record | Release tái lập được và ổn định |

Nếu P6 tạo checkpoint mới, phải re-encode corpus và quay lại P3–P5 cho checkpoint đó trước P7. Không dùng latency hoặc kết quả retrieval của checkpoint cũ để nghiệm thu model mới.

## 3. P0 — Khóa baseline và thiết kế phép đo

### Thực hiện

1. Ghi lại Git HEAD, working-tree diff và hash các file đang dùng. Chỉ ghi commit là chưa đủ vì checkout có thay đổi chưa commit.
2. Lập inventory model, corpus, embeddings, ID map, index, policy và API. Dùng checkpoint **6k dev-lock** làm baseline để điều tra serving; giữ zero-shot và Brand+POI làm đối chứng model riêng.
3. Xác nhận query encoder và passage embeddings thuộc cùng checkpoint. Kiểm tra số hàng, ID order, dimension, dtype, normalization và searchable set.
4. Chia dữ liệu thành dev để lựa chọn, Gold hiện tại để regression, holdout mới để quyết định cuối. Khóa nhóm case/POI hoặc brand family trước khi sinh biến thể; kiểm tra trùng text và entity theo protocol.
5. Khóa scope đo: query-only trước, có origin sau; response top 10 cho sản phẩm, retrieval depth 100 cho chẩn đoán. Budget 50 hiện tại được ghi thành cấu hình riêng.
6. Chốt quality tolerance, traffic mix, target QPS và SLA trước khi xem kết quả candidate. Nếu chưa có nhu cầu tải rõ ràng, chỉ công bố đường cong latency/throughput, chưa đánh dấu đạt production SLA.

### Manifest tối thiểu

| Nhóm | Trường phải ghi |
|---|---|
| Code | revision, dirty diff hash, runner hash |
| Model | checkpoint hash, tokenizer hash, encoder input normalizer version |
| Corpus | corpus version/hash, passage builder, searchable ID-set hash |
| Vectors | checkpoint source, ID-map hash, vector hash, shape, dtype, normalization |
| Search | index/mapping hash, lexical policy hash, backend, k, num_candidates, candidate budget |
| Ranking | từng flag dedup/name-address/name-quality/geo, fusion policy |
| Eval | dataset/split/qrels hash, metric definition, seed, top-k |
| Máy | CPU/GPU/VRAM/RAM, software versions, API workers, background workload |

Lưu mỗi run vào thư mục riêng `artifacts/results/dense_first/<run_id>/`; đây là đường dẫn đề xuất. Evidence nguồn không chuyển hoặc ghi đè.

### Gate G0

- [ ] Model–vector–ID map nhất quán; encoder không âm thầm fallback sang model khác.
- [ ] Baseline có đầy đủ manifest và cấu hình đóng băng.
- [ ] Dataset roles và ngưỡng nghiệm thu đã ghi rõ; ngưỡng chưa chốt được đánh dấu pending.

## 4. P1 — Xây trace và evaluator chung

### File liên quan

- [stage1_three_way_top100.py](../../apps/poi-search/bench/stage1_three_way_top100.py): hiện chỉ lưu summary, cần bổ sung output per-query.
- [es_query.py](../../apps/poi-search/api/es_query.py): giữ `_score` và thứ hạng nhánh thay vì chỉ IDs.
- [pipeline.py](../../apps/poi-search/api/pipeline.py): mở rộng trace các stage và timing.
- [ranking.py](../../apps/poi-search/api/ranking.py): ghi đầu vào/đầu ra và lý do thay đổi thứ hạng.

### Thực hiện

1. Trả candidate gồm `poi_id`, `source`, `branch_rank`, `raw_score`, `score_kind`. Phân biệt ES score với cosine; không cộng trực tiếp hai thang điểm chưa hiệu chuẩn.
2. Lưu `query_id`, `case_id` hoặc `family_id`, role, stratum, raw query, encoder input, accepted IDs, origin và route.
3. Lưu ordered candidates ở các mốc: dense, lexical, union, fusion, dedup, cap, name-address, name-quality, geo và final. Tên stage phải phản ánh thứ tự thực thi thực tế.
4. Lưu timing: queue, tokenization/encode, retrieval từng nhánh, fusion, hydration, dedup, ranking, total server và total client. Không lấy tổng latency các nhánh song song làm latency endpoint.
5. Evaluator đọc trace để sinh summary và bảng rescue/harm. Tách retrieval any-hit khỏi recall nhiều positives và recall ANN so với exact.
6. Ghi failed/timed-out requests vào mẫu số hoặc report riêng theo protocol đã khóa; không âm thầm loại khỏi điểm.

### Artifact cần có

`manifest.json`, `queries.jsonl`, `summary.json`, `slice_metrics.json`, `regressions.jsonl`, `latency.json`. Trace lớn có thể nén; giữ schema version và khả năng replay.

### Gate G1

- [ ] Summary tái tính từ trace khớp; đủ số query và không trùng ID.
- [ ] Có test nhỏ cho nhiều positives, không có hit, tie, timeout và dedup.
- [ ] Có thể chỉ ra query được cứu/bị hại và stage gây thay đổi.
- [ ] Diagnostic trace được bật riêng, không phình response sản phẩm mặc định.

## 5. P2 — Tách các biến cần kiểm tra

### 5.1. Normalizer

Giữ raw query; tách `encoder_input` khỏi lexical keys. Trên cùng checkpoint và cùng vector corpus, so raw-compatible input với `glue_code_spans` hiện tại. Kiểm tra riêng số nhà dạng `274-276`, `14-16`, slash `259/15`, mã `S3.01`, dấu tiếng Việt và query dính chữ.

Đo trên dev trước khi chọn. Sau đó dùng cùng hàm/version khi train, offline eval và serving. Nếu thay passage normalization, phải re-encode corpus; nếu chỉ thay query input, ghi rõ corpus embeddings giữ nguyên để phép ablation có nghĩa.

### 5.2. Retrieval và ranking

Tách hai lựa chọn độc lập: **nguồn candidates** và **cách xếp hạng**. Không coi `POI_RETRIEVAL_PROFILE=dense_only` hiện tại là dense thuần vì pipeline vẫn chạy heuristic.

Các chế độ cần triển khai cho thí nghiệm:

| Chế độ đề xuất | Hành vi |
|---|---|
| Dense raw | Giữ đúng thứ hạng và score dense; chỉ filter searchable set giống baseline |
| Dense + dedup | Chỉ thêm dedup và cap đã khai báo |
| Dense + từng heuristic | Bật name-address hoặc name-quality riêng |
| Hybrid raw | Lexical+dense theo fusion khai báo, chưa heuristic |
| Hybrid current | Replay nguyên pipeline hiện tại |
| Dense + gated lookup | Chỉ bổ sung lookup khi rule/gate đủ bằng chứng |

Không thêm các tên này vào tài liệu chạy lệnh như thể đã được API hỗ trợ. Khi triển khai, cập nhật settings, schema/config validation và test tương ứng.

### Gate G2

- [ ] Dense raw qua pipeline giữ nguyên ID order trên cùng input/cache.
- [ ] Từng flag có thể bật độc lập; profile thực tế được ghi trong trace.
- [ ] Branch depth, union size, cap và số results trả ra là các biến riêng.
- [ ] Test phát hiện mất candidate do cap/dedup, thay vì quy thành dense miss.

## 6. P3 — Chạy ma trận chất lượng

### 6.1. Vòng A: cùng checkpoint, normalizer và budget

| Run | Retrieval | Post-processing | Câu hỏi |
|---|---|---|---|
| A0 | Lexical | Không | Lexical standalone mạnh ở slice nào? |
| A1 | Exact dense | Không | Trần chất lượng dense với checkpoint này? |
| A2 | ANN dense | Không | ANN mất gì so với exact? |
| A3 | ANN + lexical | RRF hiện tại, chưa heuristic | Fusion cứu/hại bao nhiêu? |
| A4 | ANN dense | Dedup/cap | Dedup/cap làm mất gì? |
| A5 | ANN dense | Dedup/cap + name-address | Heuristic này giúp hay hại? |
| A6 | ANN dense | Dedup/cap + name-quality | Heuristic này giúp hay hại? |
| A7 | ANN dense | Dedup/cap + cả hai heuristic | Tương tác hai heuristic? |
| A8 | Hybrid hiện tại | Full query-only pipeline | Baseline sản phẩm trong cùng run? |

Cache cùng query vectors và branch results cho ablation ranking; không chạy lại retrieval ngẫu nhiên giữa các cấu hình rồi quy chênh lệch cho ranker. Chạy budget sweep 50/100 thành vòng riêng. Exact+lexical là phép bổ sung để nối evidence cũ, không thay cho ANN+lexical vốn đang phục vụ.

### 6.2. Dữ liệu và metrics

| Suite | Đơn vị tổng hợp | Metrics chính |
|---|---|---|
| POI/entity | Query; CI bootstrap theo case | Hit@1/5/10/20/100, MRR@10, rescue/harm |
| Brand | Family mean | AnyCompatibleHit, group MRR, coverage, namespace false-branch |
| Prefix | Session có readiness | FHC, SHC, PrefixAUC; luôn ghi mẫu số và readiness |
| House/code | Intent và exact constraints | Đúng số/mã, sai số/mã, đúng scope fallback nếu có |
| Origin/geo | Query–origin scenario | Đúng entity/brand/area, thứ tự chi nhánh phù hợp |

Gold POI/brand hiện tại là regression suite. Prefix cần bổ sung case đủ intent trước ký tự cuối. House/code và origin suite mới phải có dev/holdout, annotation độc lập với output candidate, không đổi nhãn theo model thắng.

Với nhiều positives: Hit@K là có ít nhất một positive; Recall@K là tỷ lệ positives lấy được. ANN recall@K được tính bằng overlap với exact top-K dưới cùng filter/score/tie policy, không chỉ bằng chênh Gold Hit@K.

### 6.3. Audit lỗi

Với mỗi query thay đổi, phân loại: corpus/qrel issue; normalization; candidate miss; ANN miss; fusion demotion; cap/dedup loss; heuristic demotion; wrong brand/namespace; wrong numeric constraint; geo misranking. Báo số lượng theo nhóm, ví dụ đại diện và counterexample. Giữ nguyên Gold; nếu phát hiện nhãn sai, ghi issue cho phiên bản dataset sau.

### Gate G3

- [ ] So sánh paired cùng query; CI bootstrap theo case/family, không coi biến thể là độc lập.
- [ ] Có net rescue/harm và các slice regression, không chỉ điểm trung bình.
- [ ] Tách kết luận candidate recall khỏi chất lượng final top 10.
- [ ] Chỉ chọn policy/gate trên dev; Gold không trở thành tập tuning ngầm.

## 7. P4 — Quyết định vai trò lexical và backend

### Lookup có điều kiện

Thử từng chức năng độc lập: tên/alias exact; brand membership với namespace/area; house+street/code; prefix ngắn. Giữ provenance của candidate và lý do promote. Khi intent chưa chắc chắn, tránh hard filter có thể loại POI đúng; đo false routing như một lỗi riêng.

Nếu dùng score/margin để gọi lexical, fit threshold trên dev và kiểm tra độ ổn định theo slice. Nếu gọi fallback sau dense, đo thêm latency tuần tự; nếu chạy song song, đo chi phí/QPS. Không giả định selective retrieval luôn nhanh hơn.

| Bằng chứng sau xếp hạng | Quyết định |
|---|---|
| Lexical rộng không giúp hoặc gây hại | Bỏ khỏi đường mặc định của scope đã được kiểm định |
| Lookup chỉ giúp code/address/prefix | Chỉ bật ở route tương ứng |
| Lexical giúp ổn định nhiều slice | Giữ có trọng số/gate được dev chọn; so với dense-only |
| Chỉ hữu ích khi encoder lỗi | Giữ fallback vận hành với timeout và degraded reason |
| Suite còn thiếu hoặc CI quá rộng | Chưa kết luận cho scope đó; bổ sung evidence |

Thử exact GPU và ANN với cùng corpus/filter. Ngoài chất lượng, đo VRAM tổng, startup/load time, update corpus và throughput. Không quyết định backend chỉ dựa trên 1 request trong VRAM warm.

### Gate G4

- [ ] Mỗi nhánh được giữ có incremental gain hoặc lý do vận hành cụ thể.
- [ ] Candidate dense-first khóa trên dev, có profile rollback.
- [ ] Không suy từ POI-only sang toàn bộ brand/address/autocomplete.

## 8. P5 — Benchmark tốc độ đầu cuối

1. Khóa máy, GPU, workers, model, vector/index, policy, response top-k và traffic mix. Ghi các service cùng dùng GPU; dùng môi trường kiểm soát được để công bố SLA.
2. Warmup bằng query ngoài holdout, loại warmup khỏi số đo. Ghi số lần và điều kiện ổn định đã chọn trước.
3. Chạy tối thiểu 3 lượt đo mỗi cấu hình, đổi thứ tự cấu hình giữa các lượt để giảm bias cache/nhiệt. Ghi cache warm/cold riêng.
4. Sweep concurrency 1/4/8/16; đo thêm arrival rate theo target QPS để phát hiện queue tích tụ. Giữ cùng query mix, không chỉ lặp một query có cache.
5. Thu client p50/p95/p99, server breakdown, QPS hoàn thành, error/timeout rate, CPU/GPU/RAM/VRAM và queue time. Ghi số request và thời gian đo; ít mẫu không đủ tin p99.
6. Kiểm tra tải autocomplete: prefix liên tiếp, hủy request cũ và request thừa. Kiểm tra riêng encoder unavailable, lexical unavailable và metadata unavailable.
7. Với nhánh GPU mới, bảo đảm timing phản ánh hoàn tất GPU work; tránh chỉ đo enqueue CUDA. Report retrieval microbenchmark và endpoint benchmark riêng.

### Gate G5

- [ ] Đạt target QPS, latency và error budget ở cùng điều kiện đã khóa.
- [ ] Không giảm độ sâu retrieval hoặc thay response top-k chỉ cho candidate mà không công bố.
- [ ] Không cộng percentile từng stage để suy ra percentile tổng.
- [ ] Nếu chưa có SLA, kết quả mang trạng thái characterization, chưa production-ready.

## 9. P6 — Train tiếp khi serving đã được tách lỗi

### 9.1. Sửa protocol và audit dữ liệu

1. Tách `sampling_probability` và `loss_weight`; định nghĩa rõ giá trị 0, tránh `value or 1.0` biến 0 thành 1.
2. So ba chế độ có kiểm soát: sampling-only, loss-only và kết hợp có chủ đích. Giữ số optimizer steps/token budget so sánh được; ghi distribution thực tế mỗi slot.
3. Viết test mask cho: multi-positive, ignore, cùng brand khác branch, bare brand, namespace và entity trùng. POI query chỉ coi sibling là negative khi qrels/intent thực sự loại sibling đó.
4. Chọn explicit-only hay in-batch negatives thành biến thí nghiệm; ghi số negatives hợp lệ mỗi query. Không đổi mask âm thầm khi chuyển kernel.
5. Mine brand hard negatives trên train/dev đúng vai trò; loại mọi positive hợp lệ và ignore. Kiểm tra Gold/holdout IDs khỏi training pools theo protocol cold-POI; giữ chúng trong corpus đánh giá.
6. Resample brand positives theo epoch nếu mục tiêu là học coverage nhiều chi nhánh. Audit train queries, positives, negatives và ignore bằng manifest trước upload và ngay trong kernel.

### 9.2. Kiểm soát POI–brand mix

Ghi cả tỷ lệ row trong batch, tổng loss weight theo intent, số steps và số unique POI/query được thấy mỗi epoch. Tỷ lệ 12/4 không tự có nghĩa POI chiếm 75% ảnh hưởng loss. Đặt rehearsal budget rõ ràng, không gọi một lượt qua brand là một lượt qua toàn bộ POI train.

Train từng thay đổi, chọn checkpoint bằng dev POI và brand cùng quality floors đã khóa. Báo thêm coverage và namespace, không chỉ AnyCompatibleHit@1. Một model tăng brand nhưng phá entity không được tự động thay baseline.

### Gate G6

- [ ] Leakage/mask/weight checks pass và có artifact kiểm chứng.
- [ ] Checkpoint selection không đọc holdout; budget thí nghiệm khai báo trước.
- [ ] Checkpoint thắng dev được re-encode, kiểm tra ID-map rồi đánh giá lại P3–P5.
- [ ] Nếu không có checkpoint vượt gate, giữ checkpoint cũ và ghi kết quả âm.

## 10. P7 — Khóa và quyết định cuối

Trước khi mở holdout, hoàn thành bảng sau trong manifest. Đây là template cần điền; không phải các ngưỡng đã được chấp thuận.

| Gate | Phải khóa trước |
|---|---|
| POI | Quality floor và mức giảm cho phép so baseline, đặc biệt top 10 |
| Brand | Family Hit/MRR, coverage floor, namespace error ceiling |
| Numeric/prefix/geo | Slice bắt buộc, mẫu số tối thiểu, regression tolerance |
| Hiệu năng | Máy, traffic mix, target QPS, p95/p99, timeout/error budget |
| Quyết định lexical | Gain tối thiểu hoặc điều kiện bỏ nhánh, chi phí chấp nhận |
| Thống kê | Bootstrap unit/seed, số lần resample, cách xử lý CI chưa đủ kết luận |

Khóa candidate, evaluator và ngưỡng; chạy holdout một lần cho quyết định đã đăng ký. Nếu fail, ghi fail và quay về dev. Nếu tiếp tục thiết kế dựa trên lỗi holdout, bộ đó trở thành regression set và cần holdout mới cho tuyên bố độc lập tiếp theo.

Quyết định phải ghi rõ phạm vi: bỏ lexical generic cho entity khác với bỏ mọi lexical cho toàn sản phẩm. Không tuyên bố vượt baseline nếu dữ liệu hoặc uncertainty không đủ.

## 11. P8 — Triển khai và rollback

1. Tạo release bundle liên kết checkpoint, tokenizer, normalizer, embeddings, ID map, index và policy bằng hash. Version API phải phản ánh đúng release; không dùng nhãn zero-shot cho vector fine-tuned.
2. Triển khai candidate ở môi trường thử nghiệm; smoke query-only, origin, brand, số/mã, prefix, map catalog và lỗi nhánh.
3. Đối chiếu trace offline với endpoint trên tập smoke cố định. Kiểm tra startup phát hiện model/vector mismatch thay vì fallback âm thầm.
4. Chuyển traffic khi gates đã đạt và có quyết định release. Theo dõi latency, timeout, fallback rate và phân phối routes; click rate chỉ dùng nếu logging/denominator đủ tin cậy.
5. Rollback bằng toàn bộ bundle tương thích; không chỉ đổi model mà để vector index của model mới. Ghi trigger rollback trong release record.
6. Cập nhật [CURRENT_STATE](../as-built/CURRENT_STATE.md), README active training và evidence mới; giữ evidence lịch sử theo snapshot. Lưu bundle predecessor có thể phục hồi đến khi nghiệm thu rollback, theo lifecycle đã thống nhất.

## 12. Chia đầu việc để triển khai

| Gói | Phạm vi | Kết quả review được |
|---|---|---|
| D1 | Manifest + trace + evaluator | Một run baseline tái tính được từ per-query output |
| D2 | Tách normalization và ranking flags | Dense raw đúng nghĩa và regression tests |
| D3 | Ma trận chất lượng | Báo cáo nguyên nhân, rescue/harm, quyết định nhánh |
| D4 | Gated lookup hoặc exact backend nếu evidence yêu cầu | Candidate dev-locked, cùng API contract |
| D5 | Load benchmark | Full endpoint report và bottleneck có số liệu |
| D6 | Trainer chung + weight/mask experiment nếu cần | Checkpoint chọn bằng dev, budget/splits có audit |
| D7 | Holdout + release docs | Quyết định có scope, bundle và rollback |

Ưu tiên bắt đầu D1–D3. Chưa mở rộng train hoặc viết lại hạ tầng trước khi biết regression đến từ fusion, normalizer, ranking hay model.

## 13. Checklist theo dõi

- [ ] P0: khóa baseline, splits, manifest và gates.
- [ ] P1: trace đủ và summary tái lập.
- [ ] P2: dense raw và ablation flags được kiểm thử.
- [ ] P3: chất lượng theo scope, rescue/harm và stage-loss report.
- [ ] P4: quyết định lexical/backend trên dev.
- [ ] P5: endpoint load test và SLA characterization.
- [ ] P6: ghi rõ skipped hoặc hoàn thành train bổ sung; checkpoint mới quay lại P3–P5.
- [ ] P7: holdout sau lock, decision record.
- [ ] P8: release, smoke, rollback và as-built cập nhật.

Mỗi bước ghi `run_id`, ngày thực hiện, artifact path, kết quả gate và công việc còn thiếu. Chỉ đánh dấu hoàn thành khi có evidence tương ứng.

## 14. Chuẩn bị thực thi: nguồn dữ liệu và hạn chế đã xác minh

Rà soát bổ sung ngày 2026-09-28. Bảng này chỉ xác nhận đường dẫn/code đã đọc; không thay thế kiểm tra hash và runtime của P0.

| Thành phần | Nguồn hiện có | Cách sử dụng |
|---|---|---|
| POI dev | `data/vietnam/train_stage1_v6_hardneg_6k_clean/query_train_view.parquet` | Lọc `split=dev`; manifest báo 600 case, 3.600 rows; xác minh lại trước run |
| POI pairs sạch | `data/vietnam/train_stage1_v6_hardneg_6k_clean/training_pairs.parquet` | Audit overlap; không tự dùng pack diagnostic gốc thay thế |
| Brand queries | `data/vietnam/train_stage1_brand_queries_v3/train_eval_view/brand_queries_v1.parquet` | Join family split đã khóa, xác minh schema và membership v3; không đo dev trên Gold families |
| POI regression | `data/vietnam/stage1_eval_suite_v2/gold_stage1_v2_1/` | Regression sau dev lock; không tuning |
| Brand regression | `data/vietnam/stage1_eval_suite_v2/gold_stage1_brand_v1/` | Chấm semantics family/namespace |
| Holdout mới | Chưa xây trong quy trình này | Là phụ thuộc của P7; không đổi tên Gold hiện tại thành holdout mới |

Các hạn chế cần xử lý trong D1–D2:

- `/v1/debug/trace_suggest` hiện cắt mỗi stage ở 80 IDs và `top_k` tối đa 50. Muốn audit top 100, cần trace nội bộ đầy đủ hoặc runner offline; không tăng response limit sản phẩm chỉ để phục vụ benchmark.
- Trace hiện gộp `after_dedup_cap`; chưa tách mất ứng viên do dedup và cap. Cần ghi hai mốc riêng.
- Pipeline thực thi geo trước name-address/name-quality; tên và thứ tự stage mới phải giữ đúng hành vi được đo, không mô tả geo như bước cuối nếu code chưa đổi.
- `docker-compose.search-dev.yml` phần bench còn đặt `POI_INDEX=vn-poi-core-v1-me5-small`. Không chạy với mặc định đó cho corpus v3; cấu hình experiment phải pin index/model/embeddings hiện hành riêng.
- Nếu dev case trùng intended POI đã tham gia train checkpoint thì dev serving có thể đánh giá quá lạc quan. Audit entity-level overlap và ghi hạn chế; holdout mới vẫn cần để xác nhận tổng quát hóa.

## 15. Tiêu chí nghiên cứu đề xuất và quyết định còn cần chốt

Để tránh gate hoàn toàn định tính, áp dụng bảng dưới đây làm **đề xuất ban đầu cho lựa chọn trên dev**. Đây không phải SLA sản phẩm đã được chấp thuận. Ghi chính xác ngưỡng đã chọn vào protocol trước khi chạy candidates; không chỉnh ngưỡng sau khi xem điểm để hợp thức hóa winner.

| Hạng mục | Đề xuất khởi đầu | Cách xử lý khi chưa đủ evidence |
|---|---|---|
| POI final ranking | Hit@1, Hit@10 và MRR@10 không giảm quá 0,01 tuyệt đối so baseline cùng điều kiện | Report CI và số case bị hại; không chỉ xét trung bình |
| Brand | Family AnyCompatibleHit@10 và group MRR@10 không giảm quá 0,01; coverage@20 không giảm quá 0,02 | Namespace có ít case: manual audit toàn bộ regression |
| Namespace errors | Không tăng quá 0,01 tuyệt đối trên namespace subset | Công bố mẫu số và counterexamples |
| Numeric constraints | Không có regression đã xác minh về số/mã đúng thành số/mã sai trong suite | Suite nhỏ chỉ là gate regression, không chứng minh zero error ngoài suite |
| Prefix | Không giảm quá 0,01 FHC@10 trên readiness-valid sessions | Nếu chỉ 20 case đủ SHC, SHC không làm gate duy nhất |
| Thống kê | Paired bootstrap 10.000 lần, seed 42, CI 95%, theo case/family | CI rộng hơn tolerance: chưa đủ bằng chứng non-inferiority; bổ sung mẫu |
| Latency nghiên cứu | Report p50/p95/p99 và throughput ở từng mức tải; xét giảm ít nhất 10% p95 ở cùng tải như tín hiệu cải thiện | Tín hiệu này không thay target QPS/SLA; ghi biến thiên giữa 3 lượt |

Với non-inferiority, xét cận dưới CI của delta so baseline có nằm trên `-tolerance` hay không; không dùng “không có khác biệt có ý nghĩa” để khẳng định tương đương. Các gate trên là theo từng metric/scope, không gộp thành một điểm khiến cải thiện POI che mất regression brand.

Các quyết định sản phẩm cần điền trước nghiệm thu P7/P8: target QPS, latency p95/p99 tối đa, error/timeout budget, traffic mix theo intent và môi trường triển khai. Có thể hoàn thành tooling và characterization khi các giá trị này còn pending; chưa đánh dấu production-ready.

## 16. Hợp đồng trace và decision record

### Per-query record tối thiểu

```json
{
  "schema_version": "dense-first-trace-v1",
  "run_id": "<unique-run-id>",
  "query_id": "<stable-id>",
  "group_id": "<case-or-family-id>",
  "dataset_role": "dev",
  "query_text": "<raw-text>",
  "encoder_input": "<actual-input-before-query-prefix>",
  "accepted_poi_ids": ["<poi-id>"],
  "status": "ok",
  "error": null,
  "stages": {
    "dense": [{"poi_id": "<poi-id>", "branch_rank": 1, "raw_score": 0.0, "score_kind": "cosine"}]
  },
  "timings_ms": {"client_total": null, "server_total": null},
  "profile_id": "<manifest-profile-id>"
}
```

Đây là schema minh họa cần triển khai và validate. Giá trị `0.0` chỉ là placeholder, không được điền cho score không đo được: dùng `null` cùng lý do. Mọi stage khác tuân cùng quy ước; ghi score kind đúng thực tế của backend. Trace failure giữ nguyên query/group ID và accepted IDs, không biến lỗi thành record thành công có danh sách rỗng.

### Decision record cuối mỗi vòng

```text
Decision ID / date:
Question / scope:
Baseline run_id:
Candidate run_id:
Locked protocol / manifest hashes:
Paired quality deltas / CIs:
Rescued cases / harmed cases / unresolved cases:
Latency / QPS / machine / background load:
Gates: pass / fail / pending, reason per gate:
Decision: keep baseline / advance candidate / collect more evidence:
Lexical routes retained / removed and reason:
Next step / rollback bundle:
```

Không để record chỉ ghi “dense tốt hơn”: phải nêu checkpoint, budget, scope, backend và post-processing đã so sánh.
