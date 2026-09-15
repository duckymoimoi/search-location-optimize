# Tài liệu dự án

Tài liệu được tách theo mục đích để tránh trộn trạng thái hiện tại với thiết kế tương lai.

## 1. Đang chạy — đọc trước

- [Current state](as-built/CURRENT_STATE.md): phiên bản, luồng code thực tế và gap cần xử lý.
- [Stage 1 evaluation](as-built/STAGE1_EVALUATION.md): bằng chứng lexical/dense/hybrid, ANN, typing và latency theo snapshot.
- [Runtime product](../apps/poi-search/README.md): cách chạy FE/API/Docker và smoke test.

## 2. Kiến trúc đích

- [System design](specs/SYSTEM_DESIGN.md)
- [Technical spec](specs/TECHNICAL_SPEC.md)
- [Training and retrieval protocol](specs/TRAINING_AND_RETRIEVAL_PROTOCOL.md)

Các tài liệu này mô tả hướng xây dựng. Một mục chỉ trở thành “đã triển khai” khi xuất hiện trong current state và có version/test tương ứng.

## 3. Contract và nghiên cứu

- [Contract package v1](contract-package-v1/README.md): OpenAPI, JSON Schema, config baseline, validation và Mermaid diagrams.
- [Research and pilot history](research/README.md): rationale, bài báo, tech stack và thiết kế pilot v3.

## 4. Dữ liệu, artifact và vận hành

- [Project structure and lifecycle](operations/PROJECT_STRUCTURE.md)
- [Corpus schema/lineage](../HANOI_POI_STABLE_V1/hanoi_poi_stable_v1/README.md)
- [Evaluation dataset manifest](../HANOI_QUERIES_20K/hanoi_queries_20k_stable_v1/manifest.json)
- [Artifact inventory](../artifacts/README.md)

Thứ tự xử lý mâu thuẫn: manifest/runtime code → `as-built/` → `specs/` → `research/`. Contract package v1 là baseline riêng; không mặc định đồng nhất với OpenAPI sinh từ FastAPI hiện tại.
