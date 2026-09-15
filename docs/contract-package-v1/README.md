# Contract package POI Search v1 — baseline

Bản bàn giao ngày 14/09/2026. Đây là baseline OpenAPI/schema/config đã kiểm tra cấu trúc, không phải snapshot của API đang chạy. Xem [Current state](../as-built/CURRENT_STATE.md) và [Technical spec hiện hành](../specs/TECHNICAL_SPEC.md) trước khi áp dụng; mọi thay đổi contract cần tạo version package mới thay vì sửa ngầm v1.

## Đọc và sử dụng

1. **SYSTEM_DESIGN.md**: phạm vi, scope router → Stage 1 → Stage 2, 5 sơ đồ, ETL toàn quốc, evaluation và mốc triển khai.
2. **TECHNICAL_SPEC.md**: module, dữ liệu/index, API/UI/events, timeouts, features, model integration và acceptance gates.
3. **contracts/openapi.json**: OpenAPI 3.1 để import vào editor/API tooling, tạo HTTP types và contract tests. URL localhost chỉ là server mẫu.
4. **configs/search.json**: config khởi đầu. Các giá trị radius, budgets, timeouts và SLO là giả thuyết để benchmark.
5. **contracts/features.json**, **model_bundle.schema.json**, **release.schema.json**: interface cho training và serving; không có weights/model được tạo trong gói này.
6. **contracts/examples.json**: ví dụ schema, không phải output search thực tế. **diagrams/** chứa nguồn Mermaid xuất từ tài liệu.
7. **validate_contracts.py**, **contract_validation.json**: kiểm tra OpenAPI, JSON Schema, ví dụ và giới hạn xuyên file. Chúng không thay integration/load tests của ứng dụng.

## Việc nên code trước

M0: import corpus stable v1; dựng release registry; triển khai schemas và text/feature package dùng chung; khóa dependency versions sau smoke test. M1: lexical API, query-only tab, details/exposure/select và bản đồ đường thẳng. Training có thể chạy song song sau khi chốt passage và xử lý migration nhãn.

Sau đó mở rộng ETL/corpus toàn quốc, thêm scope router + global lane và nạp encoder bundle. Chốt quality bằng exact dense trước, ANN serving sau. Stage 2 có identity/heuristic để code không bị chặn; learned ranker chỉ activate khi bàn giao bundle và report phù hợp.

## Những thứ đã khóa và những thứ cần đo

Đã khóa: ý nghĩa Stage 1/query-only và pipeline có context; giữ đường tìm rộng; ID/version; địa chỉ khác nearby context; không suy điểm đón từ centroid; N=50 mặc định; API sự kiện có exposure/idempotency; model/feature/text contract.

Cần đo trước khi tuyên bố chất lượng: corpus quốc gia bao nhiêu POI usable; cấu hình lexical/hybrid thắng; radius và global/rescue quotas; encoder mới so checkpoint cũ; lợi ích ranker contextual; ANN recall/latency/QPS. Golden context tạo sau, không dùng query mơ hồ hiện tại làm single-target gold.

Gói corpus dữ liệu **HANOI_POI_STABLE_V1.zip** đã bàn giao trước là đầu vào; không được đóng lại trong gói thiết kế này. Hệ thống cũ và checkpoint report chỉ là mốc tham khảo. Không lấy số train/eval trước đây làm kết quả cho passage/corpus mới.

Tài liệu có nguồn kỹ thuật chính thức ở SYSTEM_DESIGN.md. Những rule/config riêng của dự án được ghi là thiết kế khởi đầu. Bộ này là bản dùng cho code mới, không phải báo cáo so sánh sửa đổi tài liệu cũ.
