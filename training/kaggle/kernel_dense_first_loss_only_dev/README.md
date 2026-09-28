# Private Kaggle dev-only weight trial

Generated from the canonical trainer; regenerate after editing it. No local optimizer execution. Gold IDs are read for exclusion/validation; Gold metrics are not scored.

Submit explicitly when a training gap warrants this trial:

```powershell
python -m kaggle kernels push -p training/kaggle/kernel_dense_first_loss_only_dev
```

Do not overwrite prior kernel outputs. Use dev metrics to select trials, then freeze the checkpoint before regression/holdout scoring.
