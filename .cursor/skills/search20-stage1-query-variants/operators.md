# Stage-1 train operator contract

Đây là taxonomy duy nhất cho sáu slot `manual_authored_v6`. Chỉ dùng operator
và tag trong tài liệu này; không đặt tag mới trong lúc author.

## Source và identity

- Target row đã khóa là source of truth; corpus chỉ bổ sung fact không mâu thuẫn.
- v01 phải chứa official `name` như một contiguous span, chỉ được khác
  casing/whitespace.
- Mọi biến thể phải truy ngược được về v01 hoặc v02 bằng đúng operator đã tag.
- Digit, letter suffix, ref, building code và ordered address components là bất
  biến, trừ một contract địa chỉ mô tả rõ cách biểu diễn tương đương.
- Descriptor chỉ được dùng khi category xác nhận; không suy ra specialty.

| Category | Descriptor rộng được phép | Không được suy ra |
|---|---|---|
| `amenity=restaurant` | `nhà hàng`, `quán ăn` | món ăn cụ thể |
| `amenity=cafe` | `cà phê`, `quán cà phê` | bar/restaurant |
| `amenity=fuel` | `cây xăng`, `trạm xăng` | branch/địa danh ngoài source |
| `amenity=bank` | `ngân hàng` | `phòng giao dịch`, `chi nhánh` chưa xác nhận |
| `tourism=hotel` | `khách sạn` | `homestay`, `resort` |
| `amenity=school` | `trường` | cấp học khác source |
| `amenity=hospital` | `bệnh viện` | chuyên khoa cụ thể |

## Slot contract

### v01 — canonical

```text
family=CLEAN
operator=canonical
subtype=canonical_anchor
severity=CLEAN
```

Giữ official name và discriminator tối thiểu. Không nối toàn bộ địa chỉ hành
chính khi tên đã đủ unique. Brand nhiều branch không được dùng bare brand.

### v02 — natural identity core

```text
family=ALIAS
operator=short_name
subtype=standalone_or_natural_address
severity=CLEAN
```

- named POI: standalone name hoặc verified name fragment đủ nhận diện;
- brand branch: brand + street/area/số/ref tối thiểu;
- address-only: housenumber + street;
- building/transit: code/ref/name + namespace cần thiết;
- cross-region collision: name + area tối thiểu.

Bỏ context label không mang identity nếu qrels vẫn đầy đủ. Không respell proper
name. Không dùng dấu `.`; compact abbreviation/code chỉ khi bảo toàn ordered
alphanumeric sequence.

### v03–v06 — controlled coverage

```text
family=COMPOUND
operator=controlled_compound
subtype={2-3 compatible tags}
severity=COMPOUND
```

Mỗi row có 2–4 mutation points, dùng tag set riêng và làm biến đổi identity hoặc
discriminator. Ít nhất một mutation cục bộ nằm ở token chữ đầu tiên sau mọi
number/code bất biến. Full-strip toàn câu hoặc token-order đơn độc không thỏa
điều kiện này. Giữ skeleton đủ nhận dạng; không ép số lượng lỗi khi intent trở
thành rác.

## Controlled variation whitelist

Field vẫn tên `error_tags`, nhưng tag có thể là lỗi gõ hoặc biến thể bề mặt có
giá trị retrieval.

| Tag | Biến đổi | Điều kiện |
|---|---|---|
| `partial_diacritic_drop` | bỏ dấu ở một phần query | không biến thành full strip |
| `full_diacritic_strip` | bỏ toàn bộ dấu Việt, `đ→d` | coverage phụ; không tự đủ độ khó |
| `phonetic_confusion` | nhầm onset/coda/thanh trên một âm tiết | giữ skeleton, không thành entity khác |
| `mechanical_typo` | delete/insert/substitute/transpose/adjacent-key/double-tap | mỗi span một slip; không sửa digit/ref/code |
| `ime_telex_residual` | còn một phím kết Telex/VNI ở một âm tiết | form gốc vẫn đọc ra được |
| `raw_ime_sequence` | một cụm còn dạng Telex hoặc VNI chưa convert | dùng quy tắc bộ gõ thật, không thêm ký tự ngẫu nhiên |
| `orthographic_equivalent` | cách viết tiếng Việt tương đương đã xác minh | cần mapping/evidence; không respell proper name tùy ý |
| `token_boundary_error` | mất hoặc thừa một ranh giới whitespace | giữ nguyên ký tự và thứ tự; tối đa một boundary trong một realization |
| `token_order_variant` | đổi thứ tự token/khối đã có | không xé span proper name bất khả phân |
| `verified_name_fragment` | dùng đoạn giữa/cuối tên đủ nhận diện | collision check và qrels lại; không lấy fragment generic |
| `safe_omission` | bỏ một cụm không mang identity | không bỏ digit/ref/code/discriminator bắt buộc |
| `space_punct_variant` | spacing/punctuation không mang identity | không dùng thay cho token merge; không phá `/`, `+`, hyphen/apostrophe identity |
| `slash_address_spoken` | đọc `/` thành số/ngõ/ngách/hẻm/kiệt | giữ mọi digit/suffix và thứ tự; cần evidence vùng/cấu trúc |
| `full_address_paste` | form địa chỉ đầy đủ như được dán từ tin nhắn | chỉ dùng component có trong source, punctuation tự nhiên |
| `acronym_case` | `THCS↔thcs`, `ATM↔atm` | chỉ dùng nếu encoder nhìn thấy casing |
| `acronym_expand_contract` | acronym ↔ cụm đầy đủ theo mapping | source/category xác nhận nghĩa |
| `administrative_abbrev` | `phường↔p`, `quận↔q`, `xã↔x`, `huyện↔h`, `thành phố↔tp` | component phải có trong parent |
| `regional_abbrev` | `Hà Nội↔hn`, `TP HCM↔hcm/tphcm`, `Hải Phòng↔hp` | chỉ mapping allowlist |
| `verified_descriptor_variant` | descriptor/alias rộng được source xác nhận | không đổi loại hình/specialty |

### Token boundary

`token_boundary_error` mô phỏng gõ nhanh, không phải phép nối tùy ý:

```text
Bách Hóa Xanh → BáchHóa Xanh
Nguyễn Trãi → NguyễnTrãi
Highlands → High lands
23 Nguyễn Trãi → 23Nguyễn Trãi
```

Cho phép trên name, brand, street hoặc đúng boundary giữa housenumber và street.
Không merge toàn query, không merge qua `/`, `+`, hyphen/apostrophe, không tách
code/ref thành ký tự rời và không làm đổi bất kỳ ký tự nào ngoài whitespace.
Các dạng `HàNội`, `ĐàNẵng`, `CầnThơ` chỉ dùng khi chính boundary đó là phần query
người dùng có thể gõ và row vẫn giữ đủ anchor; không tạo chúng như công thức cho
admin token phụ.

### Raw Telex/VNI

`raw_ime_sequence` có thể tác động một hoặc nhiều âm tiết liền nhau:

```text
cửa hàng mỹ phẩm → cuwar hafng myx phaamr
phở bò nam định → pho73 bo2 nam dinh5
```

Chỉ dùng chuỗi sinh đúng quy tắc Telex/VNI. Không trộn hai hệ bộ gõ trong cùng
một span. Partial conversion được phép khi phản ánh một phiên gõ có phần đã
convert, phần còn raw.

### Orthographic equivalent

Chỉ dùng mapping được duyệt, ví dụ `Lý↔Lí`, `hòa↔hoà`, `Thúy↔Thuý`. Với proper
name, phải có alias/equivalence evidence; không dùng quy tắc ngôn ngữ chung để
tự sửa official spelling.

### Acronym mapping

```text
THCS ↔ trung học cơ sở     THPT ↔ trung học phổ thông
cấp 1 ↔ tiểu học           cấp 2 ↔ trung học cơ sở
cấp 3 ↔ trung học phổ thông
ĐH/DH ↔ đại học            CĐ ↔ cao đẳng
BV ↔ bệnh viện             BVĐK ↔ bệnh viện đa khoa
TTYT ↔ trung tâm y tế      KS ↔ khách sạn
QL ↔ quốc lộ               UBND ↔ Ủy ban nhân dân
HĐND ↔ Hội đồng nhân dân   KCN ↔ khu công nghiệp
KĐT ↔ khu đô thị           KTX ↔ ký túc xá
TTTM ↔ trung tâm thương mại
PCCC ↔ phòng cháy chữa cháy
CLB ↔ câu lạc bộ           TDTT ↔ thể dục thể thao
TNHH ↔ trách nhiệm hữu hạn
CHXD ↔ cửa hàng xăng dầu
```

Không mở initials của brand/proper name. Token mơ hồ như `TH`, `TT`, `CN`, `ĐT`,
`ATM`, `PGD` chỉ được dùng khi toàn cụm trong source khóa đúng nghĩa.

### Slash-address spoken

```text
30/48D Nguyễn Văn Linh → Số 30 hẻm 48D Nguyễn Văn Linh
24/19 Trần Quang Diệu → Số 24 ngõ 19 Trần Quang Diệu
48/34/143 Nguyễn Chính → Số 48 ngách 34 ngõ 143 Nguyễn Chính
```

Chọn `ngõ/ngách`, `hẻm`, `kiệt/K` theo region và evidence. Không chắc thì giữ
slash. Cấm đổi `48D` thành `49D`, bỏ tầng địa chỉ, đổi thứ tự hoặc tạo dạng
`30-48D`/`3048D`.

## Compatible pairs

Với tag set ba phần, mọi cặp con đều phải có trong allowlist:

```text
mechanical_typo + full_diacritic_strip
mechanical_typo + partial_diacritic_drop
mechanical_typo + phonetic_confusion
mechanical_typo + ime_telex_residual
mechanical_typo + raw_ime_sequence
mechanical_typo + orthographic_equivalent
mechanical_typo + token_boundary_error
mechanical_typo + token_order_variant
mechanical_typo + verified_name_fragment
mechanical_typo + safe_omission
mechanical_typo + space_punct_variant
mechanical_typo + slash_address_spoken
mechanical_typo + full_address_paste
mechanical_typo + acronym_case
mechanical_typo + acronym_expand_contract
mechanical_typo + verified_descriptor_variant
partial_diacritic_drop + phonetic_confusion
partial_diacritic_drop + ime_telex_residual
partial_diacritic_drop + token_boundary_error
partial_diacritic_drop + token_order_variant
partial_diacritic_drop + verified_name_fragment
partial_diacritic_drop + safe_omission
partial_diacritic_drop + slash_address_spoken
partial_diacritic_drop + full_address_paste
partial_diacritic_drop + administrative_abbrev
full_address_paste + administrative_abbrev
full_diacritic_strip + token_boundary_error
full_diacritic_strip + token_order_variant
full_diacritic_strip + verified_name_fragment
full_diacritic_strip + safe_omission
full_diacritic_strip + space_punct_variant
full_diacritic_strip + slash_address_spoken
full_diacritic_strip + full_address_paste
full_diacritic_strip + administrative_abbrev
full_diacritic_strip + regional_abbrev
phonetic_confusion + ime_telex_residual
phonetic_confusion + token_boundary_error
phonetic_confusion + token_order_variant
phonetic_confusion + verified_name_fragment
phonetic_confusion + safe_omission
phonetic_confusion + space_punct_variant
phonetic_confusion + verified_descriptor_variant
ime_telex_residual + token_boundary_error
ime_telex_residual + token_order_variant
ime_telex_residual + safe_omission
ime_telex_residual + space_punct_variant
raw_ime_sequence + token_boundary_error
raw_ime_sequence + verified_name_fragment
raw_ime_sequence + safe_omission
orthographic_equivalent + token_boundary_error
orthographic_equivalent + safe_omission
token_boundary_error + token_order_variant
token_boundary_error + verified_name_fragment
token_boundary_error + safe_omission
token_order_variant + safe_omission
space_punct_variant + token_order_variant
space_punct_variant + safe_omission
slash_address_spoken + regional_abbrev
acronym_expand_contract + regional_abbrev
verified_descriptor_variant + regional_abbrev
```

Không ghép `partial_diacritic_drop + full_diacritic_strip`. Hai tag không được
che cùng một thay đổi nếu trace không thể phân giải từng phép.

## Difficulty và naturalness

- Mutation có giá trị nhất nằm trong name/brand/discriminator; lỗi chỉ ở admin,
  descriptor hoặc province có giá trị thấp.
- Giữ ít nhất một anchor dễ đọc. Với `brand + street`, không phá nặng đồng thời
  cả hai.
- Phân phối lỗi qua đầu, giữa và cuối identity ở cấp batch; không nhân cùng brand
  typo sang mọi branch.
- Mechanical typo ưu tiên transpose, adjacent-key substitution và delete bên
  trong token. Double-tap cuối token không dùng làm mặc định.
- Một source quá ngắn hoặc toàn code có thể dùng operator phù hợp khác; không phá
  code để đạt quota.
- Sáu authored rows là coverage pool. Sampling weight và prefix augmentation
  quyết định phân bố train thực tế.

## Naturalness rejects

Reject câu hỏi/web, voice/chat, action intent, recommendation hoặc local intent
không có fact, ví dụ `ở đâu`, `chỉ đường`, `cho tôi đến`, `đặt phòng`, `rút tiền`,
`gần tôi`, `ngon nhất`. Tên thật chứa chuỗi tương tự vẫn được giữ nếu toàn cụm là
official name.

## Qrels

Kiểm tra lại qrels sau mọi phép làm ngắn, bỏ dấu, abbreviation, token boundary,
name fragment, token order hoặc omission. Query mơ hồ phải có đủ acceptable IDs
đã xác minh hoặc được viết lại. Bare brand nhiều branch được handoff sang brand
dataset, không mở rộng thành nhiều row POI.
