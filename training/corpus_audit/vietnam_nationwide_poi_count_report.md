# Báo cáo đếm POI/địa chỉ — PBF toàn quốc

Nguồn: `vietnam-260910.osm.pbf` (328,214,395 bytes).

Thời gian scan thực tế: **265.18 s**.
Policy: xấp xỉ intake Stage 1 trong thiết kế. **Chưa** cắt polygon Hà Nội, **chưa** dedup canonical.

## 1. Toàn bộ object trong PBF Việt Nam

| Loại | Số |
|---|---:|
| Nodes | 46,131,361 |
| Ways | 4,700,656 |
| Relations | 24,453 |
| **Tổng** | **50,856,470** |
| Nodes có ≥1 tag | 456,856 |

## 2. Sau lọc kiểu search (raw, chưa dedup)

| Lớp | Việt Nam (scan này) | Hà Nội pilot (đã khóa) |
|---|---:|---:|
| Functional | 166,815 | 32,900 |
| Functional + định danh | 123,401 | 24,277 |
| Addressable (số + phố) | 77,304 | 26,394 |
| Building có tên | 26,735 | 6,512 |
| **Searchable union** | **187,017** | **55,029** |
| Destination-like trong union | 187,017 | sau audit: **45,693** |

Tỷ lệ searchable VN / searchable HN raw ≈ **3.4×**.

## 3. Ước lượng nếu dedup theo tỷ lệ pilot HN

Pilot: 55,029 → canonical 46,792 → destination 45,693.

| Ước lượng VN | Số |
|---|---:|
| Canonical xấp xỉ | 159,023 |
| Destination searchable xấp xỉ | 155,288 |

## 4. Proxy Hà Nội bằng tag địa chỉ (không polygon)

Searchable union proxy: 15,986 — thấp hơn pilot vì nhiều POI không ghi chữ “Hà Nội” trong tag.

## 5. Kết luận

- Cả nước trong PBF ≈ **50,856,470** object bản đồ.
- Cùng kiểu lọc search → searchable raw ≈ **187,017** (trước dedup).
- Hà Nội ~55k/46k/45k là kết quả **cắt biên + lọc + dedup/audit**, đúng với thiết kế.
