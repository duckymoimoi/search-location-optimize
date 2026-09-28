# W6 — Nghiệm thu demo và báo cáo cuối

Cập nhật: 2026-09-28. **Chưa nghiệm thu cuối.** Người chạy, người nhận và người duyệt final demo: chưa xác nhận. Yêu cầu: W6 [kế hoạch](../SEARCH_2.0_TONG_HOP_TASK.md), bước 6 [SEARCH 2.0](../../specs/search2.0.md).

## 1. Mục tiêu và input

Chứng minh demo chạy xuyên suốt, ổn định và tái hiện được trên một final bundle. Input cần W5 đã có ranking W4, measured fallback/latency và quy trình rollback. Hiện mới có scaffold và Stage 1 verified; không có final ranking candidate để nghiệm thu W6.

## 2. Tám tình huống bắt buộc

[Tám tình huống bắt buộc](01_DEMO_SCENARIOS.md)

## 3. Bảng tổng hợp cuối phải bàn giao

[Bảng tổng hợp cuối phải bàn giao](02_FINAL_METRICS.md)

## 4. Tối ưu theo evidence

Chỉ thử cache/FP16/batching/candidate budget khi profiling cho thấy vấn đề. Một experiment phải có bottleneck đo được, giả thuyết, cấu hình trước/sau, quality guard và latency mới. Không giảm N để đạt tốc độ rồi bỏ qua candidate coverage, đặc biệt POI lạnh/brand. Chỉ cần log latency/lỗi đủ kiểm tra; không bắt buộc dựng dashboard.

## 5. Điều kiện đóng tuần và bàn giao cuối

- W4 model/ablation và W5 integration/fallback/rebuild đã qua gate đúng scope.
- Tám scenario có evidence final bundle, kết quả tái lập và lỗi mở được ghi rõ.
- Technical report có protocol, baseline vs final, per-segment, failure taxonomy, quyết định giữ/bỏ feature và giới hạn dữ liệu/SLA.
- Bundle/config/hash, mã nguồn, dependency versions, artifact retrieval instructions và rollback record đầy đủ; secrets/model lớn không nằm trong source release.
- Người nhận/duyệt xác nhận verdict và scope. Hiện chưa có xác nhận này; đây là checklist để nghiệm thu, không phải biên bản pass.

Integration + người nghiệm thu phụ trách G6. Nếu chỉ demo nghiên cứu với dữ liệu/context giả lập thì phải ghi phạm vi đó, không gọi là personalization đã được chứng minh trên người dùng thật.
