# Quyết định retrieval và SLA pilot đề xuất

Ngày: 2026-09-28. Phạm vi: demo/pilot một máy, corpus 179.209 POI, checkpoint `me5-6k-devlock-epoch2`. Cơ sở: [báo cáo thực thi](DENSE_FIRST_EXECUTION_STATUS_2026_09_28.md) và các artifact benchmark local được liệt kê ở cuối tài liệu.

**Kết luận:** chốt hướng dense-first có lexical theo intent, giữ ANN và model hiện tại. Chưa thay cấu hình demo trên toàn bộ traffic. Ưu tiên sửa lookup tên và brand namespace, xác nhận chất lượng ngoài dev, rồi nghiệm thu tải theo SLA pilot dưới đây. Các ngưỡng SLA là đề xuất mới sau phân tích benchmark, chưa phải cam kết đã đạt.

## 1. Những quyết định có thể chốt hiện tại

Cập nhật chuyển pha: [báo cáo tạm chốt Stage 1 và bàn giao Stage 2](../deliveries/w3/05_STAGE1_HANDOFF.md). Các việc “trước khi chuyển pilot” bên dưới là gate triển khai, không cản việc bắt đầu nghiên cứu ranking trên hai candidate pool đóng băng.

| Quyết định | Bằng chứng và phạm vi áp dụng |
|---|---|
| Giữ Elasticsearch và lexical | Brand và truy vấn tên POI lạnh còn cần lexical; Elasticsearch còn phục vụ document, map và geo. Không có cơ sở xóa toàn bộ lexical. |
| Chọn dense-first có routing làm kiến trúc ứng viên | ANN raw đạt POI dev Hit@1 91,11%, hybrid current depth 100 chỉ 80,53%; router brand/membership nâng brand family Hit@1 từ 57,72% lên 74,39%. Đây là lựa chọn cho thử nghiệm/pilot sau gate, chưa là chứng minh trên traffic thật. |
| Giữ ANN làm backend ứng viên | Exact đạt POI dev 92,00%, nhưng QPS endpoint gần ANN. Mức cải thiện hiện tại chưa đủ để thêm phụ thuộc exact GPU vào serving mặc định. Giữ exact làm đối chứng chẩn đoán recall. |
| Giữ raw normalizer và raw ranking cho nhánh POI ứng viên | Glue đạt 90,78%, thấp hơn raw 91,11%; broad name/address rerank gây regression. Không suy rộng kết luận query-only này sang ranking có geo/origin. |
| Tắt name lookup promotion mặc định | POI dev +25 rescue/0 harm nhưng brand còn lỗi `ATM MBBank`. Tính duy nhất trong lexical top 50 không bảo đảm duy nhất toàn corpus. |
| Giữ checkpoint hiện tại, chưa train mới | Đã tìm thấy tác động lớn từ retrieval/ranking mà không đổi model. Sau sửa serving và đánh giá độc lập mới quyết định gap nào cần train. Training nặng và re-encode đi kèm trial trên Kaggle; local chỉ inference/benchmark model đã tải. |
| Giữ baseline triển khai hiện hành đến khi ứng viên qua gate | Hai bộ stress là synthetic đã được xem kết quả; chưa có holdout độc lập đủ intent và chưa nghiệm thu tải dài. |

Không chốt “dense-only tốt hơn mọi truy vấn”. Trên 660 query source-identity của POI lạnh, ANN Hit@1 82,12%, hybrid current 96,21%. Chênh lệch này trái chiều với dev và cho thấy thay toàn bộ đường retrieval có nguy cơ làm giảm khả năng tìm tên thực thể. Lookup thử nghiệm 99,85% trên stress là bằng chứng để tiếp tục nghiên cứu, không phải chất lượng sản phẩm đã xác nhận.

## 2. Những thay đổi cần làm trước khi chuyển pilot

| Ưu tiên | Thay đổi | Điều kiện hoàn tất |
|---|---|---|
| P0 | Sửa phân biệt brand/namespace: ATM, ngân hàng/chi nhánh và tên POI có brand | `ATM MBBank` đúng intent; kiểm tra cả false positive và false negative; đo Hit@1/10 và namespace trên từng slice. Không vá chỉ theo query ID. |
| P0 | Làm lookup tên bảo thủ hơn | Kiểm tra alias và độ duy nhất trên corpus, giữ ràng buộc số/mã và địa chỉ, không promote khi intent mơ hồ; case trùng tên, khác chi nhánh và typo phải có regression. |
| P0 | Đóng băng tập đánh giá độc lập trước khi chạy ứng viên | Ít nhất 200 case POI và 40 brand family, tối thiểu 800 query, gồm tên hiếm, typo, địa chỉ/số/mã, prefix, namespace, geo. Mỗi slice trọng yếu ít nhất 50 query. Người biên soạn không nhìn ranking ứng viên; một người khác kiểm tra qrels. Nếu CI còn rộng thì bổ sung case, không coi thiếu lực thống kê là pass. |
| P0 | Benchmark tải theo arrival rate và thêm quan sát vận hành | Ghi client latency, timeout, 429/5xx, queue, encode, ES, route/fallback, VRAM/RAM; kiểm tra model/index hash và readiness trước nhận traffic. |
| P1 | Timeout, admission control và rollback | Cấu hình deadline và giới hạn tải có đo; request trong quota bị 429 vẫn tính lỗi. Khi fallback phải ghi degraded route để thấy suy giảm chất lượng. Diễn tập quay về bundle baseline. |
| P2 | Trial train nếu lỗi còn thuộc model | Audit sampling/loss weight, chạy `loss_only` trên Kaggle, chọn bằng dev-lock rồi đánh giá lại P3–P7 với model/vector/index mới. Không dùng holdout đã mở để chọn epoch. |

Nhánh prefix đang có đường lexical, nhưng vẫn cần đánh giá riêng; cấu hình raw query-only không được coi là đã nghiệm thu geo hay numeric intent. Router brand có fuzzy/membership là ứng viên, chưa sửa hết namespace: audit hiện tại có 21,43% query brand dev chứa member sai namespace ở đâu đó trong top 20.

## 3. Bộ SLA pilot v0.1 đề xuất

Đây là mục tiêu dịch vụ nội bộ cho pilot, chưa là SLA thương mại. Độ khả thi được suy ra từ phép đo ngắn trên RTX 3060 Laptop GPU, một API worker và Elasticsearch devlock; chưa có chứng cứ cho uptime hoặc soak test. CPU/RAM chưa được ghi đầy đủ trong manifest cũ, phải bổ sung khi nghiệm thu.

### Phạm vi và tải

- Endpoint `POST /v1/suggest`, `top_k=10`, retrieval depth 100, model đã warm, corpus/index và policy đóng băng; debug trace tắt.
- Query-only, không origin/personalization. Mix khởi đầu 80% POI–20% brand. Prefix, geo, map catalog và frontend cần profile riêng trước khi nằm trong cam kết này.
- Tải bình thường **20 request/giây tổng trên instance**, arrival đều; tải burst **40 request/giây trong 60 giây**, mỗi 10 phút tối đa một burst, sau đó trở lại 20 QPS. QPS là request, không phải số người dùng.
- Dành GPU cho inference; không train hoặc chạy dịch vụ GPU khác. Không reindex hay thay checkpoint khi nghiệm thu. Khi corpus, máy, mix hoặc tính năng thay đổi, chạy lại protocol.

| Chỉ tiêu | Tải bình thường | Burst | Trạng thái |
|---|---:|---:|---|
| Client latency p95 | ≤150 ms | ≤300 ms | Đề xuất, cần open-loop test |
| Client latency p99 | ≤300 ms | ≤600 ms | Đề xuất, cần đủ mẫu tail |
| Request lỗi/timeout/429 trong quota | ≤0,1% | ≤0,5% | Đề xuất, phép đo cũ quá ngắn để xác nhận |
| Deadline request | 1.000 ms | 1.000 ms | Mục tiêu cấu hình và kiểm chứng, chưa xác nhận enforcement |
| Hồi phục sau burst | Trở về ngưỡng bình thường trong 60 giây | — | Cần kiểm chứng hàng đợi thoát tải |
| Availability theo thời gian | ≥99,0% trong giờ phục vụ đã đăng ký, đo theo tháng | Cùng mục tiêu | Mục tiêu vận hành pilot, chưa đo |
| Khôi phục bằng rollback | ≤15 phút từ khi xác nhận sự cố | Cùng mục tiêu | Mục tiêu diễn tập, chưa đo |

**Cách chọn ngưỡng:** ở c=4, ứng viên có p95 71,47–72,58 ms và p99 78,06–88,60 ms qua ba lần lặp, QPS median 67,89. Đặt 20 QPS bằng khoảng 30% thông lượng đo được để chừa dư địa; p95 150 ms lớn hơn khoảng hai lần p95 tại c=4. Ở c=8 p95 dao động 127,94–215,90 ms; ở c=16 lên đến 331,76 ms. Do đó không lấy 65–68 QPS làm tải cam kết và không coi median p95 là giới hạn xấu nhất. Closed-loop và open-loop khác nhau, nên dư địa này là lập luận đề xuất, không phải chứng nhận SLA.

**Định nghĩa đo:** latency bắt đầu khi request được lên lịch gửi tại client benchmark và kết thúc khi nhận đủ body; bao gồm chờ phía phát tải nếu có, hàng đợi server, encode, retrieval, hydration và serialize. Chạy client trên cùng LAN với service; không gộp thời gian gõ, debounce, Internet, render bản đồ hoặc tải tile vào SLA backend. Request không hoàn tất trước 1 giây tính lỗi, ghi timeout và không loại khỏi báo cáo. Báo percentile của request hoàn tất cùng error rate trên toàn bộ request được lên lịch; không dùng percentile thấp để che request thất bại. Với từng route có đủ mẫu, báo cả chỉ số riêng để traffic POI không che tail của brand.

**Availability:** đăng ký trước giờ phục vụ và maintenance; 1% error budget tương đương 4,8 phút trong một ngày phục vụ 8 giờ. Cứ 30 giây probe một query có expected result qua endpoint thực; probe lỗi hoặc vượt deadline đánh dấu slot 30 giây không khả dụng. Bảo trì ngoài lịch phục vụ không vào mẫu số; bảo trì trong giờ phục vụ vẫn tính downtime. Không suy ra availability từ 0 lỗi ở benchmark. Chưa đề xuất 99,9%/24×7 cho laptop một node.

### Chất lượng: gate nghiệm thu, không trộn với availability

| Tập / chỉ tiêu | Ngưỡng đề xuất | Ý nghĩa |
|---|---:|---|
| POI dev cố định | Hit@1 ≥91,0%; Hit@10 ≥97,0% | Guard regression, hiện ứng viên đạt 91,11% / 97,56% |
| Brand dev cố định, macro family | Hit@1 ≥73,0%; Hit@10 ≥88,0% | Guard regression, hiện ứng viên đạt 74,39% / 89,11% |
| Holdout độc lập, từng suite | CI95 dưới của paired delta Hit@1 và Hit@10 ≥−1 điểm phần trăm so với baseline triển khai đã đóng băng | Gate đề xuất trước khi mở holdout; bootstrap theo case POI/family brand |
| Slice trọng yếu | Point delta Hit@1/10 không giảm quá 2 điểm phần trăm; ca số/mã và ATM-vs-branch bắt buộc đã review không có lỗi nghiêm trọng | Không cho điểm tổng che regression có tác động sản phẩm |
| Namespace brand rõ ràng | Tỷ lệ query có kết quả sai namespace trong top 10 ≤1% trên tập đã adjudicate | Mục tiêu mới; audit top 20 cũ không đủ kết luận pass/fail ngưỡng này |

Các ngưỡng dev được chọn sau khi đã xem số, nên chỉ có giá trị chặn regression. Không dùng chúng để tuyên bố tổng quát hóa. Holdout phải so với baseline triển khai, không tự thay bằng đối chứng yếu hơn. Đánh giá namespace chỉ áp dụng query có intent rõ và nhãn đã review; báo riêng ambiguous intent.

## 4. Protocol nghiệm thu SLA và quyết định go/no-go

1. Khóa bundle model/vector/ID map/index/policy/code; ghi CPU, RAM, VRAM, driver, Docker limits, worker count và tải nền. Chuẩn bị baseline rollback, chạy health/readiness và smoke.
2. Warmup 5 phút. Dùng open-loop scheduler giữ arrival rate độc lập response; generator phải có đủ kết nối. Nếu generator không phát đúng lịch, ghi scheduling lag, tính từ lịch gửi và đánh dấu run không hợp lệ để lặp lại. Không tự giảm QPS khi server chậm.
3. Chạy 5, 10, 20 QPS, mỗi mức 10 phút, ba lượt thứ tự hoán đổi. Dùng pool query rộng, seed khác mỗi lượt; không chỉ lặp cùng 128 query như benchmark cũ. Mỗi lượt 20 QPS phải qua ngưỡng tổng và các cửa sổ 5 phút không chồng lấn. Báo mọi lượt, không chỉ median tốt.
4. Soak 20 QPS trong 60 phút. Từ nền 20 QPS, chạy ba burst 40 QPS ×60 giây cách nhau ít nhất 10 phút. Mỗi burst qua ngưỡng burst và hồi phục ≤60 giây; ghi queue, memory, errors và latency theo thời gian. Nếu vượt ngưỡng ở workload đúng phạm vi: no-go, sửa hoặc hạ tải đề xuất rồi đo lại.
5. Tiêm lỗi ngắn có kiểm soát trên môi trường cách ly: encoder unavailable, ES timeout, restart API; xác nhận lỗi/degraded observability và rollback ≤15 phút. Không tính lexical fallback là chất lượng tương đương dense chỉ vì trả HTTP 200.
6. Chạy quality gate độc lập, prefix/numeric/geo/contract regression theo phạm vi release. Nếu chỉnh code sau khi xem holdout, bộ đã mở trở thành regression; cần holdout mới cho lần quyết định tiếp theo.
7. Chỉ chuyển pilot khi các gate phù hợp scope đều qua. Thu thập ít nhất một tháng trong giờ phục vụ để báo availability thực tế; benchmark ngắn không chứng minh mục tiêu tháng.

Ngưỡng cảnh báo đề xuất sau khi có metrics: p95 >120 ms trong 5 phút; lỗi >0,05% trong 5 phút với đủ mẫu; queue/VRAM/RAM tăng liên tục qua soak; tần suất fallback tăng so với baseline. Ngưỡng vi phạm dùng đúng bảng SLA. Những cảnh báo và admission control này là công việc phải triển khai, chưa được coi là tính năng hiện có.

## 5. Evidence và giới hạn

- [`DENSE_FIRST_EXECUTION_STATUS_2026_09_28.md`](DENSE_FIRST_EXECUTION_STATUS_2026_09_28.md): kết quả và trạng thái P0–P8.
- `artifacts/results/dense_first/gated_members_dev_20260928/summary.json`: quality metrics ứng viên.
- `artifacts/results/dense_first/name_lookup50_nonbrand_dev_20260928/`: lookup regressions, gồm `ATM MBBank`.
- `artifacts/results/dense_first/load_gated_members100_keepalive_20260928/{manifest,summary}.json`: 12 ô closed-loop, tổng 1.536 request đo, 0 lỗi; chỉ 128 request/ô, ba lần lặp. Không đủ khẳng định error rate ≤0,1% hay p99 dài hạn.
- `artifacts/results/dense_first/load_hybrid_current100_keepalive_20260928/summary.json`: đối chứng latency cùng setup.
- `artifacts/results/dense_first/cold_entity_v2_20260928/summary.json`: stress synthetic, không phải holdout độc lập.

Tài liệu này chốt quyết định kỹ thuật và đưa ra mục tiêu nghiệm thu; không thay cấu hình runtime, không sửa số liệu benchmark lịch sử và không tự đánh dấu SLA đã đạt.
