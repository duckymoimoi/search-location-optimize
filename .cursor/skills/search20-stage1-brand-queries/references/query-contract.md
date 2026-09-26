# Brand-only query contract

## Query schema

```text
query_id                    string
query_text                  string
canonical_brand_query       string
brand_family_id             string
namespace_scope             list<string> nullable
intent_scope                BRAND
intent_id                   string
qrel_policy                 FAMILY_ALL | FAMILY_NAMESPACE
query_variant_family        string
variant_operator            string
severity                    CLEAN | SINGLE
language_tag                lang_vi | lang_en | lang_mixed
review_status               authored | accepted | needs_review
generator_version           manual_brand_authored_v1
```

`intent_id` bằng `brand_family_id` cho `FAMILY_ALL`, hoặc `brand_group_id` cho
`FAMILY_NAMESPACE`.

`normalized_query_text` dùng cho dedupe/audit, không phải text train: áp dụng NFKC,
casefold, trim và collapse whitespace; giữ `+`, digit và punctuation mang identity.
Không accent-fold trong khóa dedupe chính. Accent-fold chỉ là khóa collision phụ để
phát hiện query có thể nhập nhằng.

## Operator whitelist

Tạo 2–6 variants theo eligibility, ưu tiên 3+ khi tự nhiên:

| Operator | Severity | Rule |
|---|---|---|
| `brand_canonical` | CLEAN | exact canonical brand; nếu family đa namespace thì thêm namespace token bắt buộc |
| `brand_namespace_form` | CLEAN | canonical brand + verified namespace token, cho phép đổi vị trí token nhưng không đảo token bên trong brand |
| `brand_alias` | CLEAN | alias có evidence; không tự rút gọn |
| `brand_case_punct` | CLEAN/SINGLE | casing/punctuation tự nhiên, không đổi token identity |
| `brand_mechanical_typo` | SINGLE | đúng một edit ở token đủ dài |
| `brand_space_variant` | SINGLE | split/merge có tính người dùng; không shuffle; không tách `+`/digit identity |
| `brand_orthographic_ime` | SINGLE | strip, residual Telex/VNI, hoặc sai thanh khi áp dụng được |
| `brand_phonetic` | SINGLE | nhầm âm Việt hợp lệ, không thành brand khác |

Không tạo operator không áp dụng được. Brand ASCII như `Eneos` không có variant
strip-diacritics. Không dùng compound noise mặc định. Brand quá ngắn hoặc dễ
thành brand/acronym khác khi typo có thể chỉ có hai rows; không bịa lỗi để đủ ba.

## Query content

- Chỉ chứa canonical brand, verified alias và namespace token cần thiết.
- Không chứa street, ward, branch, province hoặc landmark.
- Không chứa action intent: `rút tiền`, `đổ xăng`, `đi chợ`, `mua sắm`,
  `đặt phòng`, `xem phim`.
- Query `Vietcombank ATM` có namespace `atm`; query `Vietcombank` dùng family
  policy đã review.
- Family có nhiều accepted namespace bắt buộc canonical group query chứa token
  namespace. Không gán bare brand cho riêng một namespace.
- Không tự bỏ `+`, đổi số, mở rộng acronym hoặc dịch brand.
- Reject typo/phonetic variant trùng canonical/alias của brand khác.
- Một lỗi brand phổ biến chỉ author một lần cho intent; không copy nó theo số branch.

## Qrels schema

```text
query_id          string
poi_id            string
relation          positive_pool | compatible_mask | ignore
label_reason      string
brand_group_id    string
qrels_version     string
```

Brand query không có một branch intended duy nhất. Mọi accepted searchable member
trong resolved scope là `positive_pool`. Training sampler lấy một số positives;
member còn lại phải được mask, không được thành negative.

## Query QA

Reject khi:

- normalized query trùng query khác nhưng intent scope khác chưa adjudicate;
- canonical/alias không thuộc family;
- operator làm mất brand identity;
- query không resolve được positive;
- namespace token và namespace scope mâu thuẫn;
- query chứa branch/address/action text;
- operator chỉ được gắn label nhưng text không thực hiện phép biến đổi.
