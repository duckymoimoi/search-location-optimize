# W4 — Quy trình thực hiện đã chốt

[README](README.md) · Cập nhật: 2026-09-28.

1. Audit dữ liệu: session/impression/selection IDs, timestamp, displayed candidates, vị trí và nguồn nhãn; không dùng click chưa hiển thị như preference. Feature phải point-in-time, không đọc thống kê tương lai.
2. Đóng băng split theo thời gian/session; variant cùng case không chia ngẫu nhiên sang train/test. User/cold-start và brand family breakdown phải được ghi riêng theo protocol.
3. Dựng evaluator giữ nguyên candidate set; tách candidate miss với rank miss. So S1-A/S1-B thành hai track; không quy lợi ích đổi pool cho ranker.
4. Chạy ablation tuần tự. Nếu thiếu log hợp lệ, chỉ làm text/geo heuristic và evaluator với giới hạn rõ; Time/Behavior giữ pending. Train nặng trên Kaggle, tải model về rồi benchmark local.
5. So paired delta Hit@1/10, MRR@10, nDCG khi có graded labels; confidence interval theo case/family, cùng mẫu số. Báo same-name, brand namespace, near/far, missing-origin, cold user/POI và latency.
6. Chọn bằng dev; mở holdout một lần sau lock. Nếu sửa sau khi xem holdout, ghi bộ đó thành regression và chuẩn bị vòng kiểm định mới.
