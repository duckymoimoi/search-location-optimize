# App: bản hiện tại và Brand+POI

Trên demo, menu **Mô hình** có hai lựa chọn. Bản hiện tại không bị thay index hay checkpoint.

| Mô hình | API | Index | Encoder |
|---|---|---|---|
| Bản hiện tại | cổng 8000, đường `/v1` | `vn-poi-core-v3-me5-small` | multilingual-e5-small zero-shot |
| Brand+POI | cổng 8002, đường `/mix` | `vn-poi-core-v3-me5-brand-poi-mix` | checkpoint epoch 2 của batch 12 POI + 4 brand |

Cùng corpus v3, cùng lexical `search-policy-stable-demo-v12`, cùng hybrid. Khác encoder và vector dense.

Gold sau khi khóa checkpoint Brand+POI: brand Hit@1 0.578 (bản 6k trước mix là 0.552), POI Hit@1 0.9475. Hybrid của riêng checkpoint mix chưa đo lại trên index mới.

Web nginx chuyển `/mix/` tới `127.0.0.1:8002`. Index và API mix nằm trên Elasticsearch riêng cổng 9201, không ghi vào index demo.

```text
docker compose -f apps/poi-search/docker-compose.devlock.yml --profile mix up -d
```

Embedding: `artifacts/embeddings/me5_brand_poi_mix`. Checkpoint phục vụ: `artifacts/models/me5_brand_poi_mix_serving`.
