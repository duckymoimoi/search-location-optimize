# Hanoi POI Stage 1 dense retriever

Selected run: `V4C2_e5_retrain_combined_lr2e5_epoch3`  
Base model: `intfloat/multilingual-e5-small` at revision `614241f622f53c4eeff9890bdc4f31cfecc418b3`  
Dataset: `hnq20k-pilot-v4`; corpus: `hn-260910-7f1b69b167`; search view: `hn-search-view-v3`

## Evaluation

Selection used only `dev_synthetic`; `test_synthetic` was evaluated after selection. Exact ranking covers all 45,693 destination-searchable POIs.

| Split | Hit@1 | Hit@5 | MRR@10 | CandidateHit@20 | CandidateHit@50 |
|---|---:|---:|---:|---:|---:|
| dev | 0.8903 | 0.9513 | 0.9167 | 0.9668 | 0.9777 |
| test | 0.9540 | 0.9898 | 0.9691 | 0.9974 | 1.0000 |

## Intended use and limitations

This is a demo candidate generator for Hanoi POI search, not a production geocoder. Training and held-out labels are synthetic weak labels derived from OSM POIs. The test split is synthetic, `structured_code` has only 10 metric cases, IME strings were not verified against a real mobile keyboard engine, and pickup routing points are not included. Stage 2 spatial/contextual reranking and a manually reviewed benchmark are still required before deployment. Review the selected base model license before commercial use.
