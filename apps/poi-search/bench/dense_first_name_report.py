"""Replay bounded full-name lookup on frozen traces; no GPU inference."""
import argparse
import json
from pathlib import Path

from es_client import ElasticsearchClient
from settings import ES_URL
from name_lookup import lookup_name_candidates
from brand_router import BrandRouter
from dense_first_ablation import evaluate, dump, digest


def main(args):
    out=Path(args.out)
    out.mkdir(parents=True,exist_ok=False)
    client=ElasticsearchClient(ES_URL)
    router=BrandRouter('data/vietnam/train_stage1_brand_lookup_v3/brand_lookup_v3.sqlite')
    matches=0;count=0
    with (out/'queries.jsonl').open('w',encoding='utf-8') as target:
        for source in args.sources:
            with (Path(source)/'queries.jsonl').open(encoding='utf-8') as stream:
                for line in stream:
                    row=json.loads(line)
                    if row['normalizer']!='raw':continue
                    base=row['stages'].get('gated_candidate',row['stages']['ann_raw'])
                    candidates=[]
                    if not router.family(row['query_text'],fuzzy=True):
                        candidates,ms=lookup_name_candidates(client,row['query_text'])
                        candidates=[r for r in candidates if r['poi_id'] not in router.all_member_ids]
                        row['timings_ms']['name_lookup']=ms
                    else:
                        row['timings_ms']['name_lookup']=0.0
                    ids=[r['poi_id'] for r in candidates]
                    row['stages']['name_lookup_candidate']=list(dict.fromkeys(ids+base))[:100]
                    row['name_lookup_candidates']=candidates
                    matches+=bool(ids);count+=1
                    target.write(json.dumps(row,ensure_ascii=False)+'\n')
                    if count%200==0:print('name replay',count,flush=True)
    dump(out/'manifest.json',{'role':args.role,'status':'complete','training':False,'name_lookup_limit':50,
                             'n_queries':count,'n_promoted':matches,'source_hashes':{s:digest(Path(s)/'queries.jsonl') for s in args.sources},
                             'note':'Uniqueness within bounded lexical candidates, not guaranteed global uniqueness. Scoped source-identity synthetic test is not real-traffic or all-intent holdout.'})
    evaluate(out)
    print('Name replay complete',count,'promotions',matches,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--sources',nargs='+',required=True)
    parser.add_argument('--out',required=True)
    parser.add_argument('--role',default='dev')
    main(parser.parse_args())
