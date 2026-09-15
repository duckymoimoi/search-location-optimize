# Hanoi POI — corpus ổn định v1

Version `hn-poi-stable-v1`. Bản POI chuẩn hóa để dựng search index và sinh dataset tiếp theo, dựa trên snapshot OSM ngày 10/09/2026 và dữ liệu v8. Đây là corpus có hợp đồng dữ liệu cố định và nguồn truy vết; không phải địa chỉ thực địa hoặc điểm đón đã được xác minh.

## Dùng file nào?

| File | Vai trò |
|---|---|
| `pois.parquet` | Nguồn chính, một dòng cho mỗi POI; 18 cột cấp ngoài, dữ liệu liên quan nằm trong struct |
| `search_documents.parquet` | Văn bản dựng sẵn cho destination searchable; có hai passage để thử ảnh hưởng của context |
| `poi_audit.parquet` | Bằng chứng từng trường địa chỉ, dữ liệu bị chặn, enrichment chưa được chấp nhận |
| `entity_members.parquet` | Liên kết POI với thành viên OSM/entity từ v8 |
| `POI_SCHEMA.md`, `schema.json` | Ý nghĩa và kiểu dữ liệu |
| `manifest.json`, `validation.json` | Version, dấu vân tay input/output và các kiểm tra thực tế |
| `dataset_v8_compatibility.json` | Kiểm tra ID với dataset 20k hiện có; không phải chứng nhận lại nhãn |
| `build_corpus.py` | Builder và text builder dùng chung cho train/index |
| `inputs/` | Bằng chứng đóng băng để tái tạo bản corpus này; không đưa các bảng này vào serving |

Bản này có 46.792 POI; 45.692 destination searchable; 8.131 origin demo; 625 POI có bổ sung địa chỉ building đã kiểm tra; chưa có pickup access được xác minh. Số liệu chi tiết nằm trong `validation.json`. Không xóa object chưa searchable: giữ ID và audit để có thể sửa về sau. Chỉ index những dòng `destination_searchable=true`.

## Địa chỉ và context

`address` chứa các trường trực tiếp đã qua bộ lọc, cộng với số nhà–đường được kế thừa từ building nếu kiểm tra được geometry và địa chỉ nguồn. Null có nghĩa là chưa có giá trị được chấp nhận. `address_status=direct` chỉ có nghĩa có dữ liệu trực tiếp từ nguồn, không có nghĩa đủ địa chỉ hoặc đã xác minh.

Khi kế thừa, builder yêu cầu building có geometry hợp lệ, đầy đủ, bao phủ ranking point, có cả số nhà và street/place, và không xung đột với bất kỳ trường địa chỉ hiện có. Không tự ghép số nhà của đường A vào đường B. Các trường đã bị loại trong các lần xử lý trước không được lấy lại từ nguồn enrich. Không kế thừa unit/floor từ một đơn vị khác trong tòa nhà.

Đường gần đó, tên khuôn viên và địa giới polygon nằm trong `context`, không nằm trong `address`. Context kế thừa từ v8 chưa được replay toàn bộ geometry trong lần build này. Khoảng cách đường là số gần đúng từ v8, không dùng làm route distance hoặc ngưỡng an toàn. Tên địa giới trực tiếp và tên polygon có thể thuộc các thời kỳ khác nhau; không tự ghi đè, không tuyên bố bên nào là tên hành chính hiện hành.

Enrichment từ address node gần đó và consensus không đủ bằng chứng được giữ trong audit. Bản này chủ động giảm coverage địa chỉ suy ra để tránh đưa bằng chứng yếu thành nhãn chắc chắn. Bộ lọc ký tự có phạm vi cụ thể; không tuyên bố xử lý mọi confusable hoặc xác thực tên đường bằng gazetteer.

## Dùng cho search

```python
import pyarrow.parquet as pq
from build_corpus import passage

pois = pq.read_table('pois.parquet').to_pylist()
catalog = [p for p in pois if p['destination_searchable']]
texts = ['passage: ' + passage(p, mode='address') for p in catalog]
# E5 query input: 'query: ' + chuoi_nguoi_dung_go
```

Với lexical, index `name`, `aliases`, `ref`, các trường address và context thành field riêng để đặt trọng số. Không gộp đường gần đó vào exact-address field. Với dense, `passage_address` và `passage_context` là hai lựa chọn đã dựng sẵn; mỗi thí nghiệm phải dùng nhất quán một lựa chọn cho train và index. Không dùng track/case_type hoặc nhãn target làm feature.

Passage mới khác passage checkpoint cũ: cần encode lại corpus và đánh giá lại. Chưa có bằng chứng bản này tăng Hit/MRR. Giữ checkpoint/config cố định khi so sánh hai passage, chọn bằng dev; không tune bằng frozen comparison set.

Top-5 chỉ collapse theo entity_group_id được phép và policy bảo vệ access point. Không collapse mọi POI trùng tên hoặc gần nhau. `context.container_osm_id` không tự trở thành complex_id, và nguồn OSM trong context không nhất thiết có trong destination catalog.

## Dùng để sinh dataset

1. Chọn target từ destination searchable. Origin pool là tập riêng theo origin_search_eligible, không dùng để lọc destination.
2. Query tên/alias/mã phải dựa trên trường tương ứng. Mã ngắn cần namespace có bằng chứng từ địa chỉ hoặc nguồn building; thiếu namespace thì đưa vào track ambiguity/structured diagnostic.
3. Query địa chỉ lấy từ `address`. Chỉ sinh dạng số nhà–đường nếu đủ hai trường. Không sinh số nhà từ nearby context. Số nhà nhiều giá trị/range như `59,67` hoặc `7-9` giữ nguyên; không tự chọn một số và coi đó là nhãn chắc chắn.
4. Query dùng khuôn viên/nearby/admin phải mang provenance context và đánh giá riêng; không tự nâng thành single-target gold. `address_status` không phải nhãn chất lượng query.
5. Sinh chuỗi gõ tự nhiên: không dấu, sai dấu, lỗi phím, thiếu/đảo từ có kiểm tra ngôn ngữ, prefix, Telex/VNI diagnostic, địa chỉ slash, mã có namespace. Không dùng template hội thoại như “cho tôi tới X”.
6. Gắn mọi query với corpus_version; chia group trước khi tạo biến thể. Khi ghép dataset cũ, giữ nguyên split/family; không suy split từ entity_group_id. Corpus này không tái tạo poi_splits đang thiếu trong folder v8.
7. Tạo lại hoặc audit qrels khi thay address/alias/index text. Giữ ID chỉ bảo đảm khả năng join, không bảo đảm nhãn cũ còn đầy đủ. Không dùng toàn bộ catalog làm qrels fallback cho query không hiểu được.

Origin/destination của Stage 2 phải tham chiếu cùng corpus version. Origin sampler phải có seed, version và distance strata. Corpus này chưa tạo dữ liệu user/time/history hoặc xác nhận điểm đón.

## Tái tạo và cập nhật

```bash
pip install -r requirements.txt
python build_corpus.py --inputs inputs --output rebuilt
```

Input đã được đóng băng và có hash. Khi cập nhật POI hoặc policy, tạo version corpus mới, ghi hash input/output và lưu bảng thay đổi theo poi_id; không sửa nội dung âm thầm dưới cùng version. Tách model_version, corpus_version và index_version. POI mới có thể được encode bằng model hiện tại rồi cập nhật index; chỉ retrain khi thực nghiệm cho thấy cần.

Giữ tên/alias có dấu; accent folding là field index dẫn xuất. Không tự đồng nhất tên bỏ dấu với tên có dấu. Giữ mã và dấu `/`; không suy diễn căn A ở số 32 thành số nhà 32A.

Nguồn là dữ liệu dẫn xuất OpenStreetMap. Giữ attribution OpenStreetMap contributors và metadata ODbL đi cùng dữ liệu gốc. Số lượng và coverage chỉ phản ánh snapshot, không đại diện toàn bộ địa điểm Hà Nội ngoài thực tế.

## Ghép bộ 20k v8 hiện có

Tất cả 20.000 intended target vẫn tồn tại và searchable. Một record chỉ có tên website được loại khỏi search nhưng giữ trong corpus; có 4 qrel links của 4 query trỏ tới record này, được liệt kê trong dataset_v8_compatibility.json. Chưa sửa qrels hoặc eligibility cũ. Khi migrate, phải xử lý các link này và audit lại evidence của query địa chỉ; không coi việc join được là nhãn đã được kiểm chứng lại.
