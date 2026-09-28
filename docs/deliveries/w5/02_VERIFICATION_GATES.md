# W5 — Acceptance còn phải chạy

[README](README.md) · Cập nhật: 2026-09-28.

| Gate | Cách kiểm chứng | Hiện tại |
|---|---|---|
| Rebuild index | Từ bundle pin hash, tạo index cách ly, kiểm count/ID/vector space và sample parity | Chưa có biên bản final rebuild |
| Fallback thực tế | Tắt/chậm ranker, encoder, ES; kiểm route, quality, latency, error rate từng bậc | Chưa nghiệm thu đầy đủ |
| Missing origin | Không gán distance 0; có baseline không geo và test context | Có algorithm/smoke, chưa đủ quality context |
| Load/timeout | 20 QPS open-loop/soak; burst 40 QPS; 429/timeout nằm mẫu số | Pending theo SLA proposal |
| Rollback | Quay về bundle trước, kiểm version và smoke, ghi thời gian | Mục tiêu ≤15 phút chưa được đo |
| Logging | request/version/route/stage timing/error; không log PII không cần thiết | Phải audit final logs; không bắt buộc dashboard |

Khi cả dense và lexical đều phụ thuộc Elasticsearch, ES down là common dependency failure; không gọi lexical là fallback độc lập trong tình huống này. Bậc popular/nearby cần nguồn dữ liệu thực sự sẵn có hoặc phải trả lỗi/degraded rõ, không tuyên bố đã có vì xuất hiện trong sơ đồ.
