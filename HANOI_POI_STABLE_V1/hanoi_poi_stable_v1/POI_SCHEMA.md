# Hợp đồng POI — hn-poi-stable-v1

Một dòng trong `pois.parquet` là một POI có ID ổn định trong snapshot. Có **18 cột cấp ngoài**. Struct giúp nhóm dữ liệu có quan hệ; tổng số trường con vẫn được công khai trong schema.json, không phải 18 giá trị đơn.

| Cột | Nội dung / quy tắc |
|---|---|
| poi_id | String duy nhất, giữ canonical_id v8, dạng osm:node/… hoặc osm:way/… |
| name | Tên search đã chuẩn hóa; null nếu không có tên dùng được. Không phải name_raw nguyên gốc |
| aliases | List tên khác từ nguồn; không tạo alias bằng AI trong bước này |
| category | Tag category hiện có, ví dụ amenity=cafe; chưa thay bằng taxonomy mới |
| brand | Brand từ corpus OSM gốc; nullable, không suy từ chuỗi tên |
| ref | Mã ref OSM trực tiếp; nullable, không suy từ số nhà |
| address | Struct các trường địa chỉ trực tiếp/được chấp nhận; xem bên dưới |
| address_status | direct / inherited_building / missing. inherited_building có thể đồng thời có trường direct |
| context | Struct thông tin không gian hỗ trợ search, tách khỏi địa chỉ |
| ranking_point | Struct lat, lon, quality. WGS84, độ; point đại diện để hiển thị/ranking |
| routing_point | Struct lat, lon, quality hoặc null; chỉ có khi nguồn xác nhận pickup access và có tọa độ |
| destination_searchable | Bool; tập target/index. False vẫn được giữ trong corpus để truy vết |
| origin_search_eligible | Bool; pool chọn origin trong demo, yêu cầu tên hiển thị dùng được; không xác nhận đón xe |
| pickup_access_verified | Bool; bản hiện tại đều false |
| entity_group_id | Group dedup kế thừa v8; không phải leakage_group_id |
| branch_id | ID chi nhánh khi nguồn có bằng chứng; nullable |
| complex_id | Quan hệ khu phức hợp khi có bằng chứng; nullable; không suy từ container gần đó |
| preserve_individual_access_point | Bool bảo vệ platform/entrance khi collapse kết quả |

## Address

Các trường con đều string nullable: `housenumber`, `street`, `place`, `unit`, `floor`, `block`, `building`, `housename`, `quarter`, `hamlet`, `subdistrict`, `district`, `city`, `province`, `postcode`, `country`, `full`, `suburb`, `ward`, `neighborhood`, `neighbourhood`, `state`.

Giữ các namespace OSM khác nhau: suburb không tự đổi thành subdistrict. Chưa có bằng chứng chuẩn hóa địa giới thì giữ đúng trường nguồn. Các trường ít dùng có thể null mà không cản trở POI được tìm theo tên.

`full` là địa chỉ free-form có sẵn từ nguồn; không được tự parse thành số nhà. Khi full tồn tại text builder dùng full, các trường con khác vẫn giữ để audit. `housenumber` cũng là chuỗi, có thể là mã hoặc tập số; không ép integer. Không xóa `/`, không ghép unit vào số nhà.

Provenance nằm ở `poi_audit.parquet.address_provenance_json`, theo từng key, gồm source và osm_id. Các giá trị bị từ chối cùng lý do ở rejected_fields_json; các giá trị suy ra chưa đủ bằng chứng ở pending_enrichment_json. Chúng không được tự đưa lại vào passage.

## Context

| Trường con | Ý nghĩa |
|---|---|
| container_name | Tên khuôn viên/building từ v8; hint, không chứng nhận complex membership |
| container_osm_id | ID nguồn OSM; không phải FK bắt buộc vào poi_id |
| nearby_street | Tên đường gần đó; không phải addr:street |
| nearby_street_osm_id | Way nguồn từ v8 |
| nearby_street_distance_m_approx | Khoảng cách gần đúng v8, 0–100 m; không phải route distance |
| admin | Arrow map<string,string>, tên địa giới theo polygon nguồn; khi to_pylist() là list các cặp key/value |

Context không có bằng chứng field-level mới ngoài nguồn v8 thì giữ độ tin cậy context. Không dùng để gán số nhà hoặc pickup access. Các địa giới hiện hành ngoài đời chưa được xác minh trong gói này.

## Điểm tọa độ và giá trị rỗng

`ranking_point.quality` lấy từ corpus gốc: explicit_node / point_on_surface / member_geometry_representative. Không gọi tất cả là centroid. Routing point hiện null; UI có thể vẽ đường thẳng giữa ranking points nhưng phải gọi là khoảng cách/đường minh họa, không phải lộ trình xe tiếp cận được.

Null = chưa có giá trị chấp nhận; list rỗng = không có phần tử. Không thay null bằng 0, không tạo tọa độ 0,0 làm fallback. Không sinh origin_display_label riêng vì demo dùng name và eligibility đã yêu cầu name hợp lệ.

## Version và tính tương thích

Version nằm một lần ở manifest, không lặp ở từng dòng. Source version, policy version và dấu vân tay nguồn cũng nằm ở đó. Job train/eval phải lưu manifest hash, model checkpoint và passage mode đã dùng.

Chuyển từ v8: canonical_id → poi_id; search_label → name; search_aliases → aliases; ranking_lat/lon → ranking_point; routing_lat/lon → routing_point; address_fields_json/enrichment được xử lý theo policy mới. Không dùng nguyên search_address_text v8. Các ID giữ nguyên, nhưng địa chỉ/alias/index coverage có thể thay đổi. Mọi migration qrels phải có version riêng, không cập nhật ngầm test cũ.
