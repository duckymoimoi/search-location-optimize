"""Blind cold-POI target packet for independent holdout authoring; not an eval suite."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'apps/poi-search/api'))
from textnorm import fold
from brand_router import BrandRouter


def main(args):
    folder=ROOT/args.out
    folder.mkdir(parents=True,exist_ok=False)
    docs=pd.read_parquet(ROOT/'data/vietnam/poi_corpus_v3/search_documents.parquet')
    pairs=pd.read_parquet(ROOT/'data/vietnam/train_stage1_v6_hardneg_6k_clean/training_pairs.parquet',columns=['poi_id'])
    view=pd.read_parquet(ROOT/'data/vietnam/train_stage1_v6_hardneg_6k_clean/query_train_view.parquet')
    gold=pd.read_parquet(ROOT/'data/vietnam/stage1_eval_suite_v2/gold_stage1_v2_1/query_sessions_v2_1.parquet')
    banned=set(pairs.poi_id.astype(str)) | set(view.intended_poi_id.astype(str)) | set(gold.intended_poi_id.astype(str))
    for packet in args.exclude_packets:
        for line in (ROOT/packet).read_text(encoding='utf-8').splitlines():
            banned.add(json.loads(line)['intended_poi_id'])
    for frame in (view,gold):
        for ids in frame.acceptable_poi_ids:banned.update(ids)
    lookup=BrandRouter(ROOT/'data/vietnam/train_stage1_brand_lookup_v3/brand_lookup_v3.sqlite')
    for ids in lookup.member_ids.values():banned.update(ids)
    docs['name_fold']=docs.name.fillna('').map(fold)
    unique=docs.name_fold.value_counts()
    eligible=docs[~docs.poi_id.isin(banned) & docs.name_fold.map(unique).eq(1) & docs.name.str.len().between(12,80)].copy()
    selected=eligible.sample(n=args.count,random_state=args.seed)
    records=[]
    for i,row in enumerate(selected.itertuples(index=False),1):
        records.append({'case_id':f'cold-entity-{args.seed}-{i:04d}','intended_poi_id':row.poi_id,'source_name':row.name,
                        'source_aliases':list(row.aliases),'source_address':row.address_text,
                        'proposed_acceptable_poi_ids':[row.poi_id],'qrels_status':'pending_independent_semantic_review',
                        'query_status':'not_authored','model_outputs_in_packet':False})
    text=''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records)
    (folder/'targets.jsonl').write_text(text,encoding='utf-8')
    manifest={'status':'authoring_packet_only','is_evaluation_suite':False,'n_targets':len(records),'seed':args.seed,
              'candidate_output_used_for_sampling':False,'pair_id_overlap':0,'train_dev_gold_target_overlap':0,
              'brand_members_excluded':True,'packet_sha256':hashlib.sha256(text.encode('utf-8')).hexdigest(),
              'scope':'Cold named entities only; does not establish unseen brand-family, address fallback, or geo holdout.'}
    (folder/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    (folder/'README.md').write_text('# Independent holdout authoring packet\n\nNot an evaluation suite. Author clean, alias/context, typo and address-context queries without consulting candidate output; verify uniqueness/alias equivalence and annotate all acceptable entities. Confirm POI existence against the frozen corpus, review noisy queries for changed intent, validate IDs/text collisions, and lock the final query/qrel hashes before inference. Do not count proposed singleton qrels as reviewed ground truth. Build brand, prefix, numeric and origin scenarios separately where needed.\n',encoding='utf-8')
    print('Prepared',len(records),'blind cold-POI targets:',folder)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--count',type=int,default=200)
    parser.add_argument('--seed',type=int,default=20260928)
    parser.add_argument('--exclude-packets',nargs='*',default=[])
    parser.add_argument('--out',default='artifacts/results/dense_first/holdout_authoring_packet_20260928')
    main(parser.parse_args())
