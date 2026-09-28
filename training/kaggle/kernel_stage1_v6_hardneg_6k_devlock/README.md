# vn-poi-stage1-v6-hardneg-6k-devlock-train

New kernel. Does not overwrite diagnostic `vn-poi-stage1-v6-hardneg-6k-train` (Kaggle version 352867030).

- Gold POI ids are excluded from every train pair.
- Checkpoint lock is dev Hit@1 versus zero-shot dev.
- Gold is scored once after that lock, including a zero-shot Gold pass for the delta.
- Do not upload embeddings.
