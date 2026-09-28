"""Evaluate catalog-gated ANN+lexical on frozen dev traces, without GPU."""
import argparse
import json
from pathlib import Path

from brand_router import BrandRouter
from textnorm import compact_length
from dense_first_ablation import evaluate, dump, digest
from ranking import _hybrid_evidence


def main(args):
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    router = BrandRouter(args.lookup)
    counts = {}
    with (out/'queries.jsonl').open('w',encoding='utf-8') as target:
        for source in args.sources:
            with (Path(source)/'queries.jsonl').open(encoding='utf-8') as stream:
                for line in stream:
                    row = json.loads(line)
                    family = router.family(row['query_text'], fuzzy=args.fuzzy)
                    if family:
                        mode, route = 'hybrid_raw', 'brand_exact'
                    elif compact_length(row['query_text']) < 5:
                        mode, route = 'lexical', 'short_prefix'
                    else:
                        mode, route = 'ann_raw', 'entity_dense'
                    row['stages']['gated_candidate'] = row['stages'][mode][:100]
                    if family and args.membership:
                        allowed = router.members(family)
                        if allowed:
                            lex = [c['poi_id'] for c in row['candidates']['lexical'] if c['poi_id'] in allowed]
                            dense = [c['poi_id'] for c in row['candidates']['dense'] if c['poi_id'] in allowed]
                            if lex and dense:
                                merged, _ = _hybrid_evidence(lex, dense, depth=100)
                            else:
                                merged = lex or dense
                            row['stages']['gated_candidate'] = merged[:100]
                    row['brand_route_family'] = family
                    row['gated_route'] = route
                    key = row['suite']+':'+row['normalizer']+':'+route
                    counts[key] = counts.get(key,0)+1
                    target.write(json.dumps(row,ensure_ascii=False)+'\n')
    manifest = {'status':'complete','role':'dev','training':False,'branch_depth':100,'candidate_budget':100,
                'lookup_sha256':digest(args.lookup),'source_trace_hashes':{s:digest(Path(s)/'queries.jsonl') for s in args.sources},
                'routes':counts,'fuzzy':args.fuzzy,'membership':args.membership,'rule':'Accepted unambiguous full catalog alias => hybrid raw; optional family membership filter and letter-only compact edit1 on long full keys; unknown compact<5 => lexical; otherwise ANN raw. No name/address/geo reranking.'}
    dump(out/'manifest.json',manifest)
    evaluate(out)
    print(json.dumps(counts),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--sources',nargs='+',required=True)
    parser.add_argument('--lookup',default='data/vietnam/train_stage1_brand_lookup_v3/brand_lookup_v3.sqlite')
    parser.add_argument('--out',required=True)
    parser.add_argument('--fuzzy',action='store_true')
    parser.add_argument('--membership',action='store_true')
    main(parser.parse_args())
