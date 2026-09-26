# Integrate POI and brand training data

## Không merge raw tables trực tiếp

Giữ provenance riêng:

```text
POI query dataset       -- explicit per-query qrels
Brand query dataset     -- family/group qrels
Brand membership table  -- group resolver
```

Compile thành hai normalized views.

## Unified query view

```text
query_id
query_text
source_dataset          poi_queries | brand_queries
intent_scope            POI | BRAND
intent_id               poi_id | brand_family/group_id
query_variant_family
variant_operator
severity
split
sample_weight
generator_version
```

## Unified relation view

```text
query_id
poi_id
relation                positive_pool | compatible_mask | ignore
label_reason
qrels_version
```

POI queries được compile từ `acceptable_poi_ids`. Brand queries được compile từ
brand membership + namespace scope.

## Migrate bare-brand rows từ POI dataset

1. Tìm rows có query chỉ là brand/verified alias.
2. Map sang reviewed `brand_family_id`.
3. Dedupe theo `brand_family_id + normalized_query_text`.
4. Giữ một row trong brand query dataset.
5. Viết lại POI v02 thành `brand + street/ward/ref`.
6. Xóa bare-brand singleton khỏi POI dataset.

Không chọn ngẫu nhiên một branch làm intended cho row đã chuyển.

## Thứ tự triển khai

1. Khóa contract và sửa POI dataset hiện tại về branch-specific trước.
2. Có thể chạy song song việc extract candidate brand family, nhưng chưa accept
   query/qrels brand khi membership chưa review.
3. Review group, namespace và alias; sau đó mới author brand variants.
4. Compile unified views chỉ khi cả POI QA và brand QA đều PASS.

Như vậy không cần chờ toàn bộ POI dataset hoàn tất mới bắt đầu inventory brand,
nhưng không merge brand vào train view trước khi POI bare-brand đã được di trú.

## Split policy

- Split brand queries theo `brand_family_id`; mọi variants của một family cùng split.
- Báo riêng `cold_brand` (toàn family holdout) và `cold_branch` (brand đã thấy,
  branch chưa thấy).
- Strict cold-POI holdout không được lấy held-out POI làm sampled positive trong
  training, dù cùng brand; vẫn mask để tránh false negative nếu policy yêu cầu.

## Training sampler handoff

Cho query `FAMILY_ALL` hoặc `FAMILY_NAMESPACE`:

1. sample 2–4 POI từ positive pool mỗi epoch;
2. mask toàn bộ same-scope members còn lại khỏi denominator;
3. mine negatives từ brand/family khác;
4. không mine same-group POI làm hard negative.

Giữ brand queries là track phụ. Điểm khởi đầu thí nghiệm:

```text
80–90% POI/branch-specific queries
10–20% brand-level queries
```

So sánh cùng split/compute:

```text
E0 = POI queries only
E1 = POI queries + brand queries
```

Chỉ giữ E1 nếu bare-brand recall tăng mà branch/address recall và wrong-branch
không xấu đi.

## Runtime boundary

Không cần brand index riêng cho v1. Query vẫn retrieve trực tiếp POI documents.
Có thể backfill `brand_family_id`/`brand_group_id` vào document để filter, trace
và rerank. Hierarchical brand-index → branch expansion là thí nghiệm khác, không
tự kích hoạt từ dataset này.
