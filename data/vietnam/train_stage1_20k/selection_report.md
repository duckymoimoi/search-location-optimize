# SEARCH 2.0 — Training POI Selection Report (20,000 Target POIs)

> Historical selection snapshot before corpus-v2 migration. The active target
> files now contain **19,939 POIs**: 46 removed duplicate IDs and 15 POIs in
> Gold's acceptable-ID sets were deleted, with no replacements. Current counts
> and hashes are in `manifest.json`; individual removals are in
> `corpus_v2_removal_audit.json`. All 500 POIs in the locked query checkpoint
> remain in the active pool. The tables below document the original 20,000-POI
> sampling design, not the current distribution.

## 1. Tổng quan

- **Tổng số POI mục tiêu**: **20,000**
- **Tập đối chuẩn bị loại bỏ (Gold Stage-1 isolation)**: **180 POIs** (Zero leakage: 0 trùng)
- **Phạm vi địa lý**: **34 tỉnh/thành** trên cả 3 miền
- **Tỷ lệ có số nhà & đường đầy đủ**: **72.29% (14,458 POIs)**
- **Tỷ lệ `destination_searchable`**: **100.0%**

## 2. Phân bố 7 Sampling Strata

| Stratum | Số lượng | Tỷ lệ (%) | Mục tiêu huấn luyện |
| :--- | ---: | ---: | :--- |
| `brand_branch` | 4,000 | 20.00% | Học phân biệt chi nhánh cùng thương hiệu bằng đường / khu vực |
| `named_clear` | 4,000 | 20.00% | Học trích xuất thực thể tên riêng độc lập (standalone) |
| `address_street_building` | 3,200 | 16.00% | Học phân tích số nhà, ngõ/ngách/hẻm/kiệt phức tạp |
| `building_code` | 2,400 | 12.00% | Học nhận diện mã tòa, tháp, block chung cư |
| `category_local` | 2,200 | 11.00% | Học xử lý quán ăn, dịch vụ địa phương kết hợp tên người |
| `explicit_area_cross_region` | 2,200 | 11.00% | Học disambiguation thực thể trùng tên đa tỉnh thành |
| `code_transit_landmark` | 2,000 | 10.00% | Học định vị bến bãi, di tích, tôn giáo, danh lam |
| **Tổng** | **20,000** | **100.0%** | |

## 3. Phân bố 3 Miền Toàn Quốc

| Vùng miền | Số lượng | Tỷ lệ (%) | Tỉnh/thành tiêu biểu |
| :--- | ---: | ---: | :--- |
| **North** | 7,000 | 35.00% | Hà Nội, Thành phố Bắc Ninh, Thành phố Hải Phòng, Tỉnh Ninh Bình |
| **South** | 7,000 | 35.00% | Thành phố Hồ Chí Minh, Thành phố Cần Thơ, Thành phố Đồng Nai, Tỉnh An Giang |
| **Central** | 6,000 | 30.00% | Thành phố Đà Nẵng, Tỉnh Lâm Đồng, Khánh Hòa, Thành phố Huế |
| **Tổng** | **20,000** | **100.0%** | |

## 4. Phân bố chi tiết theo Tỉnh/Thành

| Tỉnh / Thành phố | Vùng miền | Số lượng POI | Tỷ lệ (%) |
| :--- | :--- | ---: | ---: |
| Thành phố Hồ Chí Minh | South | 5,831 | 29.15% |
| Hà Nội | North | 4,176 | 20.88% |
| Thành phố Đà Nẵng | Central | 2,500 | 12.50% |
| Thành phố Bắc Ninh | North | 1,626 | 8.13% |
| Tỉnh Lâm Đồng | Central | 967 | 4.83% |
| Khánh Hòa | Central | 596 | 2.98% |
| Thành phố Huế | Central | 437 | 2.19% |
| Thành phố Cần Thơ | South | 398 | 1.99% |
| Thành phố Hải Phòng | North | 340 | 1.70% |
| Tỉnh Gia Lai | Central | 332 | 1.66% |
| Tỉnh Quảng Trị | Central | 313 | 1.57% |
| Tỉnh Đắk Lắk | Central | 308 | 1.54% |
| Thành phố Đồng Nai | South | 251 | 1.26% |
| Tỉnh Ninh Bình | North | 209 | 1.04% |
| Tỉnh Quảng Ngãi | Central | 160 | 0.80% |
| Tỉnh Nghệ An | Central | 159 | 0.80% |
| Tỉnh An Giang | South | 155 | 0.78% |
| Tỉnh Thanh Hóa | Central | 135 | 0.68% |
| Thành phố Quảng Ninh | North | 125 | 0.62% |
| Tỉnh Đồng Tháp | South | 118 | 0.59% |
| Tỉnh Hưng Yên | North | 112 | 0.56% |
| Tỉnh Lào Cai | North | 111 | 0.56% |
| Tỉnh Tây Ninh | South | 106 | 0.53% |
| Tỉnh Vĩnh Long | South | 102 | 0.51% |
| Tỉnh Tuyên Quang | North | 97 | 0.48% |
| Hà Tĩnh | Central | 93 | 0.46% |
| Tỉnh Phú Thọ | North | 58 | 0.29% |
| Tỉnh Thái Nguyên | North | 41 | 0.21% |
| Tỉnh Cà Mau | South | 39 | 0.19% |
| Tỉnh Lạng Sơn | North | 30 | 0.15% |
| Tỉnh Lai Châu | North | 26 | 0.13% |
| Tỉnh Cao Bằng | North | 21 | 0.10% |
| Tỉnh Sơn La | North | 14 | 0.07% |
| Tỉnh Điện Biên | North | 14 | 0.07% |
