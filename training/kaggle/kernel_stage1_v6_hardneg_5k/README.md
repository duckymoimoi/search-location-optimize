# vn-poi-stage1-v6-hardneg-5k-train

New Kaggle script kernel. It does **not** overwrite `vn-poi-stage1-v6-e5-finetune`, `vn-poi-stage1-v6-hardneg-train`, or `vn-poi-stage1-v6-hardneg-4k-train`.

- Published v6 5000 POI / 30000 query; compiled views only.
- Slot weights: v01/v02=1.0, SINGLE v03/v05=0.5, COMPOUND v04/v06=0.25.
- Hardneg 2 random + 3 lexical + 3 dense. No forced same-brand siblings.
- At most 2 epochs. Gold Hit@1 lock; FHC/SHC reported, not used to keep.
- Do not upload `*.npy` embeddings with this pack.
