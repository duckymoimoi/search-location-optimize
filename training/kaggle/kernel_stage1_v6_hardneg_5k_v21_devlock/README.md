# vn-poi-stage1-v6-hardneg-5k-v21-devlock-train

Controlled 5k arm. Does not overwrite the 6k diagnostic kernel or `vn-poi-stage1-v6-hardneg-6k-devlock-train`.

- Gold POI ids are excluded from every train pair.
- Checkpoint lock is dev Hit@1 versus zero-shot dev.
- Gold is scored once after that lock, including a zero-shot Gold pass for the delta.
- Do not upload embeddings.
