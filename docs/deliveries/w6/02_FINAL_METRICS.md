# W6 — Bảng tổng hợp cuối phải bàn giao

[README](README.md) · Cập nhật: 2026-09-28.

| Nhóm | Baseline | Final candidate | Delta/CI | Trạng thái hiện tại |
|---|---|---|---|---|
| Retrieval Hit/coverage theo suite và slice | Baseline W2/W3 | Chưa có final | Chưa tính | Có baseline, chưa có kết quả final |
| Ranking Hit@1/10, MRR, nDCG phù hợp nhãn | Retrieval-order cùng pool | Chưa có W4 | Chưa tính | Pending |
| Geo/namespace/missing context | Baseline context đã khóa | Chưa có | Chưa tính | Pending |
| Business click/selection/booking | Cần log thật và định nghĩa | Chưa có | Chưa tính | Chưa đo, không ghi 0 |
| System latency/QPS/errors | Characterization đã đo | Cần final open-loop/soak | Chưa tính | SLA đề xuất, chưa pass |
| Fault/rebuild/rollback | Baseline bundle | Cần diễn tập | Chưa tính | Pending |

Breakdown bắt buộc: query type/length, city, head-tail, category, popularity, language, ambiguity; nếu thiếu nguồn nhãn, ghi giới hạn và phần cần thu thập. Không chỉ báo overall. Metric cùng tên phải cùng định nghĩa, mẫu số và workload mới được tính delta.
