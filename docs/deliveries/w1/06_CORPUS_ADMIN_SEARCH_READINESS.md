# Corpus/admin — mức đủ dùng cho search

Cập nhật 2026-09-28. Phạm vi đã thống nhất: clean cơ bản phục vụ search; chưa tối ưu độ đầy đủ bản đồ hoặc khôi phục mọi POI bị loại. Đánh giá dưới đây chỉ đọc dữ liệu/code, không thay corpus, qrels, geometry hoặc index.

## Quyết định

**Giữ corpus v3 và admin hiện tại để tiếp tục tối ưu search. Không rebuild/clean corpus thêm trong vòng này.** Chưa thấy lỗi liên kết dữ liệu đang làm sai candidate retrieval. Ưu tiên retrieval/ranking và đo chất lượng trên tập đang dùng.

## Kiểm tra trực tiếp

| Kiểm tra | Kết quả |
|---|---|
| Corpus | 179.209 POI ID duy nhất |
| Hash artifact corpus | 7/7 khớp manifest |
| ID order core/documents/full/access | Khớp |
| Tên giữa core/search documents; passage prefix | 0 mismatch |
| Region membership | 358.244 rows; 0 unknown POI/region, 0 duplicate pair, 0 boundary hash mismatch |
| Province đã gán | 0 unknown region, 0 thiếu geometry, 0 điểm nằm ngoài polygon đã gán |
| Subdistrict đã gán | 176 POI thiếu ID; các ID đã gán không có mismatch polygon |
| Admin geometry | 8.632 geometry, 0 invalid/empty theo Shapely; catalog 8.785 rows |
| PBF nguồn | Có local, hash khớp manifest admin |

Admin thiếu một số polygon không tự ảnh hưởng global retrieval: nhánh query-only hiện không hard-filter bằng province/subdistrict; dense/lexical lọc `destination_searchable`. Khi thêm geo/admin ranking, giữ missing bucket và global fallback. Polygon hợp lệ không chứng minh ranh giới hành chính/factual label hoàn toàn chính xác.

## Phần cần giữ ổn định để search đúng

1. Model/vector/ID map/index cùng version; tên/passage và corpus membership nhất quán.
2. Khi thiếu admin/address, không loại candidate chỉ vì metadata thiếu. Không gán missing distance =0.
3. Cleaner đã sửa và có regression: giữ riêng `12/3`, `123`, `12-3`, `12 3`; không gộp business types xung đột như bank/ATM hoặc access point được bảo vệ; dedup qua grid không còn phụ thuộc thứ tự input.
4. Loader đọc Gold active từ registry, gồm accepted positives và brand qrels; bảo vệ 2.439 Gold positive IDs và 6.889 train positive IDs khỏi drop/merge-away. Từ chối release Gold đăng ký nhưng thiếu payload. Cleaner chỉ xuất candidate vào thư mục mới, không ghi đè active corpus.
5. Artifact verifier có scope tường minh: `--scope artifacts` kiểm hash/ID/passage/migration và đạt trên 179.209 POI; mặc định `full` vẫn yêu cầu source hashes. Corpus nguồn v2 chưa có nên full provenance chưa qua, không hạ tiêu chuẩn hoặc tự tuyên bố khôi phục được.

## Kết quả sửa và phân công theo tuần

**W1 — Data quality/preparation:** quy tắc số nhà, dedup category/access point, order invariance và bảo vệ nhãn. **W5 — Offline pipeline:** source preflight, artifact/provenance verifier và entrypoint rebuild admin. Đây không phải train model hoặc ranking Stage 2.

Đã chạy **92 tests PASS**, gồm 14 regression mới cho cleaner, scope verifier và admin extractor. Artifact corpus đang phục vụ vẫn khớp hash; chưa thay corpus/index. [Pipeline và cách tái chạy W5](../w5/03_CORPUS_ADMIN_PIPELINE.md).

## Chưa cần làm

Không mở dự án chuẩn hóa toàn bộ địa chỉ/tên hành chính, hoàn thiện pickup access hoặc cứu mọi tên ngoại ngữ bị loại. Không dedup thêm chỉ vì tên giống nhau. Không tối ưu lưu trữ admin nếu chưa đo được nó nằm trên đường truy vấn và gây chậm. Giữ metadata nhẹ cần cho search; geometry/catalog đầy đủ có thể phục vụ offline.

Evidence local: `artifacts/results/corpus_admin_audit_20260928/audit.json`. Runner: [audit_corpus_admin.py](../../../tools/audit_corpus_admin.py). EDA rộng hơn: [eda/README.md](eda/README.md).
