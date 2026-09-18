# Operator whitelist (Stage 1 gold)

IDs ổn định (English). Gold: `CLEAN` hoặc `SINGLE` only.

## CLEAN

| operator | Notes |
|---|---|
| `canonical` | Query đủ chỉ intended (hoặc set acceptable) theo text |

## ORTHOGRAPHIC_IME

Không mặc định là “user sai”.

| operator | Example | Reject |
|---|---|---|
| `strip_diacritics` | `Bạch Mai` → `Bach Mai` | output ≡ canonical; đụng digit/`/`/mã |
| `partial_diacritics` | một phần token còn dấu | trùng full-strip |
| `tone_confuse` | `Phở` → `Phợ` | đổi cả nguyên âm/phụ âm |
| `telex_leftover` | `cửa` → `cuwar` | Telex random vô nghĩa |

Telex `variant_subtype`: `telex_vowel_marker` · `telex_dd` · `telex_tone_marker` · `partial_telex` · `mixed_converted_telex`

## MECHANICAL_TYPO

| operator | Example | Reject |
|---|---|---|
| `char_delete` | `bach` → `bac` | token &lt; 3; xóa digit mã/số nhà |
| `char_insert` | `bach` → `bacch` | insert alphabet đều / đổi entity |
| `char_substitute` | `bach` → `baxh` | nhầm với phonological |
| `char_transpose` | `bach` → `bcah` | swap âm tiết/token |
| `adjacent_key` | `phong` → `phpng` | đổi nghĩa số nhà |
| `double_letter` | `bach` → `bachh` | thực chất Telex `aa`/`dd` → dùng `telex_leftover` |

## PHONOLOGICAL

| operator | Example | Reject |
|---|---|---|
| `phonological_confusion` | `trường` → `chường` | ngoài bảng `s↔x` `tr↔ch` `d↔gi↔r` `l↔n`; đổi entity |

## TOKEN_EDIT

| operator | Example | Reject |
|---|---|---|
| `syllable_delete` | bỏ 1 âm tiết | query generic + qrel 1 ID; xóa số nhà |
| `space_merge` | `LêDuẩn` / `MìCay` / `SpringHotel` | dính chữ địa danh hành chính cơ học (`ĐàNẵng`, `CầnThơ`, `HàNội`); >1 biên trên SINGLE |
| `space_split` | `High lands` / `30 / 49` | cắt mã tòa / số nhà |

## PREFIX (hạn chế trên gold)

| operator | Gold policy |
|---|---|
| `char_prefix` / `token_prefix` | **Không** lưu chuỗi đầy đủ — benchmark sinh |
| `mid_token_incomplete` | Tối đa 1 / case nếu hữu ích |

## ALIAS (không phải noise)

| operator | Example | Reject |
|---|---|---|
| `abbreviation` | `BVĐK` | invent initials |
| `short_name` | `Ngày của Nắng Coffee` (standalone POI) / `Ba Ghiền` | mất identity mà qrel vẫn 1 ID |
| `code_short` | `S3.01` / `B3` | bịa mã; mã trùng mà không multi-positive |
| `name_area` | `Highlands Cầu Giấy` | area sai fact |
| `english_or_bilingual_alias` | tên EN xác minh | MT mù tên riêng |

Pattern gợi ý trong `query_types` / subtype: `name+ward` · `brand+province` · `housenumber+street` · `en_name+category` · `code+area` · `paraphrase` · `standalone_name`

## ADDRESS_VARIANT

| operator | Example | Reject |
|---|---|---|
| `slash_normalize` | `166/9 Gio An` → `số 166 ngõ 9 Gio An` / `Hẻm 96/2` / `K151/68` | dạng gạch nối cơ học `166-9`; tự chế đuôi số gán vào canonical không xuyệt |
| `housenumber_format` | `72B` → `72 B` | mất letter/digit |
| `address_component_omission` | bỏ tên phố/tỉnh | xóa nhầm từ đồng âm thuộc tên POI (như chữ `Quận` trong `Café Cố Quận`); còn mơ hồ + unique-target |

## STRUCTURAL

| operator | Example | Reject |
|---|---|---|
| `token_order_variant` | `Trung Nguyên Cà phê` / `Phở Lâm Gà` / `Hội An Bánh Mì` | xé lẻ danh từ riêng (`Trung Cà phê Nguyên`, `Hội Bánh Mì An`, `Lý Phở Quốc Sư`); shuffle ngẫu nhiên; gắn nhầm mechanical |

---

## Eligible quick table

| Operator | Apply when |
|---|---|
| `strip_diacritics` | còn dấu VN |
| `telex_leftover` | âm tiết Telex được |
| `char_*` / `adjacent_key` | token chữ đủ dài |
| `syllable_delete` | ≥2 token meaningful |
| `code_short` | POI có mã/tên mã xác minh trên row |
| `slash_normalize` | housenumber có `/` |
| `name_area` | biết ward/province đúng fact |

---

## `query_types` tags

`exact_name` · `partial` · `address` · `street` · `landmark` · `brand` · `category` · `name_address` · `name_area` · `abbreviation` · `typo` · `code` · `very_short` · `long_tail` · `lang_vi` · `lang_en` · `lang_mixed`
