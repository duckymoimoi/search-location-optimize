# Tài liệu dự án

Tài liệu tách theo mục đích: trạng thái hiện tại vs thiết kế đích vs evidence tuần.

GitHub và local chỉ giữ **một bộ tài liệu/data hiện hành**. Bản cũ nằm trong git history.

## Thứ tự nguồn sự thật

1. [`specs/search2.0.md`](specs/search2.0.md) và
   [`deliveries/SEARCH_2.0_TONG_HOP_TASK.md`](deliveries/SEARCH_2.0_TONG_HOP_TASK.md)
   là hai tài liệu gốc, được giữ nguyên.
2. `specs/` chứa contract đích hiện hành. Stage 1 eval:
   [`STAGE1_EVALUATION_SUITE.md`](specs/STAGE1_EVALUATION_SUITE.md). Số nhà/mã:
   [`ADDRESS_NUMERIC_FALLBACK.md`](specs/ADDRESS_NUMERIC_FALLBACK.md).
3. `as-built/` mô tả phần thực sự đã chạy; một thiết kế trong `specs/` không tự
   trở thành tính năng runtime.
4. `deliveries/w1_evidence/`, `research/` và `contract-package-v1/` là evidence
   hoặc baseline theo snapshot. Không sửa số liệu lịch sử để khớp runtime mới.

## 1. Đang chạy / evidence

- [Current state](as-built/CURRENT_STATE.md)
- [Nationwide corpus direction](as-built/NATIONWIDE_CORPUS_DIRECTION.md)
- [W1 evidence](deliveries/w1_evidence/README.md)
- [Tổng hợp task W1–W6](deliveries/SEARCH_2.0_TONG_HOP_TASK.md)
- Runtime FE/API: [`apps/poi-search/README.md`](../apps/poi-search/README.md)

## 2. Kiến trúc & Stage 1

- [SEARCH 2.0 vision](specs/search2.0.md)
- [Stage 1 model selection protocol](specs/SEARCH_2.0_STAGE1_MODEL_SELECTION_PROTOCOL.md)
- [Query variant standard](specs/SEARCH_2.0_STAGE1_QUERY_VARIANT_STANDARD.md)
- [Skill: viết Stage-1 variants](../.cursor/skills/search20-stage1-query-variants/SKILL.md)
- [Skill: brand queries](../.cursor/skills/search20-stage1-brand-queries/SKILL.md)
- [Shared Stage-1 evaluation suite](specs/STAGE1_EVALUATION_SUITE.md) ·
  [schema v2](specs/schemas/stage1_evaluation_v2.schema.json)
- [Address/number lexical fallback contract](specs/ADDRESS_NUMERIC_FALLBACK.md)
- [System design](SYSTEM_DESIGN.md) · [Technical spec](TECHNICAL_SPEC.md)

## 3. Dữ liệu (SoT)

- [Data README](../data/README.md)
- [`poi_corpus_v3`](../data/vietnam/poi_corpus_v3/README.md) — corpus demo 179.209 POI
- [`admin_regions_v1`](../data/vietnam/admin_regions_v1/)
- [`gold_stage1_v2_1`](../data/vietnam/stage1_eval_suite_v2/gold_stage1_v2_1/) — Gold POI/entity
- [`gold_stage1_brand_v1`](../data/vietnam/stage1_eval_suite_v2/gold_stage1_brand_v1/) — Gold brand
- [`train_stage1_brand_membership_v3`](../data/vietnam/train_stage1_brand_membership_v3/)
- [`train_stage1_queries_v6`](../data/vietnam/train_stage1_queries_v6/) — query POI compile hiện hành

## 4. Khác

- [Contract package v1](contract-package-v1/README.md)
- [Research](research/README.md)
- [Operations / structure](operations/PROJECT_STRUCTURE.md)
