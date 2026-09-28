# Kết quả thực thi dense-first và quyết định kiến trúc

Ngày đo: 2026-09-28. Đây là evidence nghiên cứu trên checkout hiện tại; API dense-first đã được đo ở compose cách ly, cổng 8003. Cấu hình demo hiện hành chưa được chuyển sang ứng viên này. Tác vụ local chỉ gồm inference, truy vấn Elasticsearch, replay và benchmark; **không train trên GPU local**. Chưa có SLA, nên phép đo tải chỉ dùng để so sánh.

## Quyết định

Mốc bàn giao mới: [tạm chốt Stage 1 để bắt đầu Stage 2](../deliveries/w3/05_STAGE1_HANDOFF.md). Giữ dense-first làm baseline chính và hybrid raw làm đối chứng coverage; mở nghiên cứu ranking trong khi các gate release còn pending.

Bổ sung sau khi người dùng yêu cầu đề xuất SLA: [quyết định hiện tại, thay đổi cần làm và SLA pilot v0.1](RETRIEVAL_DECISIONS_AND_PILOT_SLA_2026_09_28.md). SLA mới là mục tiêu đề xuất, không thay đổi trạng thái characterization của các phép đo lịch sử bên dưới.

Giữ **dense ANN + thứ tự raw** làm đường truy xuất POI mặc định cho ứng viên nghiên cứu. Giữ lexical cho truy vấn brand đã nhận diện, prefix/ngắn, fallback và tra cứu tên có điều kiện. Bỏ việc chạy lexical rộng rồi trộn RRF cho mọi truy vấn POI trong ứng viên này. Không xóa Elasticsearch: hệ thống vẫn dùng nó để lấy document, tìm kiếm địa lý, catalog bản đồ và các nhánh lexical có ích. Chưa thay ANN bằng exact GPU; exact cải thiện chất lượng một ít nhưng phép đo endpoint không cho thấy lợi thế thông lượng ổn định.

Ứng viên đã đo có `retrieval_profile=dense_first`, `ranking_profile=raw`, `encoder_normalizer=raw`, `dense_backend=ann`, brand fuzzy và membership bật. `name_lookup` vẫn **tắt mặc định**: nó cứu 25 truy vấn POI dev nhưng làm hại `ATM MBBank` ở brand dev. Không nâng thành mặc định dựa trên tập dev này.

## Trạng thái từng bước

| Bước | Kết quả | Gate |
|---|---|---|
| P0 baseline/provenance | Kiểm tra model, vector, ID map, index cùng 179.209 POI; audit overlap train/dev và Gold; manifest và hash trong `artifacts/results/dense_first/`. | Hoàn tất cho nghiên cứu |
| P1 trace/evaluator | Trace từng query, branch, stage, timing; replay summary và paired rescue/harm; test evaluator. | Hoàn tất |
| P2 ablation độc lập | Tách normalizer, retrieval, ranking, depth 50/100 và backend. | Hoàn tất |
| P3 đo lexical | Đo 3.600 POI dev và 126 brand dev (35 family), raw/glue; so sánh ANN, exact, lexical, hybrid và ranking. | Hoàn tất trên dev |
| P4 lookup/backend | Router brand có membership; tra cứu tên bounded top 50 thử nghiệm; exact GPU inference. | Có ứng viên nghiên cứu; lookup chưa qua gate brand |
| P5 tốc độ | Closed-loop 128 request/ô, lặp 3 lần, đồng thời 1/4/8/16, 80% POI–20% brand, keepalive, 0 lỗi trong các ô đã đo. | Đã đo; SLA chưa đặt |
| P6 train | Audit vấn đề sampling weight/loss weight và chuẩn bị Kaggle pack `loss_only`; **chưa submit train** vì serving change cần được đánh giá trước. | Chưa kích hoạt |
| P7 holdout | Hai bộ stress truy vấn source-identity cho POI lạnh đã chạy. Bộ thứ hai được tạo sau khi xem kết quả bộ đầu; cả hai là synthetic/regression, không phải blind human holdout. | Chưa qua |
| P8 release | Chưa triển khai production/đổi demo mặc định. | Chưa qua |

## Chất lượng: cùng model 6k dev-lock, cùng corpus/index

Hit@1 POI tính trên 3.600 query. Brand Hit@1 là trung bình theo 35 family, không phải trung bình query. Các tập này dùng để chọn ứng viên, **không** là holdout cuối.

| Cấu hình | POI dev Hit@1 | Brand dev family Hit@1 | Diễn giải |
|---|---:|---:|---|
| ANN raw top 100 | 91,11% | 57,72% | Mốc dense |
| Exact GPU raw top 100 | 92,00% | 60,34% | Chất lượng cao hơn chút; chi phí phải đo ở endpoint |
| Lexical riêng | 59,58% | 58,20% | Không đủ thay dense cho POI |
| Hybrid hiện hành, depth 100 | 80,53% | 57,24% | Ranking/fusion hiện hành làm hại POI dev |
| Dense-first + brand router/membership | 91,11% | 74,39% | POI giữ nguyên; brand +17 rescue/0 harm so với ANN trên dev |
| Thử thêm name lookup top 50 | 91,81% | 73,98% | POI +25 rescue/0 harm; brand +17 rescue/1 harm so với ANN |

Khi so hybrid hiện hành với ANN trên POI dev: 135 query được cứu nhưng 516 query bị hại ở Hit@1. `glue_code_spans` cho POI dev 90,78% so với 91,11% của raw, nên không đổi normalizer trong ứng viên. `name_address` broad rerank cũng làm giảm POI dev, vì vậy ứng viên dùng thứ tự raw. Tất cả giá trị trên là từ replay depth 100 sau khi sửa lỗi đối chiếu depth trong evaluator; các run sớm được đánh dấu loại khỏi evidence.

Stress source-identity thứ hai gồm 165 POI lạnh/660 query sinh từ tên, biến thể và lỗi gõ, không trùng entity train/Gold theo audit: ANN Hit@1 82,12%, hybrid hiện hành 96,21%, lookup thử nghiệm 99,85%. Kết quả này cho thấy lexical có tác dụng rõ ở truy vấn tên thực thể, nhưng ground truth là danh tính nguồn sinh query, không phải đánh giá intent thủ công; không dùng 99,85% làm cam kết chất lượng chung. Brand audit còn thấy 21,43% query dev có member sai namespace ở đâu đó trong top 20: việc lọc namespace chưa giải quyết triệt để.

## Tốc độ endpoint

Số dưới là **median của p95 client latency** và median QPS qua ba lần lặp, với 128 request mỗi ô. Mô hình tải closed-loop tìm thông lượng theo mức đồng thời, không mô phỏng arrival rate production. Máy và các tiến trình nền nằm trong manifest của mỗi run. Không suy diễn SLA từ bảng này.

| Cấu hình | c=1 p95 / QPS | c=4 p95 / QPS | c=8 p95 / QPS | c=16 p95 / QPS |
|---|---:|---:|---:|---:|
| ANN raw | 39,82 ms / 30,08 | 68,79 / 66,69 | 135,39 / 65,13 | 264,68 / 66,65 |
| Exact raw | 34,02 / 33,42 | 75,05 / 66,59 | 138,98 / 68,63 | 253,94 / 68,21 |
| Hybrid hiện hành | 92,21 / 14,28 | 244,34 / 24,86 | 425,23 / 24,16 | 777,03 / 24,52 |
| Dense-first + brand membership | 39,94 / 30,66 | 72,25 / 67,89 | 212,61 / 66,13 | 260,28 / 67,21 |

Ở c=8, p95 của ứng viên brand dao động nhiều dù QPS gần ANN; cần chạy lại khi có workload/SLA thật. Lookup tên chưa được tính trong bảng tải, do nó chưa qua quality gate.

## Việc còn lại trước khi release

1. Khóa một holdout độc lập do người biên soạn, đủ POI/entity, brand namespace, địa chỉ/số nhà, prefix, typo và geo. Không dùng lại hai bộ synthetic đã xem kết quả để tuyên bố pass holdout.
2. Kiểm tra intent của lookup tên và false promotion toàn corpus; sửa ca `ATM MBBank`, rồi đo lại brand/POI dev và holdout. Chỉ bật nếu lợi ích qua gate và latency endpoint đã đo.
3. Đặt workload và SLA nếu cần quyết định production; nếu không, chỉ tiếp tục báo đường cong tải so sánh. Chạy regression cho contract API/map, prefix, numeric và geo trên ứng viên đóng băng.
4. Nếu sau sửa serving vẫn còn gap của model, chạy trial `loss_only` trên **Kaggle** bằng pack đã chuẩn bị, đánh giá dev-lock, tải checkpoint về rồi mới inference/re-encode/benchmark local. Không chạy optimizer local.
5. Chỉ sau khi P7 qua gate mới lập release manifest, chuyển cấu hình demo, smoke và diễn tập rollback.

## Tái lập và nguồn số

- Kế hoạch/gate: [DENSE_FIRST_EXECUTION_PLAN.md](DENSE_FIRST_EXECUTION_PLAN.md).
- Mã runner: [`dense_first_ablation.py`](../../apps/poi-search/bench/dense_first_ablation.py), [`dense_first_replay.py`](../../apps/poi-search/bench/dense_first_replay.py), [`dense_first_gate_report.py`](../../apps/poi-search/bench/dense_first_gate_report.py), [`dense_first_load.py`](../../apps/poi-search/bench/dense_first_load.py), [`dense_first_name_report.py`](../../apps/poi-search/bench/dense_first_name_report.py).
- Mã API và compose cách ly: [`pipeline.py`](../../apps/poi-search/api/pipeline.py), [`brand_router.py`](../../apps/poi-search/api/brand_router.py), [`name_lookup.py`](../../apps/poi-search/api/name_lookup.py), [`docker-compose.dense-first.yml`](../../apps/poi-search/docker-compose.dense-first.yml).
- Artifact local (bị ignore khỏi Git): `artifacts/results/dense_first/poi_dev_replay_20260928/`, `brand_dev_20260928/`, `gated_members_dev_20260928/`, `name_lookup50_nonbrand_dev_20260928/`, `cold_entity_v2_20260928/`, `load_comparison.json`, cùng manifest/hash trong từng run. Không ghi đè evidence cũ.
