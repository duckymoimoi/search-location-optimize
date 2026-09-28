# W1 — Error taxonomy và cách xác định nguyên nhân

Mỗi lỗi có một primary class, có thể thêm secondary. Không sửa qrels theo model output để chuyển lỗi thành hit.

| Class | Điều kiện xác định | Evidence cần đọc | Nơi sửa |
|---|---|---|---|
| E0 catalog | Target thiếu hoặc thuộc tính/entity mapping sai | Corpus, ID map, source evidence | Dữ liệu/index |
| E1 retrieval | Target hợp lệ nhưng không nằm trong pool đầu vào ranker | Branch IDs và pool sau filter/cap | Retriever/routing/budget |
| E2 ranking | Pool có accepted target nhưng thứ tự không đạt | Cùng pool trước/sau ranker, feature/context | Ranker |
| E3 serving/business/UX | Hydration/filter/dedup/fallback/latency/selection làm mất kết quả đúng | Stage trace và API events | Serving/result layer |
| E4 label/evaluation | Query drift, thiếu positive, sai namespace hoặc denominator | Query-specific qrels và adjudication | Evaluation/annotation |

## Subtype ưu tiên

- E1: orthography/typo, alias, house/code, long-tail, brand routing và membership lọc mất entity.
- E2: over-weight distance/popularity, sai cohort tên, missing origin bị hiểu là 0, feature nhìn tương lai.
- E3: model/index mismatch, timeout, degraded route không được ghi, candidate bị cắt sớm, session/selection không khớp.
- E4: coi bare brand là một exact branch, split theo row gây leakage, coi tập regression đã xem là holdout độc lập.

## Biểu mẫu error analysis

Mỗi case ghi query ID, suite/split, accepted IDs, model/index/policy, route, rank tại từng stage, primary class, bằng chứng và action. Báo rescue/harm theo paired query; denominator bao gồm lỗi/timeout theo protocol.

Một target vắng pool không được tính là thất bại của Stage 2. Khi target có trong pool, sửa ranker trên pool cố định trước; nếu đổi retrieval phải tạo experiment riêng. Phân tích luôn theo query type/length, city, head-tail, category, language, ambiguity và namespace khi có nhãn.
