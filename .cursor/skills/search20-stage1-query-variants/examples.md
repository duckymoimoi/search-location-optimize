# Stage-1 train authoring examples

Các ví dụ minh họa cách giữ identity và trace operator. Không sao chép typo,
địa chỉ, alias hoặc tag set sang POI khác nếu source không hỗ trợ.

## Named POI

Source:

```text
name=Cà Phê Mộc Miên
street=Nguyễn Trãi
category=amenity=cafe
```

Một pack hợp lệ có thể dùng:

| Slot | query_text | Ý nghĩa |
|---|---|---|
| v01 | `Cà Phê Mộc Miên Nguyễn Trãi` | official name + discriminator |
| v02 | `Mộc Miên Nguyễn Trãi` | identity core tự nhiên |
| v03 | `Moocj Miên NguyễnTrãi` | raw Telex + token boundary |
| v04 | `Mọt Miên Ngyuễn Trãi` | phonetic confusion + mechanical typo |
| v05 | `Nguyễn Trãi Mộc Mienn` | token order + mechanical typo |
| v06 | `Mộcj Miên Ngyuễn Trãi` | IME residual + mechanical typo |

Không thêm quận/tỉnh để tạo surface. Qrels phải được kiểm tra lại sau khi bỏ
`Cà Phê` khỏi v02.

## Brand branch

Source:

```text
brand=Eneos
street=Nguyễn Oanh
category=amenity=fuel
```

| Slot | query_text | Ý nghĩa |
|---|---|---|
| v01 | `Cây xăng Eneos Nguyễn Oanh` | official brand + discriminator |
| v02 | `Eneos Nguyễn Oanh` | không tạo bare-brand intent |
| v03 | `Eneso NguyễnOanh` | mechanical typo + token boundary |
| v04 | `Eneos Nguyeenx Oanhh` | raw Telex + mechanical typo |
| v05 | `Ngyuễn Oanh Eneos` | token order + mechanical typo |
| v06 | `Eneos Nguyển Onah` | phonetic confusion + mechanical typo |

Không nhân `Eneso` sang mọi chi nhánh. Ở cấp batch, brand và discriminator cùng
tham gia chịu lỗi nhưng mỗi branch có realization riêng.

## Token boundary

Các dạng hợp lệ:

| Parent | Variant | Trace |
|---|---|---|
| `Bách Hóa Xanh Nguyễn Trãi` | `BáchHóa Xanh Nguyễn Trãi` | `Bách Hóa -> BáchHóa` |
| `Highlands Nguyễn Oanh` | `High lands Nguyễn Oanh` | `Highlands -> High lands` |
| `23 Nguyễn Trãi` | `23Nguyễn Trãi` | `23 Nguyễn -> 23Nguyễn` |

Mỗi span chỉ đổi boundary whitespace. `Bách Hóa→BáhHóa` phải có thêm
`mechanical_typo` và trace riêng cho thay đổi ký tự.

Reject:

- merge nhiều boundary để biến cả câu thành một token;
- merge qua `/`, `+`, hyphen hoặc apostrophe mang identity;
- `72B→7 2 B` vì phá code;
- nối admin phụ chỉ để đạt coverage.

## Raw Telex và VNI

| Parent | Variant | Tag |
|---|---|---|
| `Cửa hàng Mỹ phẩm Cỏ Mềm` | `cuwar hafng myx phaamr Cỏ Mềm` | `raw_ime_sequence` |
| `Phở Bò Nam Định` | `pho73 bo2 Nam Định` | `raw_ime_sequence` |
| `Vạn Hạnh` | `Vạn Hanhj` | `ime_telex_residual` |

Raw sequence phải theo một bộ gõ nhất quán trong span. `Vạn Hạnhx` không phải
IME residual hợp lệ nếu `x` không tạo dấu dự kiến.

## Verified name fragment

Source:

```text
name=Quán Cơm Tấm Ba Ghiền
```

`Ba Ghiền` có thể dùng `verified_name_fragment` khi collision check cho thấy đây
là cách gọi đủ nhận diện và qrels đã bao phủ mọi match hợp lý. Đây không phải
prefix: prefix expander của `Quán Cơm Tấm Ba Ghiền` không thể tự sinh đoạn giữa
`Ba Ghiền`.

Reject fragment như `Quán`, `Cơm`, `Hotel`, `Center` nếu quá generic.

## Acronym

Với source `Bệnh viện Đa khoa Tỉnh Hòa Bình`:

| Query | Operator | Điều kiện |
|---|---|---|
| `BVĐK tỉnh Hòa Bình` | `acronym_expand_contract` | source xác nhận đúng cụm |
| `Bệnh viện đa khoa Hòa Bình` | `safe_omission` | qrels vẫn đủ |

Không mở `TH` trong một brand như `TH True Mart`. `ATM` chỉ được mở rộng khi
namespace/source khóa đúng nghĩa.

## Address-only và slash

Source:

```text
housenumber=30/48D
street=Nguyễn Văn Linh
province=Thành phố Cần Thơ
```

| Slot | query_text | Ý nghĩa |
|---|---|---|
| v01 | `30/48D Nguyễn Văn Linh Cần Thơ` | exact address anchor |
| v02 | `30/48D Nguyễn Văn Linh` | natural address |
| v03 | `30/48D Ngyuễn Văn Lihn` | hai mechanical points |
| v04 | `Số 30 hẻm 48D Ngyuễn Văn Linh` | slash spoken + mechanical |
| v05 | `Ngyuễn Văn Linh 30/48D` | token order + mechanical typo |
| v06 | `30/48D NguyễnVăn Lihn` | token boundary + mechanical |

Mọi variant giữ `30`, `48D` và thứ tự. Chỉ dùng `hẻm` khi region/evidence phù
hợp; nếu không, giữ slash.

## Full address paste

Source có đủ component:

```text
121 Lê Lợi, Phường Bến Thành, Quận 1, Thành phố Hồ Chí Minh
```

`121 Lê Lợi, Phường Bến Thành, Quận 1, TP HCM` là `full_address_paste` hợp lệ.
Không thêm `Việt Nam`, landmark hoặc district không có trong source. Dấu phẩy có
thể xuất hiện trong form paste nếu schema/operator cho phép; quy tắc bỏ dấu `.`
không đồng nghĩa cấm mọi punctuation tự nhiên.

## Prefix handoff

Authored query:

```text
Mộc Miên Nguyễn Trãi
```

Pipeline có thể sinh checkpoint như `Mộ`, `Mộc`, `Mộc Miên`, `Mộc Miên Nguyễn`
theo cấu hình train/eval. Không thay một trong sáu authored rows bằng `Mộc M`.
Prefix quá ngắn hoặc chưa có identity evidence cần được sampling/down-weight ở
pipeline, không giải quyết bằng cách kéo dài authored query.

## Fact và naturalness rejects

| Bad | Lý do |
|---|---|
| đổi `Mai Chau` thành `Mai Châu` khi source không có alias | respell proper name |
| hotel thành homestay/resort | đổi category |
| thêm district từ kiến thức ngoài source | bịa fact |
| `30/48D→30-48D` hoặc `3048D` | phá housenumber |
| `Số 30 hẻm 49D` từ `30/48D` | đổi digit/suffix |
| bare `WinMart+` gán một branch | qrels sai namespace |
| `đặt phòng khách sạn...`, `rút tiền...` | action intent |
| `gần tôi`, `quanh đây` | local intent không có fact |
| cùng typo xuất hiện ở nhiều slot/case | formulaic coverage |

Nếu không thể tạo biến thể đúng source, tự nhiên và recoverable, đặt
`needs_review`; không điền đủ slot bằng dữ liệu rác.
