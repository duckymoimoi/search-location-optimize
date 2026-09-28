# Diagnostic 6k — rank regressions

Nguồn: `training/kaggle/output_stage1_v6_hardneg_6k/stage1_v6_hardneg/` `run_zero_shot_gold.jsonl` và `run_epoch2_gold.jsonl`. Đây là run Gold-gated `352867030`, không phải checkpoint dev-lock.

Query mất rank 1 so với zero-shot: **17**. q03 còn ngoài top-20 ở epoch 2: **4**.

Không sửa Gold và không chọn checkpoint từ danh sách này.

## Nhận định trên danh sách này

- 12/17 mất rank 1 là `compound`. Ba query `clean` q01 chỉ trượt trong top-5 (rank 2 hoặc 5), không rơi khỏi top-20.
- Stratum dày nhất trong 17 là `brand_branch` (7) rồi `building_code` (4). Các case brand là chi nhánh cùng chuỗi (Vincom, Cộng, MSB, Sheraton, Sacombank, Highlands), đúng kiểu sibling cạnh tranh, không phải query biến mất.
- Cụm Rainbow / Vinhomes Grand Park lặp lại: q02 S3.01/S3.02/S3.05 chỉ tụt xuống rank 2–3; q03 của S3.01 và S3.02 vẫn ngoài top-20 dù hạng có nhích (133→109, 65→59).
- Bốn q03 miss@20 không nằm trong 17 mất rank 1. Zero-shot của chúng đã không ở rank 1. `g150-132-q03` là case xấu đi rõ (5→48). `g150-029-q03` cải thiện mạnh (ngoài top-1000 → 26) nhưng vẫn miss@20.

## Mất rank 1

- `g150-066-q01` q01 / address_street_building / clean: zs 1 → e2 2. Ngày của Nắng → Ngày của Nắng Coffee+ (166/9 hẻm14, Gio An, Phường Cam Ly - Đà Lạt, Tỉnh Lâm Đồng)
- `g150-178-q01` q01 / brand_branch / clean: zs 1 → e2 5. Vincom Huế → Vincom Plaza Huế (50A, Hùng Vương, Phường Thuận Hoá, Thành phố Huế)
- `g150-113-q01` q01 / explicit_area_cross_region / clean: zs 1 → e2 5. Nhà sách Ngọc Anh → Ngọc anh (24a, Hiệp Bình, Phường Hiệp Bình, Thành phố Hồ Chí Minh)
- `g150-151-q02` q02 / building_code / compound: zs 1 → e2 2. S3 01 Rianbow Grnad Park → Tòa nhà S3.01 phân khu Rainbow đại đô thị Vinhomes Grand Park (512 Nguyễn Xiển, Đường Cầu Vồng 3, Phường Long Bình, Thành phố Hồ Chí Minh)
- `g150-152-q02` q02 / building_code / compound: zs 1 → e2 2. S3 02 Raibnow Grand Pak → Tòa nhà S3.02 phân khu Rainbow đại đô thị Vinhomes Grand Park (512 Nguyễn Xiển, Đường Cầu Vồng 3, Phường Long Bình, Thành phố Hồ Chí Minh)
- `g150-159-q02` q02 / building_code / compound: zs 1 → e2 3. S3 05 Vinhmoes Gran Park → Tòa nhà S3.05 phân khu Rainbow đại đô thị Vinhomes Grand Park (512 Nguyễn Xiển, Đường Cầu Vồng, Phường Long Bình, Thành phố Hồ Chí Minh)
- `g150-083-q03` q03 / address_street_building / compound: zs 1 → e2 8. 296 Nhu Nguyêjt Vũ Ninh Bắc Ninh → 296, Đường Như Nguyệt (296, Đường Như Nguyệt, Phường Vũ Ninh, Thành phố Bắc Ninh)
- `g150-010-q03` q03 / brand_branch / challenge: zs 1 → e2 7. Công cafe Nguyên Chí Thanh → Cộng Cà Phê (259/15, Nguyễn Chí Thanh, Phường Hải Châu, Thành phố Đà Nẵng)
- `g150-014-q03` q03 / brand_branch / compound: zs 1 → e2 8. MSV ngo gia tu bac ninh → MSB (274-276, Đường Ngô Gia Tự, Phường Kinh Bắc, Thành phố Bắc Ninh)
- `g150-178-q03` q03 / brand_branch / compound: zs 1 → e2 2. VincomHuế Hùng Vuong → Vincom Plaza Huế (50A, Hùng Vương, Phường Thuận Hoá, Thành phố Huế)
- `g150-156-q03` q03 / building_code / compound: zs 1 → e2 2. 18T2 Le Van Lương → 18T2 Trung Hòa Nhân Chính (44, đường Lê Văn Lương, Phường Yên Hòa, Hà Nội)
- `g150-143-q03` q03 / code_transit_landmark / compound: zs 1 → e2 2. Nhàdát vang đường số 6 Cần Thơ → NHÀ DÁT VÀNG CẦN THƠ (18, Đường số 6, Phường Tân An, Thành phố Cần Thơ)
- `g150-114-q03` q03 / explicit_area_cross_region / compound: zs 1 → e2 2. THCS Chuv Văn An Lê Dinh Lý Đà Nẵng → Trường Trung học cơ sở Chu Văn An (70, Đường Lê Đình Lý, Phường Thanh Khê, Thành phố Đà Nẵng)
- `g150-057-q03` q03 / named_clear / compound: zs 1 → e2 15. Trường cấp 2 Nguyên An Khương Lê Thị Hồng Gấm → Trường Trung học cơ sở Nguyễn An Khương (66/6, Lê Thị Hồng Gấm, Xã Hóc Môn, Thành phố Hồ Chí Minh)
- `g150-007-q04` q04 / brand_branch / compound: zs 1 → e2 4. Sheratn Trần Phú Nha Trng → Sheraton Nha Trang Hotel & Spa (26-28, Đường Trần Phú, Phường Nha Trang, Khánh Hòa)
- `g150-019-q04` q04 / brand_branch / compound: zs 1 → e2 3. Sacombnk đường 3 thang 2 Cần Tho → Sacombank (160, Đường 3 Tháng 2, Phường Tân An, Thành phố Cần Thơ)
- `g150-025-q04` q04 / brand_branch / compound: zs 1 → e2 5. HighlandsCoffe Ngô Quyên Đà Nẵng → Highlands Coffee (910A, Đường Ngô Quyền, Phường An Hải, Thành phố Đà Nẵng)

## q03 miss@20 ở epoch 2

- `g150-151-q03` q03 / building_code / compound: zs 133 → e2 109. S3 01 Nguyêxn Xien → Tòa nhà S3.01 phân khu Rainbow đại đô thị Vinhomes Grand Park (512 Nguyễn Xiển, Đường Cầu Vồng 3, Phường Long Bình, Thành phố Hồ Chí Minh)
- `g150-152-q03` q03 / building_code / compound: zs 65 → e2 59. S3 02 Nguyen Xieen → Tòa nhà S3.02 phân khu Rainbow đại đô thị Vinhomes Grand Park (512 Nguyễn Xiển, Đường Cầu Vồng 3, Phường Long Bình, Thành phố Hồ Chí Minh)
- `g150-132-q03` q03 / explicit_area_cross_region / compound: zs 5 → e2 48. TuấnThảo Nguyễn Dình Chiểu Mũi Né → tuấn thảo (45D, Nguyễn Đình Chiểu, Phường Mũi Né, Tỉnh Lâm Đồng)
- `g150-029-q03` q03 / named_clear / compound: zs 1001 → e2 26. Truogn Khương Ha → Trường Tiểu học - Trung học cơ sở - Trung học phổ thông Khương Hạ (31, Phố Khương Hạ, Phường Khương Đình, Hà Nội)
