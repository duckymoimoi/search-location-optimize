# Kế hoạch huấn luyện Stage 1 — Hanoi POI Search

## 1. Quyết định và phạm vi

Dataset dùng cho vòng đầu là `hnq10k-pilot-v3`, corpus `hn-260910-7f1b69b167`, search view `hn-search-view-v3`.

Vòng này chỉ huấn luyện và đánh giá **Stage 1 dense retrieval**. Lexical OpenSearch và hybrid RRF được tích hợp local sau khi chọn checkpoint dense. Stage 2, origin personalization, route và UI chưa nằm trong lượt train này.

Phân chia môi trường:

- **Kaggle GPU:** E5 zero-shot diagnostic, fine-tune, encode toàn corpus, exact-vector evaluation và xuất checkpoint.
- **Local:** OpenSearch lexical/ANN, hybrid RRF, API latency và serving benchmark.
- Không upload PBF lên Kaggle; chỉ upload search view và query artifacts tối thiểu.

Kaggle credential trên máy đã authenticate thành công và API đọc hoạt động. Chưa upload dataset, tạo notebook hay chạy kernel. Kaggle CLI chưa được cài global; khi triển khai dùng virtual environment riêng và không commit credential.

## 2. Kết quả preflight của dataset v3

Các kiểm tra độc lập đã qua:

- 30/30 artifact khớp byte size và SHA-256 trong manifest;
- JSONL và Parquet giống nhau hoàn toàn;
- train/dev/test là subset chính xác;
- 46.792 canonical IDs duy nhất, 45.693 destination searchable;
- 8.131 origin records có display label; pickup verified vẫn bằng 0;
- 10.000 query, 2.000 target, 5 query/target;
- query ID và `(query, target)` duy nhất;
- target luôn nằm trong compatible set;
- không leakage group xuyên split và không đưa prior held-out về train;
- 1.388 `adjacent_transpose` đều là phép đổi chỗ thật;
- Telex không còn chuỗi `uwow`; `trường → truowngf`, `đường → dduowngf`;
- reason lists tái tạo đúng các cờ review/main/training;
- entity policy tạo 46.791 groups từ 46.792 records, chỉ collapse một node–way pair theo rule bảo thủ.

Các tập dùng trong vòng train:

| Tập | Số dòng | Số target | Vai trò |
|---|---:|---:|---|
| Weak-supervised train | 3.927 | 1.103 | Fine-tune encoder |
| Main metric dev | 438 | không dùng để train | Chọn LR/epoch/checkpoint |
| Main metric test | 391 | không mở khi tune | Chấm một lần sau khi khóa config |
| Autocomplete | 423 | nhiều split | Diagnostic prefix |
| Ambiguity stress | 1.788 | nhiều split | Diagnostic, không dùng MRR/Hit@1 chính |
| IME keystream | 673 | nhiều split | Diagnostic riêng, không coi là committed text |
| Structured code | 616 | 125 structured targets | Diagnostic; chỉ 10 dòng đạt structured metric gate |

Human review được hoãn theo quyết định của chủ dự án. Điều này không chặn pilot training; mọi metric trước review phải mang nhãn `synthetic_weak_label_diagnostic` và không được diễn giải thành product uplift.

## 3. Input contract cho model

### 3.1 Query train

Chỉ lấy record thỏa:

```text
split == train
AND supervised_training_eligible == true
AND query_surface == committed_text
AND track == retrieval_core
```

Model chỉ nhận `query`. Không đưa `clean_query`, target name, coordinates, origin flags, reason fields hoặc IDs vào query encoder.

### 3.2 Positive passage

Join `intended_poi_id` với `corpus_search_view.parquet`. Passage v1:

```text
passage: {search_label}; {housenumber + street + subdistrict}; {category}; {search_aliases}
```

Quy tắc:

- bỏ trường rỗng và không lặp text đã có;
- giữ slash, số nhà và mã có nguồn;
- tên/địa chỉ đứng trước category/aliases;
- không ghép latitude/longitude, origin eligibility hoặc entity IDs vào text;
- pin chính xác passage builder version và hash output;
- audit tokenizer length trước train; khởi đầu query 64 tokens, passage 128 tokens.

### 3.3 Batch safety

Vì dùng in-batch negatives:

- một batch không chứa hai dòng có cùng positive canonical ID;
- không chứa hai positives thuộc cùng `entity_group_id`;
- tránh positive passage hoặc query text trùng trong batch;
- seed và batch order phải được lưu;
- dùng `NO_DUPLICATES` hoặc custom target-aware sampler.

Không dùng `known_compatible_poi_ids` ngoài target làm negatives. Vòng đầu chưa dùng hard negatives vì bộ v3 không có negative được xác nhận.

## 4. Model và loss

Backbone chính: `intfloat/multilingual-e5-small`, pin Hugging Face revision SHA.
Nhánh so sánh thuần Việt dùng `Qualcomm-AI-Research/BamiBERT` với cùng
mean-pooling, normalization và MNRL protocol. BamiBERT nhận raw Vietnamese;
không chọn raw PhoBERT ở vòng này vì PhoBERT cần external word segmentation,
dễ tạo thêm lỗi cho typo và prefix chưa hoàn thành. Model thắng được quyết định
bằng dev metrics và guardrails, không theo ưu tiên backbone.

- Query prefix: `query: `.
- Passage prefix: `passage: `.
- Mean pooling có attention mask.
- L2 normalize embeddings.
- Cosine similarity, exact search dùng inner product trên vectors đã normalize.
- Shared bi-encoder, full fine-tune với learning rate nhỏ.

Loss vòng đầu: `MultipleNegativesRankingLoss`. Nếu cần effective batch lớn hơn VRAM, thử `CachedMultipleNegativesRankingLoss`, không dùng gradient accumulation như một cách giả lập thêm in-batch negatives. Sentence Transformers khuyến nghị no-duplicate sampler cho cả hai loss: [loss documentation](https://sbert.net/docs/package_reference/sentence_transformer/losses.html) và [sampler documentation](https://sbert.net/docs/package_reference/sentence_transformer/sampler.html).

## 5. Ma trận thí nghiệm tối thiểu

Không chạy grid lớn ngay từ đầu.

| Run | Encoder | Train | Loss/batch | LR | Epoch | Mục đích |
|---|---|---|---|---:|---:|---|
| D0 | E5-small pretrained | không | — | — | — | Zero-shot baseline |
| D1 | E5-small | full fine-tune | MNRL, batch 32 | `1e-5` | tối đa 3 | Baseline train ổn định |
| D2 | E5-small | full fine-tune | MNRL, batch 32 | `2e-5` | tối đa 3 | Kiểm tra LR |
| D0-B | BamiBERT pretrained | không | — | — | — | Zero-shot thuần Việt |
| D3 | BamiBERT | full fine-tune | MNRL, batch 32 | `2e-5` | tối đa 3 | So sánh backbone thuần Việt, raw input |
| D4 | model thắng D1–D3 | full fine-tune | Cached MNRL, effective batch 128, mini-batch 16/32 | LR thắng | tối đa 3 | Chỉ chạy nếu batch size có khả năng là bottleneck |
| D5 | model thắng | fine-tune với hard negatives bảo thủ | triplet/n-tuple phù hợp | config thắng | 1–2 | Chỉ sau khi D1–D4 chứng minh lift và mining được audit |

Mỗi epoch lưu checkpoint và chạy exact retrieval trên dev. Dùng warmup ratio 0,1, linear scheduler, AdamW, weight decay 0,01, max grad norm 1, FP16 trên P100/T4. Không dùng BF16 trên P100.

Nếu không nhánh fine-tune nào vượt zero-shot tương ứng, dừng để phân tích
data/loss; chưa chuyển sang E5-base hoặc BGE-M3.

## 6. Exact-vector evaluation trên Kaggle

Encode toàn bộ 45.693 destination passages cho từng checkpoint. Corpus embeddings FP32 có kích thước lý thuyết khoảng 70,2 MB (`45693 × 384 × 4`). Dùng FAISS `IndexFlatIP` hoặc matrix multiplication exact; chưa dùng ANN trong quyết định chất lượng model.

### 6.1 Metric chính

Trên `main_metric_candidate=true`:

- CandidateHit@20 và CandidateHit@50;
- Hit@1 và Hit@5;
- MRR@10;
- per-query rank và target score;
- paired delta so với D0 theo cùng query family.

Chọn checkpoint trên 438 dev rows. Test 391 rows chỉ chạy một lần sau khi khóa model/hyperparameters.

### 6.2 Slices bắt buộc

- `clean_name`;
- `no_diacritics`;
- `wrong_tone` và `partial_diacritics`;
- `adjacent_transpose`;
- `address_exact`, `name_address`, `address_first`, `name_street`;
- address-only target;
- single-token target;
- category và vùng địa lý;
- warm/cold target theo split;
- query/passsage token-length buckets.

### 6.3 Diagnostic tracks

- **Autocomplete:** báo intended-target CandidateHit@N và any-compatible Hit@N riêng; không dùng MRR chính cho prefix mơ hồ.
- **Ambiguity stress:** báo candidate coverage, result diversity và intended-target presence; không coi compatible list lớn là qrels hoàn chỉnh.
- **Structured code:** hiện chỉ 10 metric candidates, chỉ báo cases/ranks, chưa kết luận aggregate.
- **IME:** chỉ chạy khi muốn kiểm tra raw-key robustness; không gộp vào committed-text score.
- **Entity level:** báo canonical và entity-resolved metrics song song; hiện chỉ một inferred collapse nên chênh lệch dự kiến rất nhỏ.

## 7. Guardrails chọn checkpoint

Trước khi mở test, khóa các điều kiện trên dev:

1. CandidateHit@50 và MRR@10 tốt hơn D0 hoặc ít nhất không giảm ngoài tolerance đã chốt.
2. `clean_name` và `address_exact` không giảm quá 1 điểm phần trăm tuyệt đối.
3. Noisy slices có lift nhất quán, không chỉ một case type chi phối.
4. Không có NaN, missing ID, token-prefix mismatch hoặc corpus/model dimension mismatch.
5. Kết quả có thể tái chạy cùng seed trong tolerance số học.
6. Model card ghi rõ dữ liệu synthetic/weak labels và các track bị loại.

Ngưỡng 2 điểm phần trăm trong tài liệu chính có thể dùng làm target pilot, nhưng trước human review chỉ là engineering gate, không phải bằng chứng sản phẩm.

## 8. Kaggle execution plan

### 8.1 Private input dataset tối giản

Chỉ upload:

- `queries_10k.parquet`;
- `corpus_search_view.parquet`;
- `entity_resolution.parquet`;
- `dataset_manifest.json`;
- `generation_policy.json`;
- `entity_policy.json`;
- `validation_report.json`;
- một training config YAML/JSON sau khi tạo.

Không upload PBF, JSONL 71 MB, split Parquets trùng nội dung hoặc raw credentials. Tổng input cốt lõi dưới 10 MB.

Dataset Kaggle để **private** trong pilot. Metadata phải ghi OSM/ODbL attribution, dataset/corpus/search-view versions và hashes.

### 8.2 Notebook/kernel

Notebook đề xuất: `hanoi-poi-e5-stage1-train`.

Các cell/step:

1. kiểm tra GPU, package versions và mounted hashes;
2. validate manifest/schema/versions;
3. build passages và token-length audit;
4. chạy D0 E5 và D0-B BamiBERT bằng exact retrieval;
5. chạy D1/D2 E5 và D3 BamiBERT, eval mỗi epoch;
6. chọn backbone/config bằng dev và guardrails;
7. chỉ mở test sau khi lựa chọn đã được khóa;
8. chạy selected model và các frozen zero-shot baselines trên test;
9. xuất checkpoint, embeddings, per-query runs và report.

Kaggle hỗ trợ notebook versioned environment, GPU và output artifacts; tài liệu hiện tại nêu session CPU/GPU tối đa 12 giờ và khoảng 20 GB output được lưu. GPU availability/quota có thể thay đổi và cần kiểm tra trong account trước khi chạy: [Kaggle Notebooks](https://www.kaggle.com/docs/notebooks) và [GPU usage](https://www.kaggle.com/docs/efficient-gpu-usage).

CLI chính thức hỗ trợ `datasets create/version` và `kernels push`; lưu ý `kernels push` sẽ upload rồi chạy kernel, nên chỉ gọi sau khi dataset metadata và config đã được duyệt: [Kaggle dataset commands](https://github.com/Kaggle/kaggle-cli/blob/main/skills/references/datasets.md) và [kernel commands](https://github.com/Kaggle/kaggle-cli/blob/main/docs/kernels.md).

### 8.3 Output bắt buộc

```text
outputs/
  config_resolved.json
  environment.txt
  input_manifest_verified.json
  passage_manifest.json
  zero_shot_dev_metrics_<model>.json
  token_length_audit_<model>.json
  checkpoints/<run>/
  corpus_embeddings.npy
  corpus_id_map.parquet
  per_query_runs/<run>.parquet
  metrics_by_slice.parquet
  model_selection.json
  inference_config.json
  final_model/
  MODEL_CARD.md
```

Không chỉ giữ notebook output hiển thị. Mọi quyết định phải đọc lại được từ artifacts.

## 9. Tích hợp local sau Kaggle

1. Tải checkpoint thắng và kiểm tra SHA-256.
2. Re-encode corpus local hoặc xác minh embeddings tải về khớp ID map/model revision.
3. Build OpenSearch lexical index trước.
4. Thêm `knn_vector` theo đúng `embedding_dimension` trong model manifest
   (384 nếu E5-small thắng, 768 nếu BamiBERT thắng) và ANN.
5. So exact-vector với ANN để đo index recall.
6. Chạy lexical-only, dense-only và hybrid RRF trên cùng query set/candidate budget.
7. Tune fusion và routing chỉ trên dev.
8. Chạy test một lần, sau đó benchmark p50/p95/p99/QPS local.

Kaggle không được dùng để kết luận latency serving hoặc OpenSearch capacity.

## 10. Các việc chưa chặn vòng train

- Human review 100 mẫu: chủ dự án thực hiện sau; nên lấy phân tầng theo main/address/autocomplete/structured/IME.
- Structured code metric mới có 10 cases: giữ diagnostic.
- Real IME replay chưa có: raw-key track không vào main.
- Pickup verified và routing points bằng 0: không liên quan Stage 1 destination retrieval.
- Entity collapse mới có một group: adapter vẫn được giữ để kiểm tra nhưng không ảnh hưởng lựa chọn encoder đáng kể.
- Parent corpus bundle hiện không có trong workspace query package: search view đủ cho Stage 1; cần bổ sung URI/hash nếu muốn tái tạo từ PBF.

## 11. Thứ tự thực hiện và điểm dừng

| Mốc | Đầu ra | Điều kiện đi tiếp |
|---|---|---|
| T0 — Freeze input | Hashes + minimal Kaggle dataset manifest | Tất cả input khớp v3 |
| T1 — Baseline | D0 E5/BamiBERT metrics và per-query ranks | Không có lỗi passage/evaluator |
| T2 — Pilot train | 200–300 steps hoặc một epoch D1 | Loss hữu hạn, embeddings/ranks hợp lệ |
| T3 — Main train | D1/D2 E5 và D3 BamiBERT, checkpoint mỗi epoch | Chọn trên dev theo guardrails |
| T4 — Optional scale | Cached MNRL D4 hoặc hard-negative D5 | Chỉ khi có giả thuyết từ lỗi D1–D3 |
| T5 — Freeze/test | Một model/config, test chạy một lần | Xuất report và model card |
| T6 — Local hybrid | OpenSearch + RRF + latency | Quyết định Stage 1 bàn giao hay quay lại data/model |

Nếu các zero-shot baseline đã mạnh và fine-tune không cải thiện dev, kết quả hợp
lệ là giữ backbone pretrained thắng cuộc. Không tiếp tục train chỉ để có
checkpoint riêng.
