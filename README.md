# Hanoi POI query dataset — pilot v3

**Dataset `hnq10k-pilot-v3`: 10.000 dòng query, 2.000 destination POI.** Corpus nguồn `hn-260910-7f1b69b167` có 46.792 bản ghi. `corpus_search_view.parquet` giữ tất cả ID và cung cấp **45,693 bản ghi destination_searchable** sau audit tên/địa chỉ. Dùng đúng search view này để tạo passages, candidates và kiểm tra nhãn trong thí nghiệm v3.

## Phạm vi và ba cờ độc lập

| Cờ | Ý nghĩa |
|---|---|
| `destination_searchable` | Có tên/brand/operator/ref dùng được, hoặc địa chỉ số nhà + phố được chấp nhận theo policy; là điều kiện lấy target Stage 1 |
| `origin_search_eligible` | Policy origin trong corpus AND có `origin_display_label` dùng được; không lọc destination |
| `pickup_access_verified` | Đã xác minh khả năng tiếp cận điểm đón; hiện không có bản ghi nào được xác minh |

Trong 2.000 targets có **1615 POI không thuộc origin pool**, **325 tên một token**, **499 đối tượng lấy địa chỉ làm tên tìm kiếm**, **58 POI có slash trong số nhà/phố**, **63 có unit trong địa chỉ được chấp nhận**. Unit có thể là tầng hoặc ký hiệu nguồn; không mặc định là mã căn hộ. Chỉ tạo query có unit đi cùng namespace lấy từ địa chỉ/tòa trong OSM, không bịa mã tòa/căn hộ.

## Files

| File | Cách dùng |
|---|---|
| `queries_10k.parquet`, `queries_10k.jsonl` | Hai định dạng của cùng 10.000 dòng |
| `train.parquet`, `dev_synthetic.parquet`, `test_synthetic.parquet` | Các split của cùng bảng query |
| `corpus_search_view.parquet` | Full catalog view: tên/alias/địa chỉ đã chuẩn hóa, cờ search, tọa độ; giữ tên gốc để audit |
| `origin_display_candidates.parquet` | Origin pool đã qua display gate: 8131 records |
| `entity_resolution.parquet`, `entity_candidates.parquet`, `entity_policy.json` | Mapping thực thể, cặp nghi trùng, policy/evidence |
| `entity_resolution.py` | Quy tắc collapse và adapter top-k có thể bật/tắt |
| `selected_pois.parquet` | 2.000 targets, subset của search view |
| `corpus_split_map.parquet` | Nhóm và split cho toàn corpus |
| `prior_split_map.parquet` | Lineage để POI held-out của v2 không trở thành POI train khi sửa generator |
| `typing_sessions.parquet` | **200 phiên / 4276 trạng thái** bổ sung, không cộng vào 10k hoặc coi là intent độc lập |
| `address_field_audit.parquet` | Audit từng trường địa chỉ trước khi sinh query, gồm giá trị raw và quyết định |
| `street_vocabulary.parquet` | Từ vựng phố/road-ref quan sát trong địa chỉ OSM và số object; chưa phải gazetteer đường độc lập |
| `generation_policy.json`, `validation_report.json`, `dataset_manifest.json` | Policy, coverage, kiểm tra và hashes |
| `editorial_seeds.json` | Seed viết riêng theo POI; mã dùng một seed/POI trong v3, các seed còn lại giữ provenance |
| `review_worksheet.jsonl`, `inspection_sample_100.jsonl` | Chỉ lấy từ train/dev; không chứa test |
| `build_queries.py`, `package_dataset.py` | Mã tái tạo và đóng gói |
| Hai tài liệu `HANOI_POI_*.md` | Bản thiết kế và tech stack đồng bộ với dataset v3 |

## Các track

| Track | Số dòng |
|---|---:|
| `retrieval_core` | 6,500 |
| `ambiguity_stress` | 1,788 |
| `ime_keystream` | 673 |
| `autocomplete` | 423 |
| `structured_code` | 616 |

- `retrieval_core`: query tương đối đủ thông tin; `main_metric_candidate` là cờ chọn phạm vi kỹ thuật cho eval chính, chưa phải nhãn đã chấm.
- `autocomplete`: prefix còn lại; đo riêng theo độ dài và acceptable set.
- `ambiguity_stress`: query dài không quá 3 ký tự hoặc có hơn 50 POI khớp policy; không trộn vào MRR/Hit@1 chính.
- `structured_code`: mã/label cực ngắn được phát hiện theo rule; đánh giá riêng, có namespace từ nguồn khi có.
- `ime_keystream`: chuỗi phím Telex/VNI mô phỏng; không mặc định text này xuất hiện trong request của app.

Có 8453 chuỗi khác nhau sau casefold. Query ngắn như `h` được lặp giữa nhiều target families có chủ đích: các dòng này biểu diễn nhiều tình huống khởi đầu giống nhau, không phải các đáp án đơn khác nhau. Query ID là duy nhất. Không dedup chuỗi toàn cục để rồi làm mất coverage prefix 1–2 ký tự; không dùng số trạng thái làm số intent độc lập.

| Loại query | Số dòng |
|---|---:|
| `editorial_paraphrase` | 45 |
| `prefix_1` | 450 |
| `telex_raw_keys` | 337 |
| `abbreviation` | 57 |
| `no_diacritics` | 1,668 |
| `prefix_2` | 473 |
| `vni_raw_keys` | 336 |
| `name_address` | 431 |
| `prefix_3` | 326 |
| `wrong_tone` | 333 |
| `prefix_4` | 88 |
| `partial_diacritics` | 319 |
| `prefix_8` | 250 |
| `address_first` | 105 |
| `prefix_5` | 290 |
| `adjacent_transpose` | 1,388 |
| `search_phrase` | 885 |
| `unit_with_namespace` | 63 |
| `prefix_6` | 9 |
| `prefix_7` | 91 |
| `clean_name` | 1,456 |
| `name_street` | 101 |
| `address_exact` | 499 |

Các dòng dài 1/2/3 ký tự thực tế: `{"1": 473, "2": 529, "3": 422}`.

Thứ tự phân track: raw IME → structured code → ambiguity stress → autocomplete → retrieval core. Cờ `is_structured_code` vẫn được giữ nếu dòng đó thuộc IME.

## Chuỗi gõ và IME

`typing_sessions.parquet` có `session_id`, `event_index`, `keystroke_index`, `input_event`, `query`, `is_final`, `input_mode`, `query_surface`, target, family và split. Toàn bộ trạng thái của một phiên giữ cùng target/family/split.

`direct_unicode` mô phỏng nối từng ký tự Unicode, không đo số lần bấm bàn phím vật lý ngoài thực tế. `telex`/`vni` mô phỏng chuỗi phím theo rule, gồm trạng thái đang gõ dở. **Chưa mô phỏng trình soạn thảo/IME của Android/iOS/web**, chưa xác minh composition events, sửa bằng backspace hay đặt con trỏ. `ime_engine_verified=false`. Không dùng keystream như committed text khi train/eval serving nếu app không phát ra dạng đó.

Sai dấu (`wrong_tone`) đổi một dấu thanh; mất dấu từng phần (`partial_diacritics`) bỏ dấu thanh ở một vị trí và giữ phần còn lại. Bỏ dấu toàn bộ là loại riêng. Không thay số nhà, slash hoặc mã unit khi tạo lỗi ký tự.

## Typo, mã ngắn và lý do quyết định

`adjacent_transpose` chỉ hoán đổi hai chữ cái khác nhau đứng liền nhau. Không có cặp phù hợp thì không sinh thao tác đó; không lặp ký tự cuối để đủ số dòng. `typo_source`/`typo_result` lưu cặp trước/sau để audit độc lập. Những record như `7`, `B12`, `B11C` không bị đổi thành mã mới dưới nhãn typo.

Telex xử lý cụm nguồn `ươ` cùng nhau: `trường → truowngf`, `đường → dduowngf`. Không thay mọi chuỗi Latin `uwow` bằng tìm/thay văn bản. Đây vẫn là keystream theo rule, chưa replay qua IME thực và không khẳng định tối giản cho mọi từ.

`review_reasons[]`, `main_metric_exclusion_reasons[]`, `training_exclusion_reasons[]`, `missing_address_sibling` ghi quyết định cho từng dòng. `main_metric_candidate` đúng khi danh sách lý do loại main rỗng; trường review không tự đồng nghĩa loại main. Cross-split, thiếu địa chỉ sibling, nhiều compatible IDs và track riêng có lý do tách biệt.

`is_structured_code` là heuristic: label ≤2 ký tự, hoặc code Latin/số/dấu chấm/gạch nối dài ≤12 có chữ số. Không tuyên bố tên/code đó vô nghĩa. Có 125 targets thỏa rule. `namespace_fields_json` lưu street/housename có nguồn; `namespace_in_query` cho biết query có qualifier đó. Bare code giữ để diagnostic; không ép thành tên venue thông thường. `structured_metric_candidate` là cờ cho benchmark code riêng, không nằm trong `main_metric_candidate` hay core weak training. Không bịa namespace cho code thiếu metadata.

## Thực thể và top-5

`entity_group_id` luôn có (singleton nếu chưa gộp); `branch_id` chỉ sinh local ID khi có tag branch và địa chỉ đủ; `complex_id=null` khi không có bằng chứng membership. `complex_name_hint` từ housename không được coi là ID complex. Có 83 branch IDs có provenance; chưa gán complex ID nào.

Policy `entity-v1` tạo 1624 cặp cùng label/category trong 100 m, giữ dấu trong so tên. Chỉ 1 cặp đạt rule collapse: node–way, tên venue/loại/địa chỉ đầy đủ giống nhau, không xung đột branch/ref/unit/level/brand/operator, node trong polygon hợp lệ và node chỉ khớp một polygon. Đây là suy luận bảo thủ, không phải xác minh thực thể. Giữ riêng platform, entrance, stops. Không nối chuỗi các cặp gần nhau thành một entity.

`collapse_ranked_candidates` nhận danh sách đã xếp hạng, giữ representative có hạng cao nhất mỗi entity rồi backfill đến top-k từ danh sách đầu vào sâu hơn. Có `enabled=False` làm đối chứng. Không xóa hay sửa canonical nguồn. Adapter đã có code/test; chưa tích hợp vào search API/UI vì các service đó chưa được xây trong gói dữ liệu này. Khi chấm kết quả đã collapse, resolve qrels và kết quả qua cùng entity policy, giữ cả IDs gốc để audit; không trộn điểm số canonical và entity-level.

## Làm sạch trước sinh

Chuẩn hóa NFKC và mapping confusable rõ ràng `ᴄ → c`, giữ raw để truy vết. Đây là mapping có kiểm soát cho ký tự phát hiện, không phải chuẩn hóa mọi confusable Unicode; không tự chuyển mọi chữ Cyrillic/Greek thành Latin. Trường có underscore, signature mã nội bộ/cadastral, địa chỉ dán nhầm hoặc cấu trúc không xác định bị chặn/giữ riêng. Kết quả: **209 trường địa chỉ bị chặn**, **61 trường chưa đủ điều kiện** không dùng sinh query. Tên có underscore cũng không dùng làm search label ở policy này.

Road-ref có regex riêng cho QL/ĐT/ĐH/CT; tên phố còn lại qua kiểm tra từ vựng hình thức. **Chưa xác nhận từng tên với mạng đường hoặc gazetteer độc lập**. Vì vậy dùng `road_name_lexically_plausible`, không gọi `verified_street`. Không sửa raw corpus/OSM hoặc xóa POI chỉ vì một trường địa chỉ bị chặn; POI có tên hợp lệ vẫn có thể tìm theo tên.

## Split và nhãn

| Split | Số dòng |
|---|---:|
| `train` | 8,190 |
| `dev_synthetic` | 925 |
| `test_synthetic` | 885 |

Giữ nhóm name/alias/brand/địa chỉ và lineage của v2. Khi nhóm mới chạm held-out, ưu tiên `test > dev > train`. Không ép về 8k/1k/1k bằng cách chuyển POI test sang train. Query chung ở stress track có thể xuất hiện ở nhiều split; `cross_split_compatible` và `normalized_query_cross_split` chặn trường hợp không phù hợp khỏi supervised train/eval chính.

`intended_poi_id` là nguồn sinh, không mặc định đáp án duy nhất. `known_compatible_poi_ids` tìm theo policy trên search view đầy đủ, có thể thừa/thiếu; không phải qrels đã adjudicate. `supervised_training_eligible=true` hiện có 3927 dòng để thử nhãn yếu. V2 không cung cấp negative đã xác nhận. Các POI dev/test không được dùng làm positive hoặc negative train; vẫn được encode bằng checkpoint frozen để lập retrieval index.

Test v2 đã được xem khi sửa generator nên không tiếp tục gọi là locked. Test v3 là **provisional_not_locked**; cần một lần freeze độc lập sau khi người dùng hoàn thiện nhãn/quy trình. Worksheet chỉ gồm train/dev. Phần chấm nhãn và quyết định ngưỡng do người dùng xử lý sau; không tạo nhãn human giả.

## Nguồn sinh và tái tạo

| Phương pháp | Số dòng |
|---|---:|
| `codex_authored_per_poi` | 45 |
| `controlled_typing_rule` | 5,685 |
| `controlled_ime_key_rule` | 673 |
| `grounded_composition` | 3,597 |

Đây là synthetic pilot: seed Codex viết riêng + ghép trường nguồn + rules, không phải 10.000 lần gọi LLM độc lập hay log người dùng. Không có model training, chất lượng search hoặc latency được đo trong lần build này.

```bash
python -m pip install pyarrow==25.0.1 shapely==2.1.2
python build_queries.py /path/hanoi_poi_canonical.parquet /path/hanoi_queries_10k
python package_dataset.py
```

Đặt scripts, `editorial_seeds.json` và `prior_split_map.parquet` cùng thư mục output. Chạy build tạo dữ liệu; hai tài liệu đồng bộ được giữ cùng folder khi đóng gói. Seed 20260913. SHA-256 corpus đầu vào: `a485d688feabe1da530b593d416d90d1c01253bb385b5695791a0a7980ee66bb`. Kiểm tra tự động và manifest chỉ chứng minh tính nhất quán theo policy, không chứng minh coverage thực địa.

Dữ liệu địa điểm dẫn xuất từ © OpenStreetMap contributors, [ODbL](https://www.openstreetmap.org/copyright).
