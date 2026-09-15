# Hanoi POI Search

Demo tìm kiếm và autocomplete POI cho ứng dụng đặt xe tại Hà Nội. Bản chạy chuẩn nằm trong `apps/poi-search`; corpus và bộ đánh giá dùng OSM local.

## Chạy demo

```powershell
.\apps\poi-search\scripts\start.ps1
```

- Web: http://127.0.0.1:5173
- Hybrid API: http://127.0.0.1:8000
- Dense-only API: http://127.0.0.1:8001
- Lexical-only API: http://127.0.0.1:8002

Kiểm tra nhanh:

```powershell
python apps\poi-search\bench\smoke_contract.py
```

## Cấu trúc chuẩn

| Thư mục | Vai trò |
|---|---|
| `apps/poi-search/` | FE, API, Docker Compose và benchmark runtime |
| `artifacts/` | Model release, vector dựng index và kết quả đánh giá đã chốt |
| `docs/` | Thiết kế, protocol đánh giá và tài liệu lịch sử |
| `HANOI_POI_STABLE_V1/` | Corpus OSM Hà Nội đã chuẩn hóa, 45.692 POI searchable |
| `HANOI_QUERIES_20K/hanoi_queries_20k_stable_v1/` | Dataset đánh giá Stage 1 đã khóa |
| `training/stage1/` | Mã train/eval/rebuild index còn được duy trì |
| `training/opensearch/` | Build context OpenSearch local |
| `vietnam-260910.osm.pbf` | Snapshot OSM nguồn để tái tạo corpus |

Đọc [mục lục tài liệu](docs/README.md) trước khi thay đổi corpus, model hoặc protocol đánh giá.
