# As-built

- [Current state](CURRENT_STATE.md): phiên bản, luồng đang chạy và gap với kiến trúc đích.
- [Lexical search](LEXICAL_SEARCH.md): nhánh ES lexical đang chạy (policy v12) — chuẩn hóa, field, DSL, núm boost.
- [Nationwide corpus direction](NATIONWIDE_CORPUS_DIRECTION.md): corpus toàn quốc và lineage.
- [Diagnostic negatives/geo plan](DIAGNOSTIC_NEGATIVES_GEO_PLAN.md): audit/plan theo snapshot ghi trong file.
- Kết quả Stage 1 W1 nằm trong [`../deliveries/w1/`](../deliveries/w1/README.md), đặc biệt model catalog và lexical reports.

Số liệu trong báo cáo đánh giá gắn với snapshot được ghi trong báo cáo; không mặc định áp dụng cho code mới hơn.

Address/numeric fallback vẫn là target contract tại
[`../specs/ADDRESS_NUMERIC_FALLBACK.md`](../specs/ADDRESS_NUMERIC_FALLBACK.md).

Gold hiện hành: `gold_stage1_v2_1` và `gold_stage1_brand_v1` trong
`data/vietnam/stage1_eval_suite_v2/`. Contract:
[`../specs/STAGE1_EVALUATION_SUITE.md`](../specs/STAGE1_EVALUATION_SUITE.md).
