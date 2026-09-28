# corpus_audit

Các tiện ích audit dữ liệu. **Data** nằm ở `data/vietnam/`; pipeline hiện hành đặt trong `tools/`.

| Script | Việc |
|---|---|
| [`../../tools/build_clean_poi_corpus_v3.py`](../../tools/build_clean_poi_corpus_v3.py) | Clean candidate từ source tables đầy đủ, không ghi đè corpus active |
| `extract_vietnam_admin_regions.py` | Entry point tương thích tới `tools/extract_admin_regions.py` |
| [`../../tools/report_current_datasets.py`](../../tools/report_current_datasets.py) | EDA dataset hiện có |
| [`../../tools/audit_corpus_admin.py`](../../tools/audit_corpus_admin.py) | Audit corpus/admin chỉ đọc |

Output thử nghiệm dùng thư mục mới dưới `artifacts/results/`. Corpus/admin đang phục vụ giữ nguyên cho tới khi candidate được nghiệm thu.
