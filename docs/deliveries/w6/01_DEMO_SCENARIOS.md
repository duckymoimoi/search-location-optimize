# W6 — Tám tình huống bắt buộc

[README](README.md) · Cập nhật: 2026-09-28.

Đóng băng query, accepted target/set, origin/time/history, expected route trước buổi chạy; không chọn case sau khi thấy kết quả. Bảng dưới là checklist, chưa phải test run.

| ID | Scenario | Kỳ vọng cần định nghĩa/kiểm tra | Trạng thái final bundle |
|---|---|---|---|
| D01 | Exact query | Đúng accepted POI trong top K đã khóa; chọn/hiển thị hợp lệ | Chưa chạy |
| D02 | Partial query | Đánh giá đúng group-ready/entity-ready và ổn định khi gõ | Chưa chạy |
| D03 | Address | Giữ số nhà/mã/đường; không trả nhầm mà gọi relevant | Chưa chạy |
| D04 | Ambiguous POI/nhiều branch | Candidate đúng intent/namespace; xếp chi nhánh theo context hợp lệ | Chưa chạy |
| D05 | Typo | Biến thể giữ intent, target hợp lệ được tìm thấy | Chưa chạy |
| D06 | Cùng query, khác vị trí | Kết quả đổi hợp lý trong cohort relevant; không ép đổi nếu chỉ có một target | Chưa chạy |
| D07 | Long-tail POI | Đúng target ít phổ biến; tách candidate miss khỏi rank miss | Chưa chạy |
| D08 | Missing context/service down | Fallback/degraded/error đúng thiết kế, có latency/quality và recovery | Chưa chạy |

Mỗi lần chạy ghi timestamp, bundle IDs/hash, input, expected, actual IDs/ranks, latency, route/error và pass/fail. Build thành công hoặc smoke một query không tự thay cho toàn bộ checklist. Diễn tập lại 1–2 lần cùng bundle sau sửa lỗi.
