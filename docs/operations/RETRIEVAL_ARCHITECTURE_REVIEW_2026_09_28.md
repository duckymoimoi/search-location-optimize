# Review kiến trúc retrieval, train và benchmark — 2026-09-28

## Quyết định đề xuất

Chuyển baseline nghiên cứu sang **dense-first**. Bỏ giả định phải RRF đồng trọng số lexical+dense cho mọi query. Chưa xóa lexical hoặc Elasticsearch khỏi sản phẩm: giữ khả năng lookup tên/alias, prefix ngắn, mã/số nhà, brand membership và fallback khi encoder lỗi; đo đóng góp riêng trước khi quyết định bật từng nhánh.

Đây là review và đề xuất, chưa đổi runtime. Đã đọc working tree hiện tại, các summary local, code train/bench và kiểm tra `/health`: API 8000 zero-shot, 8001 6k dev-lock, 8002 Brand+POI đều trả `ok`, CUDA, corpus 179.209. Không chạy lại train hay benchmark GPU; các số chất lượng/latency bên dưới là kết quả đã lưu, không phải phép đo mới. Working tree có nhiều thay đổi chưa commit.

## Bằng chứng trực tiếp

Nguồn: `artifacts/results/stage1_v6_6k_devlock_top100/summary.json`; runner `apps/poi-search/bench/stage1_three_way_top100.py`. Cùng 800 query Gold POI v2.1, top 100, checkpoint 6k dev-lock.

| Retrieval | Hit@1 | Hit@20 | Hit@100 | p50 ms | p95 ms |
|---|---:|---:|---:|---:|---:|
| Lexical | 52,875% | 75,125% | 86,250% | 13,71 | 30,57 |
| Dense ANN | 94,125% | 98,750% | 99,125% | 22,62 | 57,38 |
| Exact dense GPU | 94,625% | 99,250% | 99,875% | 10,36 | 20,61 |
| Exact dense + lexical RRF k=60 | 77,875% | 98,750% | 99,500% | 24,84 | 45,42 |

- RRF cứu rank 1 cho 19 query nhưng làm mất rank 1 của 153 query: net -134/800 = -16,75 điểm phần trăm.
- Lexical tự đứng rank 1 ở 9 query exact dense không đứng rank 1. Đây không phải cùng đại lượng với 19 query được fusion cứu.
- Lexical cứu 1 query dense miss@20 và 1 query dense miss@100. Với top 100, lợi ích oracle về any-hit tối đa chỉ +0,125 điểm phần trăm trên suite này; không suy rộng sang brand, prefix hoặc địa chỉ chưa được chấm.
- ANN mất 0,5 điểm Hit@1 và 0,75 điểm Hit@100 so exact. Gap này đáng đo nhưng nhỏ hơn nhiều mức tổn hại của RRF đang thử.
- Benchmark lưu summary, không lưu top IDs/scores và rank theo query ra output. `inputs/queries.jsonl` cũng thiếu query_id/case_id. Hiện không thể audit trực tiếp danh tính 153 query chỉ từ output này.

Không ghép bảng này với API hybrid như một ablation cùng điều kiện. API hybrid 6k đã lưu Hit@1 87,625%, Hit@20 98%, server p50/p95 79,71/266,63 ms; dùng depth/budget 50, ANN, dedup, heuristic ranking. Nguồn: `artifacts/results/stage1_v6_6k_devlock_hybrid/summary.json`.

## Vấn đề code và đo lường

### 1. Fusion cho nhánh lexical quá nhiều quyền

`ranking.py:rrf` và `_hybrid_evidence` dùng tổng nghịch đảo thứ hạng không trọng số. Với k=60, ứng viên rank 20 ở cả hai nhánh nhận 2/80=0,025; ứng viên chỉ có dense rank 1 nhận 1/61≈0,0164. Consensus có thể đẩy kết quả dense rất tốt xuống dưới. Sau fine-tune, giả định hai nhánh có độ tin cậy tương đương không được số liệu ủng hộ.

`es_query.py:search` chỉ trả IDs và timing, bỏ `_score`. Ranker không còn cosine score/margin để đánh giá mức chắc chắn của dense. Nên giữ score gốc, branch rank, match evidence và nguồn candidate. Cosine không mặc nhiên là xác suất; gate phải được kiểm định trên dev.

### 2. dense_only chưa phải dense thuần

`pipeline.py:retrieve_detailed` có profile `dense_only`, nhưng `suggest` vẫn gọi `candidate_documents` và `rank_candidates`. `ranking.py:rank_candidates_traced` luôn đi qua `prioritize_name_address` rồi `prioritize_name_match_quality` khi policy bật, kể cả không có origin.

`prioritize_name_match_quality` sort theo match level, accent, span và token coverage trước thứ tự retrieval. Đây là thay đổi thứ hạng cứng, không chỉ cộng một bonus nhỏ. Không thể quy toàn bộ regression của app cho lexical retrieval. Cần ablation giữ nguyên dense order, rồi bật từng bước dedup, name/address và geo.

Candidate budget 50 được áp trước các bước xếp hạng. Nếu fusion/cap loại mất POI đúng, rerank không cứu được. Trace hiện có các stage IDs là nền tảng tốt để định vị điểm mất candidate.

### 3. Chuẩn hóa train và serving khác nhau

Trainer/evaluator Kaggle encode `query_text` trực tiếp. Serving và benchmark top100 encode `glue_code_spans(query)`. Kiểm tra 800 input local thấy 21 query bị thay đổi, ví dụ `274-276` thành `274276`, `14-16` thành `1416`.

Hàm hiện ghép mọi span nối bằng dấu chấm/gạch ngang, không bắt buộc span chứa cả chữ và số. Việc áp quy tắc phục vụ lexical analyzer lên encoder có thể làm mất ý nghĩa khoảng số nhà. Đây là nguy cơ có bằng chứng code; chưa chứng minh nó gây cụ thể bao nhiêu regression. Cần tách normalized input cho encoder khỏi keys dành cho lexical, dùng cùng encoder normalization khi train/eval/serve và version hóa nó.

Gold Hit@1 94,75% trên Kaggle và 94,625% ở exact local không hoàn toàn trùng protocol. Chưa đủ evidence để gán chênh lệch duy nhất cho normalizer.

### 4. Latency chưa phải SLA sản phẩm

Runner top100 thực hiện lexical → encode → ANN → exact theo thứ tự cố định. Latency exact+lexical được cộng tuần tự. Runtime thực tế submit lexical sang thread pool trước khi encode/dense, nên phần retrieval là đường găng của các nhánh, không phải luôn tổng hai nhánh.

Exact GPU đã có ma trận corpus trong VRAM, không gồm HTTP API, hydrate documents, dedup, rank, serialize response hoặc queue dưới tải. ANN gồm round-trip Elasticsearch. So sánh hữu ích cho chọn backend, nhưng chưa chứng minh full API dense-only có p95 20,61 ms.

Không có warmup phase riêng, randomized mode order, concurrency sweep hoặc repeated-run distribution trong runner này. API benchmark cũ cũng tuần tự; evidence W3 ghi nhận nhiều API cùng dùng GPU. `Runtime.encode` có lock và encode một query mỗi lần: cần đo queue time khi concurrency tăng.

Ma trận 179.209 × 384 float32 chỉ khoảng 262,5 MiB, chưa gồm model, metadata và workspace. Exact GPU là ứng viên hợp lý để thử ở quy mô hiện tại. Chưa có benchmark throughput/tăng corpus để quyết định bỏ ANN trong production.

## Train: đã cải thiện POI nhưng chưa giải xong brand

Run diagnostic 6k đầu tiên dùng Gold trong chọn checkpoint và có Gold negatives. Run **6k dev-lock riêng** đã sửa protocol; không đánh đồng hai run. Summary dev-lock ghi `checkpoint_selection=dev_only`; code có kiểm tra Gold overlap và đánh giá Gold sau lock.

Tuy nhiên, cùng Gold đã được xem qua nhiều vòng nghiên cứu. Dev-only trong từng run không khiến cả quá trình thiết kế trở thành untouched test. Nên giữ Gold hiện tại làm regression suite và có holdout mới, độc lập, khóa trước quyết định cuối.

| Exact dense brand, family mean Hit@1 | Kết quả |
|---|---:|
| Zero-shot | khoảng 67,4% |
| POI-only 6k | khoảng 55,2% |
| Brand+POI mix | khoảng 57,8% |

Nguồn: W3 `07_PREFIX_AND_BRAND.md` và summary `output_stage1_v6_brand_poi_mix/brand_poi_mix/summary.json`. Mix giữ POI Hit@1 94,75% nhưng chưa khôi phục brand về zero-shot. Chưa có bằng chứng lexical generic sẽ giải quyết hết gap này.

Các điểm cần sửa hoặc làm rõ trước train tiếp:

1. **Weight bị áp hai lần:** trainer 6k `sample_epoch_rows` giữ row theo `sample_weight`, sau đó `train_one_epoch` lại nhân loss với cùng weight. Với w=0,25, hệ số sampling × loss thô là 0,0625 trước chuẩn hóa batch. Không nên mô tả là chỉ giảm còn 25%. Tách `sampling_probability` và `loss_weight`, quyết định chủ đích và ablate; không mặc định tăng weight chắc chắn cải thiện.
2. **Mix thay objective negatives:** trainer 6k mở toàn batch trong `allowed_mask` rồi mask ignore. Trainer mix khởi tạo mask false, chỉ mở positives/negatives riêng của từng query. Do đó cùng batch không đồng nghĩa dùng in-batch negatives. Cần ghi rõ và so sánh có kiểm soát.
3. **Brand negatives còn dễ:** `brand_rows` lấy 4 negatives random; positives tối đa 4 được chọn một lần khi tạo rows, chưa resample theo epoch. Thử hard negatives sai brand/namespace/area nhưng không loại nhầm chi nhánh hợp lệ.
4. **Epoch mix không bao phủ toàn bộ POI train:** số batch phụ thuộc số brand rows. Summary báo 196 steps, mỗi step 12 POI: 2.352 POI selections/epoch, so với 32.394 query POI train. Đây là rehearsal subset, không phải một lượt qua toàn bộ 6k data.
5. **Hai intent có semantics khác:** truy vấn chi nhánh có thể cần đẩy chi nhánh khác xuống; bare brand có thể chấp nhận nhiều chi nhánh. Quy tắc positive/negative/mask phải theo intent và namespace, không chỉ theo cùng tên brand.

Prefix suite hiện có 180/200 case chỉ entity-ready tại ký tự cuối, SHC(w=3) chỉ có 20 case. Điểm prefix cao chưa đủ chứng minh autocomplete cho prefix ngắn. Address-scope chưa có eval; không dùng Gold POI để kết luận bỏ mọi xử lý số nhà.

## Cấu trúc nên hướng tới

Một API, một encoder release đang chọn, các thành phần tách được để ablate:

1. Query interpretation: giữ raw text; phân biệt entity/brand/address/prefix khi đủ bằng chứng; chuẩn hóa có version.
2. Dense retriever: trả ID, score, rank; backend exact GPU hoặc ANN có cùng interface.
3. Structured lookup tùy intent: alias/brand membership, house+street/code, prefix. Đây là vai trò chức năng; không bắt buộc mọi lookup phải là BM25 rộng.
4. Candidate assembly: giữ dense order mặc định; lookup chỉ thêm/promote khi có bằng chứng đủ mạnh được dev kiểm định. Không RRF đồng trọng số mặc định.
5. Ranking: geo chỉ trong tập phù hợp intent; heuristics tên/địa chỉ bật độc lập và phải chứng minh lợi ích.
6. Document store và observability: hydrate metadata, trace source/rank/score và timing từng stage.

Giữ lexical fallback khi encoder lỗi là lựa chọn vận hành, tách khỏi quyết định chất lượng ranking. Giữ Elasticsearch lúc đầu vì runtime còn dùng `_mget`, map catalog, origin lookup và nearby geo search; bỏ BM25 khỏi đường chính không đồng nghĩa bỏ Elasticsearch.

Không cần tách microservice hay viết lại toàn repo ngay. Hợp nhất logic train/eval dùng chung thay vì copy kernel cho mỗi thí nghiệm; kernel Kaggle chỉ giữ config và entrypoint. Manifest release phải pin checkpoint hash, corpus/ID-map hash, normalizer, passage builder, policy hash, index mapping, candidate budget, code revision. Devlock compose hiện chưa đặt release/embedding-space IDs riêng như mix, dễ gây nhầm provenance.

Tài liệu hiện lệch trạng thái: `CURRENT_STATE.md` còn tập trung run diagnostic cũ và ghi E1 chưa chạy; W3 và runtime đã có nhánh dev-lock/mix. `training/stage1/README.md` vẫn trỏ corpus Hanoi và tài liệu đã bỏ. Cần phân loại rõ legacy/active; không dùng README cũ làm lệnh train hiện hành.

## Thứ tự thực hiện đề xuất

1. Chốt một checkpoint, corpus, normalizer và budget; sửa benchmark để ghi query_id/case_id, full top IDs/scores, accepted ranks, policy/hash, hardware và timing. Không ghi đè evidence cũ.
2. Trên dev, đo dense ANN thuần, exact dense thuần, hybrid hiện tại, dense + lookup có điều kiện. Với mỗi phương án, ablate dedup/name-address/name-quality/geo riêng. Dùng trace chỉ ra số query được cứu và bị hại mỗi stage.
3. Đo POI, brand family/namespace/coverage, prefix có readiness đủ đa dạng, số nhà/mã và địa lý. Report Hit@1/5/10/20/100, MRR@10, any-hit so với recall nhiều positives; bootstrap theo case/family, không coi các biến thể cùng case là độc lập.
4. Đo full endpoint cùng máy và chế độ tài nguyên, warmup, lặp lại, concurrency 1/4/8/16, QPS, p50/p95/p99, queue, encode, retrieval, hydration và ranking. Giữ background load được ghi rõ; không cần tắt dịch vụ người dùng để review này.
5. Chọn cấu hình trên dev, khóa trước khi đánh giá holdout mới. Chấp nhận dense-first khi giữ các slice quan trọng trong tolerance sản phẩm đã định trước và đáp ứng SLA. Lexical generic chỉ tiếp tục nằm trên đường chính nếu có incremental gain sau ranking, không chỉ oracle union.
6. Sau khi tách được lỗi serving, mới quyết định train tiếp: weight ablation, intent-aware masks, hard negatives cho brand, budget POI/brand rõ ràng. Không cố sửa regression do RRF bằng cách thêm dữ liệu train.

Quyết định có thể đưa ra ngay: dừng xem hybrid đồng trọng số là mặc định đúng; ưu tiên đo và triển khai thử dense-first. Quyết định còn thiếu evidence: xóa hoàn toàn lexical, thay ANN bằng exact GPU cho mọi tải, hoặc chọn mix làm model duy nhất cho toàn sản phẩm.
