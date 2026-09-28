# W3 — Retrieval benchmark hiện hành

Cùng model 6k dev-lock và corpus 179.209 POI. POI dev 3.600 query; brand dev 126 query/35 family; stress entity 660 query synthetic. Các tập dùng chẩn đoán/chọn cấu hình, không thay independent holdout.

| Suite | S1-A Hit@1 /10 /100 | S1-B hybrid raw Hit@1 /10 /100 |
|---|---:|---:|
| POI dev | 91,11 /97,56 /98,53% | 78,64 /95,44 /99,67% |
| Brand dev macro family | 74,39 /89,11 /94,52% | 66,34 /91,43 /99,52% |
| POI lạnh synthetic | 82,12 /90,15 /93,03% | 88,64 /98,94 /100,00% |

## Kết luận ablation

ANN raw POI dev Hit@1 91,11%; exact raw 92,00%; glue 90,78%. Hybrid current depth 100 chỉ 80,53%, với 135 rescue/516 harm so ANN. Name lookup thêm 25 rescue/0 harm POI nhưng hại brand `ATM MBBank`, nên tắt mặc định.

Brand routing/membership nâng macro Hit@1 từ ANN 57,72% lên 74,39%, 17 rescue/0 harm trên dev. Tuy nhiên S1-B coverage cao hơn; giữ pool này làm đối chứng Stage 2. Ranking không thể sửa target vắng pool.

## Serving và tốc độ

4.386 query offline replay khớp metrics. Mỗi profile S1-A/S1-B có 190/190 live query khớp count, candidate prefix 80 và top 10; debug API cắt stage ở 80. Không gọi đây là full live toàn bộ query/top100 order.

Endpoint S1-A c=4 median p95 72,25 ms/QPS 67,89; hybrid current 244,34 ms/24,86. Closed-loop 128 request/ô, ba lượt, mix 80% POI–20% brand. Chưa open-loop/soak, không cam kết 67 QPS. SLA 20 QPS/p95 150 ms là mục tiêu cần nghiệm thu.

Metrics/hash: [evidence_snapshot.json](handoff/evidence_snapshot.json). Kiểm tra: [verification_summary.json](handoff/verification_summary.json). Trace lớn local được định danh trong snapshot.
