# Stage 1 training runner

Local preflight, không tải model:

```powershell
python train_stage1.py --validate-only `
  --input-dir ..\..\HANOI_QUERIES_10K\hanoi_queries_10k `
  --output-dir .\smoke-output
```

GPU training dùng cùng script và `config.json`. Kaggle staging nằm ở `training/kaggle`; không đưa `kaggle.json` hoặc PBF vào staging.

Runner dùng Transformers + PyTorch trực tiếp:

- shared bi-encoder với hai backbone: multilingual E5-small và BamiBERT;
- mean pooling có attention mask;
- L2 normalization;
- MNRL/in-batch negatives;
- batch không trùng target/entity/query;
- exact full-corpus retrieval để chọn checkpoint;
- test chỉ chạy sau khi chọn model trên dev.

Runner thực hiện hai zero-shot baseline, D1/D2 cho E5 và D3 cho BamiBERT.
BamiBERT nhận raw Vietnamese nên phù hợp hơn raw PhoBERT cho query lỗi/chưa gõ
xong; giấy phép Qualcomm Responsible AI cần được review trước khi dùng thương mại.

Khi push bằng Kaggle CLI, ưu tiên khóa T4 để dùng trực tiếp PyTorch của image:

```powershell
kaggle kernels push -p ..\kaggle\kernel --accelerator NvidiaTeslaT4
```

Runner vẫn có fallback cài wheel CUDA 12.6 nếu scheduler cấp P100 cũ.
