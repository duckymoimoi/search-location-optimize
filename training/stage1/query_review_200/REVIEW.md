# Human review — mẫu 200 query (hnq20k-pilot-v4)

Seed lấy mẫu: `20260913`. Phân tầng: retrieval_core 90 / autocomplete 30 / ambiguity 30 / ime 25 / structured 25.

## Verdict ngắn

Chất lượng **đủ dùng cho Stage 1 synthetic benchmark và MNRL đã lọc**, nhưng **chưa phải human-gold**. Phần retrieval_core rõ ràng ổn; phần phrase template hơi máy; ambiguity/IME/structured đúng là stress diagnostic (đã loại khỏi main metric phần lớn). Có vài case nhãn/diễn đạt đáng nghi nhưng tỷ lệ thấp và thường đã `requires_review` / không train.

## Điểm model hiện tại (bối cảnh)

Selected `V4C2` exact full-corpus: **dev Hit@1 0.890 / CH@50 0.978**; **test Hit@1 0.954 / CH@50 1.000**. Slice yếu vẫn là alias, keyboard_neighbor, mixed errors — khớp với những query “vỡ” trong mẫu review.

## Phân loại sau khi đọc mẫu

| Nhóm | Ước lượng trong 200 | Nhận xét |
|---|---:|---|
| Rõ, dùng tốt | ~45–50% | Tên/địa chỉ/abbrev/no-diacritics có neo |
| Noise có chủ đích, vẫn ổn | ~25–30% | Typo/prefix được flag đúng |
| Template / diễn đạt hơi giả | ~8–12% | `cho tôi tới X`, `địa chỉ X` |
| Stress quá mỏng / mã ngắn | ~10–15% | `t`, `e2`, `van`, brand ngắn |
| Đáng nghi nhãn hoặc quá hỏng | ~3–5% | mixed errors mất neo; alias lạ |

Heuristic auto: ok 181 / mixed 7 / bad 12 — “bad” phần lớn là weak_naturalness hoặc structured_thin đã loại metric, không phải nhãn sai hàng loạt.

## Ví dụ ổn (điển hình)

- `bv đa khoa đan phượng` → Bệnh viện Đa khoa Đan Phượng
- `113 ngõ 192 lê trọng tấn` → đúng slash/ngõ
- `thcs sài đồng phân hiệu 1` → paraphrase viết tắt tự nhiên
- `484 duong ang` ← `484 đường láng` (deletion có kiểm soát)
- `trám biến áp triệu việt vương 1` (sai thanh, vẫn nhận diện được)

## Vấn đề cần lưu ý

1. **Search phrase template**: nhiều dòng chỉ là wrapper + tên (`địa chỉ vietnam post`, `cho tôi tới võ đường hanoi kendo`). Vẫn grounded, nhưng ít đa dạng ngôn ngữ thật; đã có flag `synthetic_language_rule` ở một phần.
2. **OSM name thô / generic**: `Quán trà đá`, `Market`, `Eab`, `Bệnh Viện Nhi` gắn `helipad` — corpus noise, không phải lỗi generator đơn thuần.
3. **Ambiguity đúng vai trò**: `kfc` (compat 25), `van` (1841), `winmart lê duẩn` (826) — không nên vào Hit@1 chính; sample cho thấy đã `main_metric=False`.
4. **Mixed errors đôi khi mất neo**: `qan via` ← Quán bia (compat 32); `phi hun` ← Pho Hùng. Khó cho người và model; giữ diagnostic, hạn chế train.
5. **Alias đặc biệt**: `yên lãng` → POI `Kẻ Láng` — nguồn OSM alias có thể đúng lịch sử nhưng người dùng hiện đại khó gõ vậy; `long bien station` ổn hơn.
6. **Unit/namespace**: `g 191 phố minh khai` / `a 7 phố hàm long` — hữu ích nếu có mã căn, nhưng dễ nhiễu nếu `G`/`A` không có trong nguồn thật.
7. **IME**: keystream Telex/VNI là mô phỏng, chưa engine thật — chỉ diagnostic.
8. **Structured code** `e2`, `n4`, `b3`: thiếu namespace → đúng là không vào core metric.

## Kết luận review

- **Query generation**: phần lớn grounded từ metadata, mutation có provenance, policy loại train/main khá chặt → **ổn cho pilot**.
- **Không ổn nếu**: dùng full 20k như bằng chứng traffic Hà Nội, hoặc tin Hit@1 trên ambiguity/IME/structured.
- **Ưu tiên tiếp**: human review 100–300 retrieval_core main-metric; giảm template phrase; siết/loại mixed-error mất token overlap khỏi train; giữ holdout chưa mở cho tune.

Artifacts: `sample_200.jsonl`, `sample_200_readable.md`, `audit_200.json`.
