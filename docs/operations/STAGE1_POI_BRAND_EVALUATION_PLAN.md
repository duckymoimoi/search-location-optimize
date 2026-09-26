# Kế hoạch hoàn thiện đánh giá Stage 1: POI/entity và brand

**Trạng thái:** kế hoạch, chưa thực thi. Không sửa Gold đã khóa hoặc dùng kết quả
baseline để đổi nhãn. Corpus/index đánh giá hiện hành là v3.

## 1. Phạm vi và quyết định

- Giữ nguyên `gold_stage1_v2_1` làm test POI/entity: 200 target, 800 query,
  820 qrels theo query và 200 q01 prefix-evidence. Gold v2 cũ cũng bất biến.
- Xây `gold_stage1_brand_v1` riêng để đánh giá bare brand, alias đã xác minh,
  lỗi tên brand, namespace và autocomplete ở mức brand group. Train brand là
  release khác; không lấy một chi nhánh làm positive duy nhất cho bare brand.
- Không tạo `address_scope_eval_v1` trong kế hoạch này. Vấn đề số nhà/đường
  được xử lý bằng lexical tìm trên các trường riêng; không đưa wrong-number
  hoặc same-street fallback thành positive cho encoder. Sau khi chốt phạm vi,
  cập nhật registry/tài liệu để address suite không còn bị hiểu là điều kiện
  bắt buộc để hoàn thành đánh giá Stage 1 hiện hành.
- Không gộp điểm POI và brand thành một chỉ số. Báo riêng retrieval candidate,
  thứ hạng cuối, prefix và từng exposure class.

## 2. Đầu vào đã có và khoảng trống

| Đầu vào | Hiện trạng | Việc cần làm |
|---|---|---|
| `stage1_eval_suite_v2/gold_stage1_v2_1/` | Đã khóa, baseline corpus v3 đã chạy | Chỉ replay/đọc; không tái author theo miss list |
| `train_stage1_brand_v1/` và `train_stage1_brand_lookup_v2/` | Membership/lookup đã khóa, nguồn gốc corpus v1 | Tạo view/phiên bản tương thích v3, không sửa tại chỗ |
| `train_stage1_brand_queries_v2/brand_authoring_packet_v2.jsonl` | 381 intent sau merge ATM BIDV và loại descriptor generic | Là nguồn intent hiện hành để đối chiếu/split |
| `train_stage1_brand_queries_v1/staging/` | 381 intent, 1.156 query, 34.041 qrel rows; validator PASS | Reconcile với packet v2, QA và phát hành train/eval riêng; staging chưa là Gold |
| `stage1_eval_suite_v2/suite_registry.json` | POI v2.1 active; brand và address còn `pending` | Chỉ cập nhật sau khi brand Gold được khóa và phạm vi address được chốt |

Read-only audit ban đầu: 430 accepted brand-member POI ID của qrels hiện tại
không còn trong corpus v3, ảnh hưởng 271 query nhưng chưa query nào mất toàn
bộ positive. Có 34 POI thuộc Gold POI v2.1 trong accepted brand membership.
Bộ query hiện có không có verified-alias row; `space_variant` chỉ 23 row.
Những số này là đầu vào cho audit, không phải quota để bịa thêm query.

## 3. Split và chống leakage

1. Chốt bảng `brand_family_id → brand_group_id/namespace → accepted POI IDs`
   trên corpus v3. Truy nguồn 430 ID vắng mặt bằng migration/cleaning map;
   chỉ chuyển positive khi chứng minh cùng POI thật. `needs_review` và alias
   chưa xác minh không được tự nhập positive pool.
2. Reconcile từng intent của packet v2 với query staging v1. Áp quyết định
   merge/exclude trước khi chia. Audit bare-brand còn nằm trong train POI;
   chuyển hoặc loại row singleton sai trước khi compile train views.
3. Chia **theo `brand_family_id`**, không chia ngẫu nhiên query hoặc chi nhánh:
   mọi namespace, alias và variant của một family ở cùng split. Dự kiến
   khoảng 60–80 family test, 30–40 family dev, phần còn lại train trong
   khoảng 320 family đang có; chốt số cuối sau khi phân tầng theo số branch,
   namespace, tên Việt/Anh, acronym và mức nhập nhằng. Không ép quota làm
   hỏng độ tự nhiên hoặc thiếu nhóm quan trọng.
4. Eval family không xuất hiện trong **brand-query train**. Tuy vậy member POI
   của family có thể đã xuất hiện trong POI branch-query train hoặc corpus
   index: gắn exposure `brand_query_heldout / branch_seen` tương ứng, không
   gọi mặc định là `cold_brand`. Strict-cold-brand chỉ công bố nếu đã loại
   toàn bộ family/member liên quan khỏi mọi positive train và distillation.
5. Với brand train, loại Gold POI v2.1 và các entity-equivalent ID của chúng
   khỏi positive sampling; giữ mask để chúng không thành false negative.
   Family không còn positive train hợp lệ thì bỏ khỏi train, không đổi Gold.
   Kiểm tra trùng query theo normalized text, accent-fold, alias và near-dup
   giữa train/dev/test, đồng thời so với Gold POI.

Membership là sidecar chung để resolve group; **không tách bảng membership
thành hai tập POI**. Brand eval qrels dùng toàn bộ member tương thích, còn
brand train sampler chỉ lấy positive đủ điều kiện của train và mask các member
khác. Ghi hash của split, membership v3 view, corpus, normalizer và qrels.

## 4. Xây brand dev/test và train

- Từ family test đã chọn, kiểm tra độc lập tên chuẩn, namespace, alias và
  member set trước khi khóa. Có canonical bare brand, namespace-qualified,
  typo/IME/space tự nhiên và prefix `group_ready` theo khả năng áp dụng; bổ
  sung verified alias bằng nguồn chứng cứ, không tự đoán acronym. Không copy
  cùng lỗi cho từng chi nhánh; một brand query trỏ đến group/pool tương thích.
- Từ family dev tạo bộ nhỏ cùng schema để chọn model/policy. Không nhìn test
  Gold để sửa query hoặc qrels. Nếu cần thêm query, author sau khi family split
  và không dùng bề mặt query của test làm template cho train.
- Family train giữ provenance `brand_queries`, compile cùng POI queries qua
  unified query/relation views; brand positives là pool/mask, không ép
  diagonal single-positive. Trainer chưa hỗ trợ multi-positive mask thì chưa
  merge brand track vào training; dùng thí nghiệm POI-only làm đối chứng.
- Validator phải kiểm tra 100% ID tồn tại và searchable trong corpus v3,
  namespace đúng, alias có evidence, query resolve được positive, query/Qrel
  parity, split family-disjoint, không có Gold target trong train positives,
  không có query leakage và mọi ngoại lệ được adjudicate.

## 5. Đánh giá và điều kiện hoàn tất

1. Replay POI Gold v2.1 không đổi: full-query theo q01–q04, stratum,
   difficulty/exposure; Hit@1/5/20/50, MRR@10, candidate miss và phân tích
   miss theo target vắng/candidate miss/rank miss. Prefix q01 báo raw FHC/SHC/
   AUC **riêng** với phần từ `entity_ready`; `SHC(w=3)` sau mốc này chỉ có
   20/200 case đủ ba checkpoint trong release hiện tại, nên luôn ghi mẫu số.
2. Brand test chấm AnyCompatibleHit@K, group MRR, compatible coverage@K
   (phân tầng theo group size), namespace false-branch và prefix group-ready.
   Không dùng exact-branch Hit@1 cho bare brand. Báo family-weighted metrics
   và paired confidence interval; nhiều query/prefix của cùng family không
   được coi là mẫu độc lập.
3. So E0 (POI-only) với E1 (POI + brand) trên cùng train budget, corpus/index,
   candidate policy và split. Chỉ nhận E1 khi brand recall tăng mà POI q01,
   branch-specific và candidate recall không giảm quá ngưỡng được chốt **trước**
   khi mở test. Tách lexical raw, hybrid final API và model-only nếu có;
   hybrid-vs-lexical không chứng minh riêng tác dụng của encoder.
4. Xuất train manifest, dev manifest, brand Gold manifest/`LOCKED.json`,
   leakage/QA report và baseline report có hash. Khi đó cập nhật suite registry
   và docs phạm vi hai suite POI/entity + brand; giữ mọi release cũ để replay.

Không mở rộng Gold POI chỉ vì 200 case hoặc một baseline miss. Nếu cần ước lượng
traffic thực tế hay autocomplete entity-ready sớm hơn, tạo một supplement độc
lập từ nguồn query người dùng/đợt chọn mới, khóa trước khi xem challenger;
không sửa Gold v2.1 sau khóa.
