# Project structure and lifecycle

## Source of truth

| Thành phần | Đường dẫn chuẩn | Có thể tái tạo |
|---|---|---|
| Sản phẩm demo | `apps/poi-search/` | Không; đây là source code chính |
| OSM source | `vietnam-260910.osm.pbf` | Có thể tải lại, nhưng phải giữ đúng snapshot để reproducible |
| POI corpus | `HANOI_POI_STABLE_V1/hanoi_poi_stable_v1/` | Có, từ PBF và script trong bundle |
| Stage 1 eval data | `HANOI_QUERIES_20K/hanoi_queries_20k_stable_v1/` | Đang được coi là frozen release |
| Encoder | `artifacts/models/e5-v4-finetuned/` | Có thể train lại, nhưng tốn GPU và không đảm bảo bit-identical |
| Index vectors | `artifacts/indexes/hanoi-poi-stable-v1-release1/` | Có, từ corpus + encoder cùng embedding space |
| OpenSearch index | Docker volume `hanoi-poi-opensearch-data` | Có, qua `apps/poi-search/scripts/start.ps1` |
| Kết quả eval chốt | `artifacts/evaluations/stage1-stable-v1/` | Có, qua scripts trong `training/stage1/` |

`apps/poi-search/models/current` chỉ là junction do `scripts/link_model.ps1` quản lý; không đặt thêm một bản weights vào app.

## Cấu trúc tài liệu

| Thư mục | Ý nghĩa |
|---|---|
| `docs/as-built/` | Trạng thái code/runtime và số liệu theo snapshot |
| `docs/specs/` | Kiến trúc đích, technical spec và protocol nâng cấp |
| `docs/contract-package-v1/` | Baseline OpenAPI/schema/config có validation riêng |
| `docs/research/` | Rationale, bài báo và lịch sử pilot; không phải runtime truth |
| `docs/operations/` | Layout, artifact lifecycle và quy tắc release |

## Những gì đã loại khỏi workspace

- Dataset 10K và các snapshot 20K v6/v7/v8 sau khi stable-v1 được khóa.
- Checkpoint giữa epoch, model input copy, output Kaggle cũ, query embedding và per-query cache.
- Runtime API/launcher/Compose cũ dưới `training/`; runtime duy nhất nằm trong app.
- Ba tài liệu root v3 cũ; phần còn giá trị đã được phân loại vào `docs/specs/` và `docs/research/`.
- OpenSearch distribution đã extract, Windows ZIP, node data/log local và cache làm giàu địa chỉ v8.
- Bản Overture sample sinh thử; script audit/tải lại vẫn được giữ để dùng khi mở rộng corpus sau này.

Trường `source_dataset` trong manifest stable-v1 vẫn ghi đường dẫn v8 lịch sử. Đây là lineage của lần migration, không phải dependency runtime và không nên sửa ngược manifest frozen.

## Quy tắc cho release tiếp theo

Không tạo `v9`, `final2` hay `outputs_new` ở cấp workspace. Tạo release có ID rõ trong `artifacts/`, cập nhật manifest/junction, chạy dev → test frozen → typing → ANN/load, rồi chỉ thay release hiện tại sau khi qua gate. Cache tạm phải nằm trong thư mục ignored và xóa sau khi xuất báo cáo tổng hợp.
