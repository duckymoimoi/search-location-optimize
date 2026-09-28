# Báo cáo thử nghiệm và tạm chốt Stage 1 để chuyển sang Stage 2

Cập nhật dữ liệu: [Gold v2.2 tái phát hành](../../../data/vietnam/stage1_eval_suite_v2/gold_stage1_v2_2/README.md) đã được kiểm tra và tái dựng byte-identical; [EDA 40 bảng](../dataset_eda_20260928/README.md) là thống kê hiện hành. Provenance lịch sử v2.1 vẫn chưa khôi phục, v2.2 không phải holdout mới. Retrieval đã qua 4.386 query offline và 190 query live mỗi profile S1-A/S1-B; Stage 2 chưa train/triển khai.

Ngày chốt: 2026-09-28. Trạng thái sau kiểm tra thực tế: **baseline retrieval đã kiểm tra; Stage 2 chưa train/triển khai; sign-off dữ liệu còn pending**. Bản trước chỉ là đề xuất bàn giao và chưa có kiểm tra chuyển pha. Xem [biên bản kiểm tra và chuẩn bị GitHub](../../operations/STAGE1_SOURCE_RELEASE_CHECKLIST.md) cho kết quả mới, gồm lỗi provenance Gold POI v2.1 chưa khôi phục được. Đây chưa là nghiệm thu release hay xác nhận SLA production.

Theo [định nghĩa dự án](../../specs/search2.0.md), Stage 1 tìm candidate theo văn bản; Stage 2 xếp lại chính candidate đó bằng text, geo, time và behavior. Tên phase “Stage 2” trong bảng tiến độ tuần không thay đổi ranh giới kỹ thuật này.

## 1. Quyết định tạm chốt

| Thành phần | Quyết định v0.1 |
|---|---|
| Model | Giữ `me5-6k-devlock-epoch2`; chưa mở trial train mới. |
| Corpus/index | 179.209 POI; index `vn-poi-core-v3-me5-6k-devlock`; vector 384 chiều cùng checkpoint và ID map. |
| Dense backend | Elasticsearch ANN; exact GPU chỉ làm đối chứng recall/chất lượng. |
| Query encoder | `raw`; chưa áp dụng `glue_code_spans`. |
| Baseline chính S1-A | `dense_first`, raw ranking, depth 100; brand fuzzy/membership bật; name lookup promotion tắt. |
| Lexical | Giữ cho routing brand, truy vấn ngắn và fallback; giữ khả năng lấy lexical candidate phục vụ đối chứng coverage. Không xóa Elasticsearch. |
| Đối chứng S1-B | `hybrid_raw` depth 100 đã có trace, trước broad name/address/quality rerank; dùng đo giá trị của candidate coverage đối với Stage 2. |
| Stage 2 output | Rerank toàn bộ candidate đầu vào; tầng response lấy top 10. Không tự truy xuất thêm POI trong ranker. |
| Triển khai | Giữ demo hiện hành trong khi nghiên cứu Stage 2; cấu hình trên là baseline bàn giao, không phải thông báo đã đổi runtime mặc định. |

Không tiếp tục tối ưu Stage 1 vô hạn trước khi bắt đầu ranking. Mọi thay đổi model, normalizer, routing, fusion, filter hoặc candidate budget sau mốc này phải có version mới và đo lại candidate coverage; không thay âm thầm trong một thí nghiệm Stage 2.

## 2. Thiết kế thử nghiệm và độ tin cậy

- POI dev: 3.600 query. Brand dev: 126 query, 35 family; metric brand lấy trung bình theo family. Hai tập được dùng chọn cấu hình nên không phải kiểm định độc lập.
- Ablation cùng model/index: raw/glue, ANN/exact/lexical/hybrid, ranking raw/dedup/name-address/name-quality và depth 50/100. Các run sớm có lỗi depth đã bị loại; số liệu dùng replay đã sửa.
- Stress POI lạnh v2: 165 entity/660 query source-identity synthetic; tạo sau khi đã xem stress v1. Dùng phát hiện lỗi và regression, không chứng minh generalization trên traffic thật.
- Load: closed-loop, 128 request/ô, ba lượt, concurrency 1/4/8/16, mix 80% POI–20% brand, keepalive; local RTX 3060 Laptop GPU, một API worker. Không có train local.
- Đã chạy 60 tests liên quan evaluator, router, lookup, geo và training weights trong đợt thực thi trước; compile và compose config hợp lệ. Các kiểm tra đó không thay thế holdout hay nghiệm thu SLA.
- Snapshot số liệu và SHA-256 nguồn: [evidence_snapshot.json](evidence_snapshot.json). Hash trace khóa đầu vào offline; artifact lớn giữ local, snapshot nhỏ có thể đưa vào Git. Việc có hash không biến phép đo cũ thành đo trên mọi thay đổi code hiện tại.

## 3. Kết quả quan trọng đối với Stage 2

| Tập | Candidate/ranking | Hit@1 | Hit@10 | Hit@100 |
|---|---|---:|---:|---:|
| POI dev | S1-A dense-first | 91,11% | 97,56% | 98,53% |
| POI dev | S1-B hybrid raw | 78,64% | 95,44% | 99,67% |
| POI dev | Hybrid + ranking hiện hành depth 100 | 80,53% | 94,75% | 99,67% |
| Brand dev, macro family | S1-A dense-first | 74,39% | 89,11% | 94,52% |
| Brand dev, macro family | S1-B hybrid raw | 66,34% | 91,43% | 99,52% |
| Brand dev, macro family | Hybrid + ranking hiện hành depth 100 | 57,24% | 73,91% | 99,52% |
| Stress POI lạnh v2 | S1-A dense-first | 82,12% | 90,15% | 93,03% |
| Stress POI lạnh v2 | S1-B hybrid raw | 88,64% | 98,94% | 100,00% |

**Phải phân biệt ranking với coverage.** S1-A có thứ tự tốt trên dev nhưng S1-B chứa đáp án đúng thường xuyên hơn ở top 100: +1,14 điểm phần trăm POI dev, +5,00 điểm brand dev và +6,97 điểm trên stress POI lạnh. Đây là lý do giữ S1-B khi bắt đầu Stage 2. Không loại lexical chỉ vì Hit@1 của RRF thấp.

Hit@100 ở đây là tỷ lệ có ít nhất một accepted POI trong top 100, không phải recall của toàn bộ positives. Nó là trần Hit@1 lý tưởng của ranker trên candidate cố định với đúng qrels và cách lấy trung bình này; không phải mức chất lượng ranker chắc chắn đạt. Khi có nhiều positives, báo thêm coverage@K. Nếu thêm filter/dedup sau retrieval thì phải đo lại trần sau filter.

S1-A nâng brand Hit@1 so với ANN raw từ 57,72% lên 74,39%, 17 query được cứu/0 query bị hại trên dev. Nhưng membership filtering/routing có thể giảm coverage so với hybrid rộng; Stage 2 phải nhìn cả pool, không chỉ điểm hạng đầu. Name lookup giúp POI dev thêm 25 rescue/0 harm nhưng gây lỗi `ATM MBBank`, nên chưa bật.

Exact raw đạt POI dev Hit@1 92,00%, so với ANN 91,11%; lợi thế endpoint throughput không rõ. Chưa có lý do thay backend hoặc train model chỉ để chữa lỗi ranking đang quan sát được. Các phép đo này so serving trên cùng checkpoint, không đủ thay thế toàn bộ chứng minh model vượt zero-shot/lexical trên test độc lập của milestone training.

## 4. Tốc độ và ngân sách cho Stage 2

| Endpoint đã đo | c=4 median p95 / QPS | c=16 median p95 / QPS |
|---|---:|---:|
| S1-A + hydration/response hiện tại | 72,25 ms / 67,89 | 260,28 ms / 67,21 |
| Hybrid + ranking hiện hành | 244,34 ms / 24,86 | 777,03 ms / 24,52 |

Đây là latency endpoint, không phải chi phí riêng Stage 1. Benchmark hybrid current không đại diện cho latency của S1-B + ranker Stage 2 mới. Chưa có benchmark endpoint riêng cho cấu hình đó; phải đo khi ghép pipeline. Không cộng p95 từng stage để suy ra p95 E2E.

Giữ [SLA pilot đề xuất](../../operations/RETRIEVAL_DECISIONS_AND_PILOT_SLA_2026_09_28.md): tải bình thường 20 QPS, p95 ≤150 ms, p99 ≤300 ms, lỗi ≤0,1%; burst 40 QPS trong 60 giây với p95 ≤300 ms, p99 ≤600 ms. Mục tiêu này chưa được nghiệm thu bằng open-loop/soak. Stage 2 text-only dùng nó làm mục tiêu E2E chung, không nhận thêm một ngân sách 150 ms riêng. Khi thêm geo/time/behavior, phải mở rộng workload và đo lại phạm vi SLA.

## 5. Ranh giới bàn giao Stage 1 → Stage 2

**Đầu vào ranking cần đóng băng:** query ID/text, suite/split, context thời điểm request, version model/index/policy, route, ordered candidate IDs, branch ranks/scores với tên thang điểm, document/features version, accepted IDs và nguồn nhãn trong dữ liệu offline. Không cộng trực tiếp ES score với cosine khi chưa hiệu chuẩn. Missing context là null kèm cờ missing; không dùng khoảng cách 0 khi thiếu origin.

Trace hiện có chứa query, qrels, branch/stage, timing và candidate IDs. Đây là nguồn candidate replay; nó chưa tự cung cấp nhãn lựa chọn theo bối cảnh, impression log hay feature store point-in-time đầy đủ cho Stage 2. Cần kiểm tra và hydrate feature snapshot trước khi train ranker.

**Hai track dữ liệu cố định:** lấy `gated_candidate` và `hybrid_raw`, normalizer `raw`, từ các trace được hash trong snapshot. So sánh ranker với retrieval-order của chính track đó; khi đổi S1-A sang S1-B, ghi thành thí nghiệm candidate pool riêng. Không quy toàn bộ cải thiện do đổi pool cho ranker.

**Đầu ra ranking:** cùng tập POI IDs, mỗi ID một score/rank có thể giải thích nguồn feature; top 10 được cắt sau ranking. Nếu phát hiện cần truy xuất thêm candidate thì tạo phiên bản Stage 1 mới, không đưa retrieval ẩn vào ranker.

**Điều kiện dữ liệu:** Stage 2 personalization cần impression/selection thật với context tại thời điểm đó. Các user/history demo chỉ dùng kiểm tra chức năng nếu chưa xác nhận provenance, không làm bằng chứng model học được hành vi thật. Nếu chưa có log, bắt đầu retrieval-order, text-only và geo heuristic có nhãn kiểm định; phần time/behavior để pending. Không tự tạo click giả rồi báo là chất lượng personalization.

## 6. Công việc Stage 2 bắt đầu từ đây

| Thứ tự | Công việc | Đầu ra / gate |
|---|---|---|
| S2.0 | Audit nguồn context, impression, selection, timestamps và provenance; hydrate snapshot features cho hai pool | Dataset inventory; missingness; phân biệt dữ liệu thật/demo/synthetic; split đóng băng. Nếu thiếu log, vẫn triển khai evaluator và baseline heuristic. |
| S2.1 | Dựng ranking evaluator trên candidate cố định | Hit@1/10, MRR@10, nDCG@10 nếu có graded labels, coverage ceiling và paired CI; invariance test đảm bảo không thêm/mất ID. |
| S2.2 | Retrieval-order → text-only; chạy riêng trên S1-A và S1-B | Bảng 2 pool × 2 ranker, rescue/harm và latency; biết lợi ích do pool hay do ranking. |
| S2.3 | Text-only → +Geo | Đo same-name, brand branch, near/far và missing-origin; không dùng geo tạo ra qrels rồi coi đó là đánh giá độc lập. |
| S2.4 | +Time → +Behavior → Full quality features khi nguồn dữ liệu hợp lệ | Ablation từng nhóm; feature tại thời điểm request, không dùng tổng click tương lai. Split theo thời gian/session, giữ variant cùng case trong một split. |
| S2.5 | Error analysis → hypothesis → fix → re-evaluate | Mỗi experiment có quan sát, giả thuyết, thay đổi duy nhất, kết quả theo slice và quyết định giữ/bỏ. |
| S2.6 | Chọn ranker trên dev, mở holdout và đo E2E | Chất lượng không regression theo gate đã khóa; đo tải dài, namespace/numeric/geo/contract và rollback trước release. |

Không chốt cross-encoder/LambdaMART hay kiến trúc học ranking khác trước audit dữ liệu và baseline. Model học phải chứng minh thêm giá trị so với baseline đơn giản. Nếu train nặng, chạy Kaggle; local chỉ dùng model tải về để inference/benchmark.

## 7. Nợ kỹ thuật và điều kiện mở lại Stage 1

| Vấn đề | Xử lý khi chuyển Stage 2 | Khi nào mở lại Stage 1 |
|---|---|---|
| POI lạnh/brand bị thiếu candidate | Giữ S1-B đối chứng và báo ceiling theo slice | Đáp án vắng trong pool nên ranker không thể sửa; cần lexical rescue/routing/budget mới có version |
| Namespace ATM/ngân hàng | Lookup vẫn tắt; tạo regression và đo sai namespace top 10 | Nếu routing/membership filter đã loại đúng entity trước ranker |
| Trùng tên và lookup uniqueness | Chuyển thành backlog lookup; không promote chỉ vì duy nhất top 50 | Khi có cơ chế xác minh toàn corpus và qua quality/latency gate |
| Holdout độc lập chưa có | Không ngăn xây baseline ranking; ngăn tuyên bố generalization/release | Nếu holdout phát hiện gap retrieval, sửa và lập vòng đánh giá mới |
| Chưa có log hành vi đủ tin cậy | Làm text/geo heuristic, thu thập và audit log | Không phải lý do train lại retriever; là thiếu dữ liệu Stage 2 |
| SLA mới là đề xuất | Giữ mục tiêu và chạy open-loop/soak khi có pipeline Stage 2 | Chỉ mở optimization retrieval khi profiling chỉ ra bottleneck |

**Chấp thuận chuyển pha ở mức nghiên cứu:** có checkpoint, corpus/index nhất quán, candidate trace, đối chứng coverage, số đo chất lượng/tốc độ và danh sách giới hạn đủ rõ để bắt đầu Stage 2. **Chưa chấp thuận release:** holdout độc lập, kiểm định context/namespace và SLA dài hạn còn thiếu. Việc chuyển pha không xóa các gate này.

## 8. Tài liệu và evidence bàn giao

- [Snapshot metric, bundle và hash nguồn](evidence_snapshot.json).
- [Báo cáo thực thi P0–P8](../../operations/DENSE_FIRST_EXECUTION_STATUS_2026_09_28.md).
- [Quyết định kiến trúc và SLA pilot](../../operations/RETRIEVAL_DECISIONS_AND_PILOT_SLA_2026_09_28.md).
- [Kế hoạch dense-first và gate](../../operations/DENSE_FIRST_EXECUTION_PLAN.md).
- [Pipeline hiện có](../../../apps/poi-search/api/pipeline.py), [ranking hiện có](../../../apps/poi-search/api/ranking.py), [runner đánh giá](../../../apps/poi-search/bench/dense_first_ablation.py).

Artifact lớn là file local được tham chiếu bằng đường dẫn và hash trong snapshot; để tái lập ở máy khác phải chuyển đúng artifact tương ứng. Tài liệu này không khẳng định các file đó đã được publish hoặc lưu trữ từ xa.
