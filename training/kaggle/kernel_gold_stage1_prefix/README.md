# Gold Stage1 Round-1b — char-prefix (Kaggle GPU, no local upload)

Chỉ dùng dataset đã có: `hiengchi/vn-poi-gold-stage1-w1`.  
Kernel tự expand NFC grapheme prefixes + encode lại corpus/prefix trên GPU.

```bash
python -m kaggle kernels push -p training/kaggle/kernel_gold_stage1_prefix
python -m kaggle kernels status hiengchi/vn-poi-gold-stage1-prefix-char
# sau khi xong:
python -m kaggle kernels output hiengchi/vn-poi-gold-stage1-prefix-char -p training/kaggle/output_gold_stage1_prefix
```

Profiles: BM25 · mE5 · Bekko A8M · Bekko A25M · FHC/SHC/PrefixAUC @1/5/10.
