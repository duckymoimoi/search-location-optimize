"""Create a private dev-only Kaggle trial from the canonical trainer; never train locally."""
import argparse
import hashlib
import json
from pathlib import Path


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8*1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def main(args):
    root = Path(__file__).resolve().parents[1]
    source = root/'training/kaggle/kernel_stage1_v6_hardneg_6k_devlock'
    data = root/'training/kaggle/dataset_stage1_v6_hardneg_6k_devlock'
    out = root/args.out
    out.mkdir(parents=True, exist_ok=False)
    hashes = {name:sha(data/name) for name in ['train_config.json','query_train_view.parquet','training_pairs.parquet','search_documents.parquet','gold_query_variants.csv']}
    code = (source/'run_train_stage1_v6_hardneg.py').read_text(encoding='utf-8')
    code = code.replace('import argparse\n', f'import argparse\nimport os\nimport hashlib\nos.environ["POI_DEV_ONLY"] = "1"\nos.environ["POI_WEIGHT_MODE"] = "{args.mode}"\n', 1)
    verification = '\n    expected_inputs = '+repr(hashes)+'\n'
    verification += '    for name, expected in expected_inputs.items():\n        h = hashlib.sha256()\n        with (data_dir / name).open("rb") as stream:\n            for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):\n                h.update(block)\n        if h.hexdigest() != expected:\n            raise RuntimeError("Pinned dataset drift: " + name)\n'
    anchor = '    checks = verify_pack(data_dir, config)'
    if anchor not in code:
        raise ValueError('Trainer packaging anchor changed')
    code = code.replace(anchor, verification+anchor, 1)
    (out/'run_train.py').write_text(code, encoding='utf-8')
    metadata = json.loads((source/'kernel-metadata.json').read_text(encoding='utf-8'))
    user = metadata['id'].split('/')[0]
    name = 'vn-poi-dense-first-'+args.mode.replace('_','-')+'-dev'
    metadata.update(id=user+'/'+name, title=name, code_file='run_train.py', is_private='true')
    (out/'kernel-metadata.json').write_text(json.dumps(metadata,indent=2), encoding='utf-8')
    (out/'preparation_manifest.json').write_text(json.dumps({'mode':args.mode,'dev_only':True,'submitted':False,'canonical_trainer_sha256':sha(source/'run_train_stage1_v6_hardneg.py'),'input_hashes':hashes,'budget_note':'Same epochs are not equal optimizer steps across weighting modes; compare recorded steps and effective samples before attributing causality.'},indent=2),encoding='utf-8')
    (out/'README.md').write_text('# Private Kaggle dev-only weight trial\n\nGenerated from the canonical trainer; regenerate after editing it. No local optimizer execution. Gold IDs are read for exclusion/validation; Gold metrics are not scored.\n\nSubmit explicitly when a training gap warrants this trial:\n\n```powershell\npython -m kaggle kernels push -p '+args.out.replace('\\','/')+'\n```\n\nDo not overwrite prior kernel outputs. Use dev metrics to select trials, then freeze the checkpoint before regression/holdout scoring.\n',encoding='utf-8')
    print('Prepared private Kaggle package:',out)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--mode',choices=['loss_only','sampling_only','legacy_both'],default='loss_only')
    parser.add_argument('--out',default='training/kaggle/kernel_dense_first_loss_only_dev')
    main(parser.parse_args())
