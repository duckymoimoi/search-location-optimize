# Tools — các điểm vào hiện hành

Thư mục này chứa pipeline dữ liệu offline, authoring, evaluation và kiểm tra release. API/ranker chạy online nằm trong `apps/poi-search/api`; training optimizer nằm trong Kaggle kernels.

## Các lệnh dùng cho công việc hiện tại

| Mục đích | Script | Ghi chú |
|---|---|---|
| Kiểm tra corpus phục vụ search | `verify_clean_poi_corpus_v3.py --scope artifacts` | Không chứng nhận full source provenance |
| Clean candidate corpus | `build_clean_poi_corpus_v3.py --source ... --output ...` | Source đầy đủ; output mới, không ghi đè active |
| Rebuild admin candidate | `extract_admin_regions.py --pbf ... --output ...` | Chưa tự activate hoặc remap memberships |
| Audit corpus/admin | `audit_corpus_admin.py --out ...` | Chỉ đọc; kiểm hash, geometry, FK và policy |
| EDA dataset | `report_current_datasets.py --out ...` | Khóa scope và source hashes |
| Verify Gold POI hiện hành | `reissue_gold_stage1_v22.py verify` | Regression reissue; không phải holdout mới |
| Verify Gold brand | `validate_gold_stage1_brand_v1.py --release-dir ... --require-lock --report ...` | Chỉ định release và output report |
| Verify bàn giao retrieval | `verify_stage1_handoff.py --api ... --out ...` | Cần frozen traces/model/index local |
| Chuẩn bị trial Kaggle | `prepare_dense_first_kaggle_trial.py` | Chuẩn bị pack; không train local |

Từ repo root chạy `python tools/<script> --help` để xem tham số. Model, vector, trace và generated reports giữ dưới `artifacts/`, không đưa vào source Git.

## Các nhóm hỗ trợ còn cần giữ

| Nhóm | Các tên script | Vai trò |
|---|---|---|
| POI authoring | `build_stage1_authoring_packet`, `serialize_stage1_v6`, `validate_stage1_train_v6`, `stage1_v6_common`, `expand_stage1_v6_manual_batch`, `merge_stage1_v6_authored` | Schema, query variants, trace và validation |
| Brand pipeline | `build_brand_*`, `validate_brand_*`, `serialize_stage1_brand_queries_v1`, `stage1_brand_*_common`, `split_brand_families_v1`, `compile_stage1_poi_brand_views` | Membership/aliases, query/qrels và split |
| Negative mining | `mine_stage1_hardneg_pilot`, `compile_stage1_hardneg_pilot`, `augment_stage1_hardneg_brand_siblings`, `sample_hardneg_audit` | Train pairs, FN audit và masks |
| Evaluation authoring | `serialize_gold_poi_draft`, `audit_gold_query_coverage`, `plan_gold_name_street`, `lock_gold_stage1_brand_v1` | Serializer/schema helpers còn được kiểm thử; không sửa signed release tại chỗ |
| Diagnostics | `report_*`, `compare_*`, `judge_devlock_summary`, `inspect_osm_*`, `analyze_gold_stage1_v21_miss` | Chẩn đoán offline; output riêng, không tự cập nhật bàn giao |
| Shared helpers/tests | `prefix_sampler`, common modules, `tests/` | Dependency dùng chung và regression |

Tên version trong authoring biểu thị schema/payload contract, không đủ để kết luận script hết dùng. Script chỉ được xóa khi không còn dependency và quy trình hiện hành cần nó. Các tool được pin hash trong dataset manifests phải giữ đúng bytes cho verifier.

## Quy tắc thêm tool

1. Mở rộng CLI hiện có nếu cùng nhiệm vụ, thay vì tạo `report_x_v2_new_final.py`.
2. Ghi vào bảng nhóm và tài liệu tuần liên quan; output thử nghiệm dùng thư mục mới dưới `artifacts/results`.
3. Tool một lần chỉ sửa batch cụ thể không trở thành entrypoint vận hành; bỏ sau khi migration đã hoàn tất và không còn dependency.
4. Không tạo wrapper chỉ để chuyển tiếp tới một file đã mất. Không dùng wildcard xóa các tool cùng suffix version.

Regression: `python -m pytest -q tools/tests`. Các test này kiểm pipeline offline, không train optimizer hoặc chứng nhận chất lượng ranking.
