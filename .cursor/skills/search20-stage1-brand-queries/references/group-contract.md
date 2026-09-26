# Brand group contract

## Identity levels

Phân biệt hai cấp:

```text
brand_family_id: toàn bộ identity thương hiệu, ví dụ brand:vietcombank
brand_group_id: family + namespace, ví dụ brand:vietcombank:atm
```

Không dùng một group cho các namespace có intent khác nhau.

## Namespace whitelist khởi đầu

```text
fuel
bank
atm
cafe
restaurant
convenience_store
supermarket
pharmacy
hotel
retail
other_reviewed
```

Không tạo namespace mới nếu category hiện tại đã diễn đạt được. Trường hợp khó
đặt `other_reviewed` và bắt buộc manual note.

## Membership schema

```text
brand_family_id          string
brand_group_id           string
brand_canonical          string
brand_fold               string
brand_namespace          string
poi_id                   string
destination_searchable   boolean
province_region_id       string nullable
subdistrict_region_id    string nullable
membership_status        accepted | needs_review | excluded
membership_evidence      explicit_brand | exact_name_pattern |
                         verified_alias | manual_adjudication
evidence_text             string
group_version             string
review_status             authored | accepted | needs_review
```

Primary key: `brand_group_id + poi_id`.

## Membership decision

Auto-accept membership khi POI searchable, group có ít nhất hai member mạnh,
namespace nằm trong whitelist và có evidence đủ mạnh:

- `brand` field khớp canonical/verified alias;
- POI name khớp exact canonical của một family đã có explicit-brand evidence.

Giữ `needs_review` khi evidence cần suy luận:

- name pattern sau khi bỏ descriptor;
- alias chưa được adjudicate ở family level;
- singleton group hoặc namespace `other_reviewed`;
- surface trùng nhiều family.

`membership_status=accepted, review_status=authored` nghĩa là pass rule mạnh tự
động. `review_status=accepted` nghĩa là family/top group đã được người review.
Hai trạng thái này phải được giữ riêng để audit và chọn mức tin cậy downstream.

Manual adjudication có thể accept khi:

- alias trong corpus map rõ vào brand;
- manual adjudication có evidence text.

Không accept chỉ vì:

- brand token là substring của tên dài không liên quan;
- cùng từ generic như `An Phước`, `Phương Anh`, `Mango`;
- cùng category;
- gần nhau về địa lý;
- model/embedding cho score cao.

## Family and namespace rules

- `WinMart` và `WinMart+` là hai family/group riêng nếu product/corpus phân biệt.
- `Vietcombank ATM` và `Vietcombank bank` cùng family nhưng khác group namespace.
- Bare `Vietcombank` có thể resolve union nhiều namespace chỉ khi product policy
  chấp nhận; nếu chưa chốt thì `needs_review`.
- Branch đóng, duplicate hoặc `destination_searchable=false` không vào positive
  pool, nhưng có thể giữ membership `excluded` để audit.

## Group QA

Cho mỗi group, báo:

```text
n_members_total
n_accepted_searchable
n_needs_review
n_excluded
province_count
category_distribution
evidence_distribution
```

Review thủ công mọi group có category lẫn lộn, một member duy nhất, hoặc tăng/
giảm member bất thường so với version trước.

Ưu tiên review top family theo member count và toàn bộ anomaly; không cần mở từng
branch explicit-brand sạch. Descriptor generic như `tạp hóa`, `trạm xăng`,
`homestay` phải excluded ở family level dù corpus điền vào field `brand`.
