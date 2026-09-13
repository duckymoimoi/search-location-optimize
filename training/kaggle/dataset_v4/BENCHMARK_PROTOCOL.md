# Protocol Stage 1 cho hnq20k-pilot-v4

## Freeze và phân vai dữ liệu

Corpus vẫn là `hn-260910-7f1b69b167`, search view `hn-search-view-v3`, gồm 45.693 destination searchable. Bundle mới mang version `hnq20k-pilot-v4`; 10k record cũ vẫn giữ nguyên dataset_version v3 để bảo toàn nguồn gốc. Không random-split bảng tổng, không lấy mọi dòng train làm nhãn đơn đích.

- `train_eligible_v4.parquet`: nhãn yếu đơn đích theo policy, dùng cho MNRL có kiểm soát false negatives. Cùng entity, target, query và known-compatible không được coi nhau là negative trong batch.
- `dev_synthetic.parquet`: chọn cấu hình, tách track bằng loader. Phần dev mới là 2.000 dòng, thêm vào dev v3.
- `test_synthetic.parquet`: đúng 885 dòng test v3 đã từng được xem. Đây là frozen regression/comparison set; main core có 391 dòng.
- `architecture_holdout.parquet`: 3.000 dòng thuộc target/family/lineage/entity mới đối với mọi query cũ và khác train/dev mới. POI có trong catalog là điều kiện cần để retrieval, không phải leakage query label.

Holdout chưa được chạy qua model trong công việc tạo bundle này. Nó được tạo cùng họ generator với train/dev, nên chỉ kiểm tra khả năng tổng quát hóa sang family mới trong synthetic benchmark. Không coi đó là traffic thật hay holdout được một nhóm độc lập xây dựng. File tổng chứa cả holdout để đóng gói; việc không mở để tune do workflow thực nghiệm bảo đảm. Không dùng ví dụ holdout cho sửa analyzer hoặc prompt sinh dữ liệu sau khi bắt đầu benchmark.

## Chất lượng trước, serving sau

1. Giữ checkpoint E5 fine-tuned hiện tại, freeze hash checkpoint, POI text builder, tokenizer, tiền tố query/passage, pooling và vector normalization. Bundle này không chứa checkpoint hay embeddings đã train.
2. Đăng ký trước một ma trận nhỏ lexical, exact dense và RRF. Lexical gồm exact/name, accent-folded, prefix/edge-ngram, address và source alias. Nếu thử analyzer mới, chỉ chọn bằng dev.
3. So sánh ở final K = 5, 20, 50 trên toàn bộ destination catalog. Mỗi branch hybrid có depth cố định, chẳng hạn 50 hoặc 100; RRF rồi cắt final K. Báo branch depth, số candidate union, RRF constant và policy tie-break. Không đưa số 50/100 thành tham số tune sau khi đã xem holdout.
4. Có thể chọn routing query-only dựa trên tín hiệu lúc phục vụ: text, độ dài, syntax địa chỉ/mã, trạng thái input được client gửi, confidence retrieval. Không dùng case_type, track, clean_query, intended_poi_id hay mutation metadata làm input router.
5. Khóa analyzer, field weights, RRF, candidate depths, router và selection rule. Chạy frozen comparison/holdout rồi paired cluster bootstrap theo query_family_id; bổ sung sensitivity theo leakage_group_id nếu nhiều family chung group.
6. Sau khi chốt chất lượng, thay exact bằng ANN với cùng embeddings, similarity và filter. Báo overlap ANN recall@K so với exact, sau đó báo mức giảm CandidateHit/MRR end-to-end.
7. Benchmark p50/p95/p99, QPS, index size, peak memory, concurrency, warm-up, cache và phần cứng. So sánh cả cùng final K và cùng tài nguyên/latency. Thời gian train mỗi epoch không thay thế query inference latency.

Nếu fine-tune lại bằng dữ liệu mới: so sánh checkpoint hiện tại và checkpoint mở rộng trên cùng dev; chỉ chạy holdout sau khi khóa lựa chọn. Kết quả test v3 đã công bố không phải bằng chứng blind mới.

## Metric theo track

| Track | Metric và cách diễn giải |
|---|---|
| Retrieval core eligible | CandidateHit@20/50, Hit@1/5, MRR@10; eligibility_v4 là nguồn quyết định |
| Autocomplete | Hit@5, MRR@5 theo độ dài; intent target là nhãn yếu, không phải đáp án duy nhất cho mọi prefix |
| Ambiguity stress | CandidateHit@K theo đích giả định và coverage/recall trên known-compatible báo riêng; không ép Hit@1 |
| IME keystream | Diagnostic theo Telex/VNI; chưa replay qua engine thật nên không dùng làm gate |
| Structured code | Case study, chia có/không namespace; metric subset còn nhỏ, không suy rộng |

Recall trên known-compatible phải ghi rõ nhãn chưa đầy đủ. Khi compatible count rất lớn, recall@K có trần K/count thấp; đừng so trực tiếp nó với recall trên query duy nhất. Nếu collapse entity, giải cả candidates và qrels qua cùng entity mapping rồi báo riêng so với canonical-ID metric.

Typing sessions nằm ở bảng riêng: đo bước sớm nhất target vào top-K, bước sớm nhất từ đó target giữ top-K đến cuối, tỷ lệ session chưa tìm được và top-K churn. Không bỏ các session không tìm được khi tính trung bình. Đây là trạng thái ký tự Unicode được mô phỏng, không phải thời gian hay hành vi phím vật lý đo được.

Không có một ngưỡng pass chung cho toàn bộ 20k. Quota cân bằng là thiết kế đánh giá độ bền, không phải phân bố traffic. Quyết định chọn kiến trúc dựa trên rule khóa trước, khoảng tin cậy, guardrail từng track và ngân sách serving.

## Origin và Stage 2

Destination sampling chỉ phụ thuộc destination_searchable. Origin pool có nhãn hiển thị dùng được vẫn là artifact riêng. origin_search_eligible không có nghĩa pickup_access_verified; corpus hiện chưa có điểm đón được xác minh hay routing point đủ dùng.

Dataset này phục vụ Stage 1. Nó không thêm nhãn cá nhân hóa, origin/time/user counterfactual hoặc bằng chứng mô hình hiểu hành vi người dùng. Hoàn tất benchmark Stage 1 trước khi xây Stage 2.
