# vn-poi-stage1-v6-hardneg-6k-devlock-encode

Encode corpus v3 with the locked 6k checkpoint. Output directory is `me5_small_v3_6k_devlock`.

Do not load these vectors into `vn-poi-core-v3-me5-small` or `artifacts/embeddings/me5_small_v3`.

The serving index name is `vn-poi-core-v3-me5-6k-devlock`. Push this kernel only after the 5k train and the prefix/brand rescore leave the GPU.
