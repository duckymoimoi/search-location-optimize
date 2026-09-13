# Kết quả huấn luyện Stage 1 — Hanoi POI v1

Ngày chạy: 2026-09-13. Kaggle kernel version 2 đã hoàn tất. Dataset và kernel
đều để private.

- Dataset: <https://www.kaggle.com/datasets/hiengchi/hanoi-poi-stage1-v3>
- Kernel: <https://www.kaggle.com/code/hiengchi/hanoi-poi-e5-stage1-train>
- Input: `hnq10k-pilot-v3`, corpus `hn-260910-7f1b69b167`, search view
  `hn-search-view-v3`.
- Exact evaluation corpus: 45.693 destination-searchable POIs.
- Train/dev/test: 3.927 / 438 / 391 queries.
- Selection order: CandidateHit@50, MRR@10, Hit@1; clean-name và
  address-exact là guardrails.

## Kết luận

Checkpoint được chọn là `D2_e5_mnrl_lr2e5_epoch3`, khởi tạo từ
`intfloat/multilingual-e5-small`, LR `2e-5`, batch 32, ba epoch, MNRL với
in-batch negatives không trùng target/entity/query.

| Candidate | Dev Hit@1 | Dev Hit@5 | Dev MRR@10 | Dev CH@20 | Dev CH@50 |
|---|---:|---:|---:|---:|---:|
| E5 zero-shot | 0,6142 | 0,7123 | 0,6570 | 0,7626 | 0,7877 |
| E5, LR `1e-5`, epoch 3 | 0,9064 | 0,9635 | 0,9312 | 0,9795 | 0,9932 |
| **E5, LR `2e-5`, epoch 3** | **0,9064** | **0,9749** | **0,9348** | **0,9886** | **0,9977** |
| BamiBERT zero-shot | 0,1393 | 0,1872 | 0,1604 | 0,2352 | 0,2808 |
| BamiBERT, LR `2e-5`, epoch 3 | 0,8676 | 0,9521 | 0,9036 | 0,9795 | 0,9909 |

Test chỉ được mở sau khi khóa lựa chọn bằng dev:

| Model | Test Hit@1 | Test Hit@5 | Test MRR@10 | Test CH@20 | Test CH@50 |
|---|---:|---:|---:|---:|---:|
| E5 zero-shot | 0,5780 | 0,6522 | 0,6100 | 0,6931 | 0,7110 |
| **Selected E5** | **0,9258** | **0,9795** | **0,9502** | **0,9872** | **0,9974** |

## Độ chắc của lift

Đã chạy paired cluster bootstrap 10.000 lần theo `query_family_id`, tránh coi
các biến thể cùng một POI/query family là độc lập.

- Selected so với E5 zero-shot trên dev: Hit@1 `+0,2922`, CI95%
  `[+0,2369; +0,3486]`; MRR@10 `+0,2778`, CI95%
  `[+0,2285; +0,3281]`; CH@50 `+0,2100`, CI95%
  `[+0,1674; +0,2556]`.
- Selected so với E5 zero-shot trên test: Hit@1 `+0,3478`, CI95%
  `[+0,2916; +0,4043]`; MRR@10 `+0,3402`, CI95%
  `[+0,2891; +0,3904]`; CH@50 `+0,2864`, CI95%
  `[+0,2387; +0,3325]`.
- Selected E5 so với BamiBERT fine-tuned trên dev: Hit@1 `+0,0388`, nhưng
  CI95% `[-0,0068; +0,0841]`; ba CI đều cắt 0. E5 thắng theo rule selection
  đã khóa, nhưng bộ dev này chưa đủ để khẳng định họ model E5 luôn tốt hơn
  BamiBERT.

## Trả lời lựa chọn BamiBERT/PhoBERT

BamiBERT không quá nặng để train. Trên cùng Tesla P100, một epoch gồm train và
full-corpus dev eval mất khoảng 73 giây, so với khoảng 30 giây của E5-small.
Checkpoint BamiBERT khoảng 393 MiB; checkpoint E5 khoảng 449 MiB. Tuy nhiên
BamiBERT tạo vector 768 chiều, làm dense index float32 dự kiến gấp đôi E5 384
chiều. Với 45.693 POI, riêng vector thô là khoảng 134 MiB thay vì 67 MiB.

BamiBERT zero-shot rất yếu vì đây là masked-language backbone, không phải
retrieval encoder. Sau MNRL nó tăng mạnh lên Hit@1 0,8676, chứng minh hướng này
khả thi. Dù vậy E5 vẫn là lựa chọn demo hợp lý hơn nhờ metric dev cao hơn, index
nhỏ hơn và inference nhanh hơn. Raw PhoBERT chưa được chạy vì yêu cầu external
word segmentation tạo thêm rủi ro cho query typo/prefix. Giấy phép Qualcomm
Responsible AI của BamiBERT phải được review trước commercial production.

## Audit artifact

Local audit đã pass:

- 6/6 hash của final model khớp `final_model_manifest.json`;
- corpus embeddings có shape `(45693, 384)`, dtype float32, không NaN/Inf,
  norm nằm trong `[0,99999988; 1,00000012]`;
- 45.693 ID là duy nhất và đúng thứ tự destination corpus;
- 15 rank Parquet có rank hợp lệ; metric tái tính khớp JSON;
- selected dev ranks giống chính xác D2 epoch 3;
- model selection được tái hiện đúng từ dev metrics và guardrails.

Executed kernel SHA-256:
`3e1dd8ab88ee814c74f1b3f2c9c9607079c0cab4d68c39330030cca7c28a04ce`.
Config SHA-256:
`517a4b7efb528bfc32736bdc3117b66e5f0efae44f980cd3521ce5c093b2fbaf`.

## Error analysis và giới hạn

Hai slice lớn còn yếu nhất trên test là adjacent-transpose, Hit@1 `0,8734`
(`n=79`), và no-diacritics, Hit@1 `0,8774` (`n=106`). Address-exact đạt 1,0
(`n=33`) và clean-name đạt 0,9710 (`n=69`). Các slice rất nhỏ như
unit-with-namespace (`n=4`) không đủ để kết luận.

Kết quả hiện tại chỉ chứng minh trên synthetic weak-label benchmark được sinh từ
cùng OSM corpus; chưa chứng minh chất lượng traffic thật. Structured-code mới có
10 metric cases, IME chưa replay bằng keyboard engine thật, chưa có pickup routing
point và Stage 2 chưa tham gia. Human review 100 mẫu vẫn là quality gate do chủ
dự án thực hiện sau.

Kaggle cấp P100 nhưng image mặc định dùng PyTorch không chứa `sm_60`. Runner đã
tự cài wheel CUDA 12.6 và run thành công. Lần sau nên khóa
`--accelerator NvidiaTeslaT4`. BamiBERT có một AMP overflow ở bước đầu nên
scheduler đã tiến một step dù optimizer skip; source local sau run đã sửa để
scheduler chỉ tiến khi optimizer thực sự step. Điều này không ảnh hưởng model
được chọn vì checkpoint thắng là E5 và E5 không phát warning đó.

## Bước tiếp theo

1. Giữ nguyên test; không dùng nó để tune tiếp.
2. Nạp final 384-d embeddings và ID map vào OpenSearch k-NN index.
3. Đo exact-vector so với ANN để lấy index recall.
4. Xây lexical BM25 và hybrid RRF; tune chỉ bằng dev.
5. Thêm Stage 2 spatial/context reranker dùng origin POI, khoảng cách và context.
6. Chạy test frozen và benchmark p50/p95/p99/QPS của luồng hoàn chỉnh.
