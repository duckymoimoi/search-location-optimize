# Tài liệu dự án

Tài liệu tách theo mục đích: trạng thái hiện tại vs thiết kế đích vs evidence tuần.

## 1. Đang chạy / evidence

- [Current state](as-built/CURRENT_STATE.md)
- [Nationwide corpus direction](as-built/NATIONWIDE_CORPUS_DIRECTION.md)
- [W1 evidence](deliveries/w1_evidence/README.md) — problem statement · EDA · taxonomy · DQ
- [Tổng hợp task W1–W6](deliveries/SEARCH_2.0_TONG_HOP_TASK.md)
- Runtime FE/API: [`apps/poi-search/README.md`](../apps/poi-search/README.md)

## 2. Kiến trúc & Stage 1

- [SEARCH 2.0 vision](specs/search2.0.md)
- [Stage 1 model selection protocol](specs/SEARCH_2.0_STAGE1_MODEL_SELECTION_PROTOCOL.md)
- [Query variant standard](specs/SEARCH_2.0_STAGE1_QUERY_VARIANT_STANDARD.md)
- [Skill: viết Stage-1 variants](../.cursor/skills/search20-stage1-query-variants/SKILL.md)
- [Query variant rules v5](specs/SEARCH_2_0_QUERY_VARIANT_GENERATION_RULES_V5.md) (chi tiết)
- [System design](specs/SYSTEM_DESIGN.md) · [Technical spec](specs/TECHNICAL_SPEC.md)

## 3. Dữ liệu (SoT)

- [Data README](../data/README.md)
- [`vn-poi-core-v1`](../data/vietnam/poi_corpus_v1/) — corpus toàn quốc ~186k
- [`admin_regions_v1`](../data/vietnam/admin_regions_v1/)
- [`gold_stage1_v1`](../data/vietnam/gold_stage1_v1/) — **180 POI · 1,080 queries locked**

## 4. Khác

- [Contract package v1](contract-package-v1/README.md)
- [Research](research/README.md)
- [Operations / structure](operations/PROJECT_STRUCTURE.md)

> Legacy Hanoi (`HANOI_POI_STABLE_V1`, `HANOI_QUERIES_20K`) và pilot-110 đã gỡ khỏi repo (2026-09-18).
