# Kế hoạch tái biên soạn Gold Stage 1 — release v2.1

**Trạng thái:** release v2.1 đã khóa ngày 2026-09-26; baseline sau khóa đã
chạy trên Docker corpus v3. Đây là release mới của suite logic
`gold_stage1_v2`, không sửa/xóa bản Gold v2 đã khóa.  
**Mục tiêu:** 200 POI, 800 completed sessions, qrels theo từng query, prefix
evidence đủ để chấm autocomplete, coverage có bằng chứng và validator mạnh hơn.

**Checkpoint lịch sử 2026-09-25 (trước khi khóa):** bản nháp đã có 200/800 sessions, 820 qrels và 200
q01 prefix evidence. Kiểm tra cơ học PASS; đối chiếu toàn bộ train v6 đã xuất
bản (5.000 POI / 30.000 query) không thấy trùng target ID hoặc query sau
accent-fold. Tại thời điểm này bản nháp **chưa đủ điều kiện khóa**: xem
`staging/gold_stage1_v2_1/draft/coverage_diagnostic.json` và
`independent_audit.json`. Đã xác minh thêm các tag raw Telex/VNI, phím kề,
đảo thứ tự, acronym, đoạn giữa/cuối tên và địa chỉ đầy đủ trên query/trace/source;
chỉ requirement 12 (`bo_type_context_dau`) còn thiếu: 42/80 q01 có evidence
thật. Shortfall này đã được người dùng chấp nhận và lưu trong
`staging/gold_stage1_v2_1/coverage_shortfall_adjudication_v1.json`; không tự
gắn tag cho brand không có context để bỏ. Sau khi rút ngắn q01,
20 case có `entity_ready` trước cuối câu; 180 case giữ mốc bảo thủ ở cuối.
Quality signoff gắn hash đã được hoàn tất trước khi khóa. Train v6
published manifest còn ghi corpus v2, trong khi Gold v2.1 và Docker index dùng
corpus v3; baseline sau lock phải pin rõ v3 và báo train-time v2 → eval-time
v3 là khác biệt snapshot, không diễn giải như cùng một corpus.

**Điều chỉnh query ngắn cùng ngày:** q01 được rút về tên POI riêng, địa chỉ
`số + đường`, hoặc brand + discriminator ngắn nhất khi source-only corpus v3
chứng minh đủ phân biệt; 21 q02 tên riêng và 14 q02 địa chỉ cũng được rút
trong khi giữ hai mutation points. Trung vị q01 từ 7 xuống 6 từ; số q01 dài
ít nhất 7 từ từ 121 xuống 61. Sau serialize lại, audit cơ học PASS và overlap
accent-fold với Gold v1/train-5k bằng 0. Prefix evidence được tạo lại theo
q01 mới; 180/200 `entity_ready` hiện ở cuối q01 ngắn. Các mốc này không được
tự dịch sớm hơn nếu chưa có nguồn phân biệt. Đây là kết quả của bản nháp
trước khi quality signoff và khóa release.

**Biến thể tên + đường, không số nhà:** trên 136 POI có tên và metadata
số/đường, 131 đã có một query được gắn `name_street_no_house` và kiểm tra
trên corpus v3. Hai giá trị `CC2`/`SH16-130` là mã đơn vị nên không ép bỏ.
Ba case không thể gán singleton Gold đúng bằng tên + đường và đã được người
dùng chấp nhận là ngoại lệ:
`g150-035` có `addr:street=Hồ Tùng Mâuj` sai ngay trong OSM PBF,
`g150-115` có nhiều Long Châu trên Trần Hưng Đạo (có train target), và
`g150-129` có nhiều trạm sạc VinFast trên Xương Giang. Chi tiết ở
`staging/gold_stage1_v2_1/draft/name_street_no_house_coverage.json`.
Không tự coi các địa điểm khác nhau là `entity_equivalent` hoặc thêm train
target vào Gold positives. Ba ngoại lệ đã được adjudicate và QA signoff bản
cuối trước khi xuất release `data/vietnam/stage1_eval_suite_v2/gold_stage1_v2_1/`.

**Building-code review:** 26 case thuộc stratum `building_code` đã được rút
q02/q03 theo mã + khu/tòa, mã + tên riêng hoặc mã + đường; q04 được giữ làm
ca dài/khó hơn. Độ dài trung bình q02 giảm 7,0 → 4,3 từ, q03 giảm 6,2 → 4,5
từ; q03 dùng `space_merge` giảm 23/26 → 7/26. Audit kiểm tra mã bất biến
và các chuỗi số trong tên tòa; mọi query hiện PASS sau serialize.

Nguồn quy tắc:
[`GOLD_STAGE1_V2_CONSTRUCTION_PLAYBOOK.md`](../specs/GOLD_STAGE1_V2_CONSTRUCTION_PLAYBOOK.md),
[`STAGE1_EVALUATION_SUITE.md`](../specs/STAGE1_EVALUATION_SUITE.md) và
[`stage1_evaluation_v2.schema.json`](../specs/schemas/stage1_evaluation_v2.schema.json).
Release hiện hành: [`LOCKED.json`](../../data/vietnam/stage1_eval_suite_v2/gold_stage1_v2_1/LOCKED.json),
[`quality_signoff.json`](../../data/vietnam/stage1_eval_suite_v2/gold_stage1_v2_1/quality_signoff.json).
[`quality_audit.md`](../../artifacts/results/gold_stage1_v2_docker_baseline/quality_audit.md)
là audit baseline của Gold v2 cũ, không phải kết quả benchmark v2.1.
Baseline v2.1 ở
[`baseline_report.json`](../../artifacts/results/gold_stage1_v21_docker_baseline/baseline_report.json):
800 full-query và 5.092 q01 prefix checkpoint; hybrid Hit@20 = 91,25%,
lexical raw Hit@20 = 71,75%. Hybrid q01 raw FHC@10 = 99,5%; từ mốc
`entity_ready`, FHC@10 = 98,5%. SHC cửa sổ 3 sau mốc đó chỉ có 20/200
case đủ checkpoint, nên không diễn giải tỷ lệ trên toàn bộ 200 case như
chất lượng mô hình. Baseline này là eval-time corpus v3; train v6 published
manifest còn ghi corpus v2, phải báo đây là hai snapshot khác nhau.

## Ranh giới và nguyên tắc

Nguồn thực thi hiện hành là `poi_corpus_v3/pois_core.parquet` và train-target
`v1.2-corpus-v3-filtered`. Packet/manifest v2.1 đã được dựng lại từ v3; audit
kiểm tra cả train-target v3 lẫn snapshot train v2 đã pin ở
`target_pois_20k.parquet.v2bak` để ngăn leakage. Nguồn release đã được pin
trong `source_files.json`; không phụ thuộc vào tên backup khi phát hành. Corpus v3 giữ
nguyên Gold target theo chính sách bảo vệ, nên ba target mơ hồ 038/091/111
được thay bằng các POI v3 có tên/địa chỉ rõ ràng theo
`target_overrides_v1.json`; Gold v2 cũ không bị sửa.

- Giữ nguyên `data/vietnam/stage1_eval_suite_v2/gold_stage1_v2/` và Gold v1.
  Bản làm việc ở `data/vietnam/stage1_eval_suite_v2/staging/gold_stage1_v2_1/`;
  sau QA mới xuất release
  `data/vietnam/stage1_eval_suite_v2/gold_stage1_v2_1/`. `suite_id` trong
  schema vẫn là `gold_stage1_v2`; tên release nằm ở path/`LOCKED.json`, còn
  manifest giữ đúng schema với policy/version đã pin.
- Giữ 200 target hiện tại nếu source corpus v3 còn đúng. Thay target chỉ khi
  fact, eligibility hoặc equivalence audit độc lập chứng minh sai; nếu chuyển
  POI từ train thì loại nó và mọi positive/equivalent liên quan trước lock.
- Không đưa rank, miss list hoặc top results của baseline cũ vào packet author.
  Sửa quy tắc chung do audit cấu trúc được phép; không sửa từng query/nhãn để
  model hiện tại đạt điểm cao. Lần benchmark tiếp theo chỉ chạy **sau lock**.
- Bare brand, street-only và wrong-number không bị ép thành positive POI. Gold
  POI phủ phần của nó; yêu cầu #18 thuộc address suite và phải báo `pending`
  cho đến khi suite đó có artifact thật.

## Cách tiết kiệm token mà vẫn author thủ công

Một script tạo **case packet ngắn** từ `pois_core.parquet`, Gold target và
train exclusion snapshot; chỉ tra search documents, migration map hoặc brand
lookup riêng khi một case cần review:
`case_id`, official name, verified aliases/brand, số–đường–admin, category,
code/ref, identity anchor, candidate cùng tên/địa chỉ gần, `entity_group_id`
và nguồn/hash. Chỉ xuất 10–20 case mỗi lần, không đổ 179k POI hoặc bốn bản
query cũ vào context.

Agent chỉ author một JSONL nhỏ cho mỗi case:

```text
case_id, q01, q02, q03, q04,
query-specific accepted IDs hoặc needs_review,
coverage tags + evidence ngắn,
điểm bắt đầu group_ready/entity_ready của q01,
ghi chú fact/ambiguity cần adjudicate
```

Serializer lấy target metadata, `query_id`, `query_family_id`, schema/version,
`qrel_set_id`, origin/exposure/stratum và các trường lặp từ packet; không bắt
agent viết lại 18 cột × 800 hàng. Code chỉ điền fact/trường cơ học, thống kê
coverage và phát hiện rủi ro; **không sinh hàng loạt q02–q04 bằng một công thức
typo**. Mỗi batch được xem lại dạng bảng 4 query/case trước khi nhập batch kế.

## Các pha và gate

1. **Freeze input và audit target (200/200).** Pin hash của corpus/index v2,
   target list, train list, brand lookup và Gold v2 cũ. Chạy verifier hiện có.
   Kiểm tra 200 ID tồn tại, không giao train target/positive, duplicate gần,
   tên/địa chỉ/mã đúng source. Xuất `target_audit.json` và danh sách
   `needs_review`. Không đổi target chỉ vì baseline miss.
2. **Chuẩn bị packet + serializer + validator.** Tạo script dùng chung, test
   trên vài case có brand, số slash, building code và POI địa chỉ. Packet không
   chứa kết quả model. Validator kiểm tra CSV/Parquet parity, 4 role/case,
   canonical ID, qrel set, evidence source, tag có hiện tượng thật, mutation
   trên identity/discriminator, old-Gold/train query collision, prefix labels,
   hash và status. `difficulty` không được suy ra từ slot.
3. **Author 200 case theo batch 10–20.** q01 là cách gõ ngắn tự nhiên nhưng
   đủ POI/branch intent. q02–q04 phải có ít nhất hai điểm biến đổi có ý nghĩa
   ở các vị trí khác nhau, trong đó có một điểm ngay phần nhận dạng đầu tiên
   (bỏ qua số/code bất biến); không đặt trần số lỗi, nhưng giữ skeleton để
   khôi phục intent. Phủ cả mất ranh giới giữa từ (`space_merge`) và khoảng
   trắng chèn giữa chữ của một token (`space_split_inside_token`) trong mỗi
   batch, nhưng `space_split_inside_token` là ca hiếm, chỉ vài row có source
   và cách gõ hợp lý, không dùng làm công thức mặc định. Trace ngắn ghi rõ
   `early:source→query` và các điểm sau; code chỉ
   kiểm tra trace/coverage, không tự chế typo. Không dùng rụng dấu + dính space
   thành template cho hầu hết q02/q03. Review thủ công từng case, tự đặt
   `needs_review` khi fact thiếu. Chỉ serialize batch khi 4 query đều
   source-backed.
4. **Qrels theo từng query, độc lập với model.** Review collision sau từng
   omission, fragment, viết tắt, mất dấu, số/đường. Qrels có thể singleton
   hoặc nhiều POI cùng entity/ambiguity đã xác minh; không tự mở rộng mọi
   branch của brand. `qrel_set_id` riêng theo query trừ khi tập positive thật
   sự giống nhau. Các cặp cùng tên/địa chỉ gần được đưa vào hàng review bằng
   catalog evidence; quyết định không dựa trên top result của baseline.
5. **Prefix evidence bằng ranh giới, không author mọi ký tự.** Với mỗi q01,
   agent duyệt vị trí grapheme đầu tiên đủ `group_ready` và `entity_ready`
   (hoặc ghi không đạt + lý do). Expander NFC sinh checkpoint/state/biên từ;
   q02–q04 có thể báo robustness prefix riêng. Unit test SHC yêu cầu đủ ba
   checkpoint liên tiếp, không dùng cửa sổ rút ngắn cuối câu. Headline q01
   chỉ chấm exact entity khi `entity_ready`; báo raw FHC/SHC riêng.
6. **Coverage và QA toàn bộ.** Báo Gold-owned requirements 1–17, 19–22 và
   derived prefix 14–15 bằng source/trace; #18 là handoff pending, không ghi
   shared suite 22/22. Double-review mọi multi-positive và compound/challenge,
   blind-review tối thiểu 20% q01 cùng các variant còn lại. Xuất phân bố tag,
   độ khó thực tế, vị trí lỗi, tỷ lệ q02 fold-trùng q01, template repetition,
   old-Gold/train collisions và các case chưa rõ. Nếu cần thay bề mặt, làm
   trước lock và không nhìn rank model.
7. **Lock rồi benchmark một lần.** Đúng 200 target, 800 session, 4/case,
   schema/hashes/qrels/prefix evidence/coverage/leakage PASS và
   `needs_review=0`. Xuất immutable Parquet+CSV, qrels, prefix evidence
   sidecar, coverage/audit, manifest và `LOCKED.json`; cập nhật registry trỏ
   release mới nhưng giữ release cũ để replay. Chạy lại lexical raw, hybrid
   app trên 800 full-query và q01 prefix 200 case cùng index/policy đã pin.
   Báo Hit@20/50, MRR@10, FHC/SHC/AUC, raw vs evidence-ready, theo role và
   difficulty. Không sửa release theo kết quả này.

## Điều kiện hoàn thành và bất đồng cần báo

Hoàn thành khi validator độc lập PASS, 200/800, query-specific qrels đầy đủ,
prefix evidence có trên 200 q01, các requirement Gold-owned đủ/shortfall được
adjudicate, train overlap 0 và baseline mới được lưu sau lock. Shared suite
chỉ hoàn thành 22/22 khi brand/address suites liên quan cũng được build và
validate. Nếu một case không có query ngắn đủ định danh hoặc collision không
thể adjudicate bằng corpus, báo rõ case và chọn target thay thế dựa trên source
trước khi lock; không đoán nhãn.
