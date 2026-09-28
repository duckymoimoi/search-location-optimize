# W5 — Kiểm tra corpus và rebuild admin

Cập nhật 2026-09-28. Quy tắc clean/search intent thuộc [W1](../w1/06_CORPUS_ADMIN_SEARCH_READINESS.md); tài liệu này mô tả pipeline offline và verification.

## Đã hoàn thành

- Cleaner phân biệt số nhà có dấu phân cách, bảo vệ Gold/train positives và không gộp business types xung đột/access point. Candidate có version riêng; chặn ghi đè active corpus và kiểm input trước khi chạm output.
- Verifier có `full` mặc định và `artifacts` tường minh. Artifact scope kiểm hash, ID order, tên/passage, FK và migration; không gắn nhãn provenance verified.
- Entry point admin chạy qua `tools/extract_admin_regions.py`, không còn trỏ đến script thiếu. Đọc relation/way/node từ PBF, xuất catalog/geometry/preview và manifest hash vào thư mục mới.
- 92 tests PASS, trong đó 14 regression mới. Full PBF extraction đã chạy; artifact check corpus đang phục vụ PASS.

## Kết quả rebuild admin cách ly

Nguồn `vietnam-260910.osm.pbf` khớp hash manifest đang dùng. Candidate có 8.785 catalog, 8.609 geometry; 0 invalid/empty geometry, 0 FK lỗi, output hashes khớp. 166 relation thiếu member, 9 outer rings chưa khép, 1 không có outer way được ghi rõ; không tự lấp polygon thiếu hoặc nối sai biên.

Candidate chưa được kích hoạt. Admin đang dùng có 8.632 geometry; extractor mới bảo thủ hơn nên không coi đây là bản byte-identical hoặc tự thay sidecar đang dùng. Muốn activate phải so coverage và tạo lại POI memberships trên candidate, rồi đo search/geo. Đợt sửa này chỉ xác nhận rebuild entrypoint hoạt động và output được kiểm tra.

Evidence local: `artifacts/results/admin_rebuild_candidate_20260928/manifest.json` và `verification.json`. Corpus/index active không bị thay đổi.

## Lệnh vận hành

```powershell
# Kiểm tra artifact phục vụ search (không chứng nhận nguồn build)
python tools/verify_clean_poi_corpus_v3.py --scope artifacts

# Full provenance: chỉ PASS khi đúng source v2 được khôi phục
python tools/verify_clean_poi_corpus_v3.py --scope full --source PATH_TO_EXACT_V2

# Rebuild admin candidate vào thư mục mới
python tools/extract_admin_regions.py --pbf vietnam-260910.osm.pbf --output artifacts/results/admin_candidate_new

# Clean candidate: phải có đủ source tables, không dùng output active
python tools/build_clean_poi_corpus_v3.py --source PATH_TO_SOURCE --output artifacts/results/corpus_candidate_new
```

Dependencies CPU có trong `requirements-dev.txt`. Không train model ở các bước này. Source v2 còn thiếu nên chưa chứng nhận full corpus reconstruction; đây là dependency còn mở, không phải lỗi artifact corpus hiện tại. Không chạy lại cleaner trực tiếp trên active corpus để che thiếu nguồn.
