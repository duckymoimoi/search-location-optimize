"""Recompute fusion/ranking from frozen branch traces, without GPU inference."""
import argparse
from functools import lru_cache
import hashlib
import json
from pathlib import Path

from es_client import ElasticsearchClient
from settings import ES_URL, INDEX_NAME
import ranking
from ranking import candidate_document_stages, rank_candidates_traced, _hybrid_evidence, _lexical_evidence
from textnorm import compact_length
from dense_first_ablation import evaluate, digest, dump
from brand_router import BrandRouter


def main(args):
    source = Path(args.source)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    client = ElasticsearchClient(ES_URL)
    cache = {}
    router = BrandRouter('data/vietnam/train_stage1_brand_lookup_v3/brand_lookup_v3.sqlite')
    ranking.fold = lru_cache(maxsize=100000)(ranking.fold)
    feature_caches = []
    def cached(function):
        values = {}
        feature_caches.append(values)
        def wrapped(query, doc):
            key = query, doc['canonical_id']
            if key not in values:
                values[key] = function(query, doc)
            return values[key]
        return wrapped
    for name in ('name_match_class', 'name_address_evidence', 'mixed_text_number_signals', 'token_overlap', 'accent_token_coverage'):
        setattr(ranking, name, cached(getattr(ranking, name)))
    fields = ['canonical_id', 'search_label', 'search_aliases', 'address', 'ranking_point', 'housenumber', 'entity_group_id', 'branch_id', 'category', 'preserve_individual_access_point']
    manifest = {'role': 'dev', 'status': 'running', 'source_manifest': json.loads((source/'manifest.json').read_text(encoding='utf-8')),
                'source_trace_sha256': digest(source/'queries.jsonl'), 'index': INDEX_NAME, 'fusion_depth': 100,
                'note': 'Replayed from frozen k=100 ANN and lexical branches. Serving depth50 emulation uses prefixes of k100 ANN, not a new ANN k50 request.',
                'source_hashes': {str(p): digest(p) for p in [Path(__file__),Path(ranking.__file__)]}}
    dump(out/'manifest.json',manifest)
    with (source/'queries.jsonl').open(encoding='utf-8') as stream, (out/'queries.jsonl').open('w',encoding='utf-8') as target:
        for i, line in enumerate(stream):
            row = json.loads(line)
            if row['status'] != 'ok':
                raise ValueError('Cannot use failed source traces')
            for values in feature_caches:
                values.clear()
            lex = [c['poi_id'] for c in row['candidates']['lexical']]
            ann = [c['poi_id'] for c in row['candidates']['dense']]
            union = list(dict.fromkeys(lex+ann))
            missing = [x for x in union if x not in cache]
            if missing:
                result = client.request('POST',f'/{INDEX_NAME}/_mget',{'docs':[{'_id':x,'_source':fields} for x in missing]})
                cache.update({x['_id']:x['_source'] for x in result['docs'] if x.get('found')})
            if any(x not in cache for x in union):
                raise ValueError('Metadata missing')
            fused, evidence = _hybrid_evidence(lex, ann, depth=100)
            row['stages']['hybrid_raw'] = fused[:100]
            for budget in (50,100):
                ds = candidate_document_stages(fused,[cache[x] for x in fused],budget=budget)
                row['stages'][f'hybrid_dedup_{budget}']=[d['canonical_id'] for d in ds['after_dedup']]
                row['stages'][f'hybrid_cap_{budget}']=[d['canonical_id'] for d in ds['after_cap']]
                for profile in ('dedup_only','name_address','name_quality','current'):
                    ranked = rank_candidates_traced(row['query_text'],ds['after_cap'],evidence,None,profile=profile)
                    row['stages'][f'hybrid_{profile}_{budget}']=[r[3]['canonical_id'] for r in ranked['final']]
            if compact_length(row['query_text']) < 5:
                order, ev = lex[:50], _lexical_evidence(lex[:50])
            else:
                order, ev = _hybrid_evidence(lex,ann,depth=50)
            docs = candidate_document_stages(order,[cache[x] for x in order],budget=50)['after_cap']
            final = rank_candidates_traced(row['query_text'],docs,ev,None,profile='current')['final']
            row['stages']['hybrid_serving50_emulation']=[r[3]['canonical_id'] for r in final]
            family = router.family(row['query_text'])
            row['brand_route_family'] = family
            row['stages']['gated_candidate'] = row['stages']['hybrid_raw'] if family else row['stages']['ann_name_quality_50']
            target.write(json.dumps(row,ensure_ascii=False)+'\n')
            if (i+1)%200==0:
                print(f'replay {i+1}',flush=True)
    report = evaluate(out)
    manifest['status']='complete'
    dump(out/'manifest.json',manifest)
    print('Replay complete',out,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',required=True)
    parser.add_argument('--out',required=True)
    main(parser.parse_args())
