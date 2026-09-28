# W3 — Mining và hard-negative audit

Pack dùng cho baseline nghiên cứu là 6k clean; IDs trong corpus và query của training pairs thuộc split train. Mining cần giữ multi-positive/ignore mask, lọc false negative, pin encoder/index nguồn negative và dataset hash.

## Mẫu kiểm tra

[Nhãn 150 pairs](hardneg_audit_6k_sample.csv), seed 42: 75 dense, 50 random, 25 lexical.

| Nguồn | True hard | Easy | Đánh dấu false negative |
|---|---:|---:|---:|
| Dense | 73 | 0 | 2 |
| Lexical | 25 | 0 | 0 |
| Random | 0 | 50 | 0 |
| Tổng | 98 | 50 | 2 |

Tỷ lệ trên mẫu là 2/150 (1,3%). Mẫu stratified không phải ước lượng không chệch toàn population. Hai cặp Petrolimex cùng tên/địa chỉ hành chính chưa đủ evidence chứng minh cùng cửa hàng; cần adjudication trước chứng nhận false-negative rate toàn pack dưới 5%.

## Acceptance

- Có dataset/pair audit, mẫu và nhãn truy vết được.
- Không dùng query/entity trong Gold làm negative để rồi gọi Gold là untouched test.
- Cần kết luận adjudication của hai cặp nghi vấn và báo sampling distribution trước ký đầy đủ TC1.
- Không chọn checkpoint theo negative sample audit. Không suy inferred duplicate từ tên giống nhau.

Observation: dense negatives có entity ambiguity. Hypothesis: near-duplicate entity tạo false negatives. Experiment: soi mẫu theo nguồn. Result: hai ca nghi vấn. Decision: giữ audit mở cho adjudication; không tự đổi nhãn khi chưa đủ source evidence.
