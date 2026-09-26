# Target specifications

Hai tài liệu gốc [`search2.0.md`](search2.0.md) và
[`SEARCH_2.0_TONG_HOP_TASK.md`](../deliveries/SEARCH_2.0_TONG_HOP_TASK.md) được
giữ nguyên. Các contract chi tiết hiện hành:

1. [System design](SYSTEM_DESIGN.md)
2. [Technical spec](TECHNICAL_SPEC.md)
3. [Training and retrieval protocol](TRAINING_AND_RETRIEVAL_PROTOCOL.md)
4. [Shared Stage-1 evaluation suite](STAGE1_EVALUATION_SUITE.md) — Gold POI,
   brand-group và address-scope eval
5. [Gold Stage-1 v2 construction playbook](GOLD_STAGE1_V2_CONSTRUCTION_PLAYBOOK.md) —
   quy trình agent chọn 200 POI, author 800 sessions, qrels, prefix QA và lock
6. [Stage-1 evaluation schema v2](schemas/stage1_evaluation_v2.schema.json)
7. [Address and numeric fallback](ADDRESS_NUMERIC_FALLBACK.md) — conditional
   lexical routing, membership và evaluation gate
8. [Origin-aware dense](ORIGIN_AWARE_DENSE.md) — thí nghiệm Stage 1 (chưa ship)

Đây là kiến trúc đích và protocol nâng cấp. Trạng thái đã triển khai được ghi riêng tại [`as-built/CURRENT_STATE.md`](../as-built/CURRENT_STATE.md).

`contract-package-v1/` là baseline bàn giao 14/09/2026 và không tự chứa
evaluation/address extension mới. Khi triển khai extension, tạo release/schema
version mới; không sửa ngầm package v1 hoặc nhồi contract vào `app.py`.
