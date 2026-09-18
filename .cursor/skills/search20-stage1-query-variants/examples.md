# Examples (gold Stage 1)

## brand_branch — Vincom / Highlands

POI: Highlands, Phường An Hải, Đà Nẵng · hn `910A` · street `Đường Ngô Quyền`

| slot | query_text | family/operator | severity | notes |
|---|---|---|---|---|
| 1 | `Highlands Ngô Quyền` | CLEAN/canonical | CLEAN | brand + street |
| 2 | `Highlands Ngo Quyen` | ORTHOGRAPHIC_IME/strip_diacritics | SINGLE | |
| 3 | `Hihglands Ngô Quyền` | MECHANICAL_TYPO/char_transpose | SINGLE | |
| 4 | `Highlands An Hải` | ALIAS/name_area | CLEAN | multi-positive nếu nhiều chi nhánh An Hải |

**Cấm:** canonical = `Highlands` (bare) với unique-target.

---

## building_code — S3.01

POI: `Tòa nhà S3.01 … Vinhomes Grand Park`

| slot | query_text | family/operator | severity |
|---|---|---|---|
| 1 | `S3.01 Vinhomes Grand Park` | CLEAN/canonical | CLEAN |
| 2 | `S3.01 Vinhomes Grand Park` → telex/partial nếu có dấu trong phần chữ | ORTHOGRAPHIC_IME/… | SINGLE |
| 3 | `S301 Vinhomes` | MECHANICAL_TYPO/char_delete (bỏ `.`) **chỉ nếu** vẫn chỉ đúng tòa — else reject | SINGLE |
| 4 | `S3.01` | ALIAS/code_short | CLEAN | **multi-positive** mọi S3.01 hợp lý / hoặc needs_review |

---

## address_street_building

POI: hn `30/48D` · street `Nguyễn Văn Linh` · Cần Thơ

| slot | query_text | family/operator | severity |
|---|---|---|---|
| 1 | `30/48D Nguyễn Văn Linh Cần Thơ` | CLEAN/canonical | CLEAN |
| 2 | `Hẻm 30/48D Nguyễn Văn Linh Cần Thơ` | ADDRESS_VARIANT/slash_normalize | SINGLE |
| 3 | `30/48D Nguyen Van Linh Can Tho` | ORTHOGRAPHIC_IME/strip_diacritics | SINGLE |
| 4 | `30 / 48D Nguyễn Văn Linh Cần Thơ` | TOKEN_EDIT/space_split | SINGLE |
| 5 | `30/48D Nguyễn Văn Linh CT` | ALIAS/abbreviation | CLEAN |
| 6 | `30/48D Nguyễn Văn Linh Cần Thow` | ORTHOGRAPHIC_IME/telex_leftover | SINGLE |

**Cấm:** gạch nối cơ học `30-48D` hoặc xóa mất thành phần số nhà.

---

## named_clear & Standalone Entity Search

POI: `Ngày của Nắng Coffee` · hn `166/9` · street `Gio An` · Đà Lạt

| slot | query_text | family/operator | severity | notes |
|---|---|---|---|---|
| 1 | `Ngày của Nắng Coffee 166/9 Gio An Đà Lạt` | CLEAN/canonical | CLEAN | canonical đầy đủ nhận diện |
| 2 | `Ngày của Nắng Coffee số 166 ngõ 9 Gio An Đà Lạt` | ADDRESS_VARIANT/slash_normalize | SINGLE | khẩu ngữ địa chỉ thực tế |
| 3 | `Ngay cua Nang Coffee 166/9 Gio An Da Lat` | ORTHOGRAPHIC_IME/strip_diacritics | SINGLE | không dấu |
| 4 | `Ngày của Nắng Coffee` | ALIAS/short_name | CLEAN | **Standalone entity search** không kèm địa chỉ |
| 5 | `Ngayf của Nắng Coffee 166/9 Gio An Đà Lạt` | ORTHOGRAPHIC_IME/telex_leftover | SINGLE | dính phím telex |
| 6 | `Ngày của Nẵng Coffee 166/9 Gio An Đà Lạt` | ORTHOGRAPHIC_IME/tone_confuse | SINGLE | nhầm dấu hỏi/ngã |

---

## category_local

Canonical phải là **tên quán**, không `quán ăn + phường`.

| OK | Reject |
|---|---|
| `Tằm café` | `quán cafe Hoàn Kiếm` (fake) |
| alias `Tằm` nếu unique trong set qrels | category-only + single-ID |

---

## Bad → fix

| Bad | Why | Fix |
|---|---|---|
| `cho tôi đến Vincom Đồng Khởi` | chat template | `Vincom Center Đồng Khởi` |
| `Vincom` unique-target | bare brand đa chi nhánh | thêm khu / multi-positive |
| `Quán ăn Thạnh Lộc` | category+area giả | dùng tên POI thật |
| `166-9 Gio An Đà Lạt` | gạch nối cơ học, phi tự nhiên | `số 166 ngõ 9 Gio An Đà Lạt` hoặc `Hẻm 166 Gio An` |
| `Cộng Cà Phê... 259-15` | tự chế đuôi số gán vào canonical không xuyệt | `Cộng Cà Phê Nguyễn Chí Thanh` |
| `Trung Cà phê Nguyên Diên Hồng` | đảo từ xé rách danh từ riêng thương hiệu | `Trung Nguyên Cà phê Diên Hồng` |
| `Converse Lê Duẩn ĐàNẵng` | dính chữ địa danh hành chính cơ học | `Converse LêDuẩn Đà Nẵng` |
| `Café Cố Nguyễn Công Trứ` | regex xóa nhầm chữ `Quận` thuộc tên quán | `Café Cố Quận Nguyễn Công Trứ` |
| lưu `S`, `S3`, `S3.`, `S3.0`, `S3.01`… vào gold | prefix dump | chỉ canonical + vài alias; prefix để bench |
