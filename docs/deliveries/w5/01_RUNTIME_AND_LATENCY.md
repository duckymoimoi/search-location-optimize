# W5 — Kết quả và quyết định

[README](README.md) · Cập nhật: 2026-09-28.

Dense-first endpoint ở concurrency 4 có median p95 72,25 ms/QPS 67,89; hybrid current 244,34 ms/QPS 24,86. Đây là số endpoint trên workload ngắn, không phải thời gian riêng Stage 1 hay cam kết throughput production. Không cộng percentile từng stage thành p95 tổng.

Contract + geo smoke đạt ở hybrid/current; raw profile không áp dụng geo nên không dùng nó để pass geo requirement. Giữ profile/config riêng, version phải phản ánh đúng behavior. FE build có cảnh báo chunk >500 kB; chưa có bằng chứng đây là bottleneck tương tác để tự mở tối ưu rộng.

**Observation:** endpoint hybrid current chậm hơn dense-first trong phép đo. **Hypothesis:** chi phí retrieval/fusion/ranking khác nhau. **Experiment:** bốn cấu hình endpoint, ba lượt và các concurrency đã pin. **Result:** đường cong tải đã có, không có SLA dài hạn. **Decision:** dùng profiling khi ghép ranker W4; chưa đổi runtime demo chỉ dựa vào một percentile.
