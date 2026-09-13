"""Normalize v5 into v6 without changing query content, splits or qrels.
python build_compact.py --source ../hanoi_queries_20k_v5 --output .
"""
import argparse, collections, hashlib, json, shutil
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq

CORE=['query_id','query','intended_poi_id','query_family_id','split','track','case_type','query_surface']
ELIG=['query_id','supervised_training_eligible','main_metric_candidate','structured_metric_candidate',
      'training_exclusion_reasons','main_metric_exclusion_reasons']
REVIEW=['query_id','ai_reviewed','ai_review_decision','ai_review_scope','ai_review_note','human_reviewed','review_reasons']
POI=['poi_name','poi_address','category','destination_searchable','origin_search_eligible','origin_display_label',
     'origin_eligibility_policy','pickup_access_verified','pickup_access_status','namespace_fields_json']
META=['corpus_version','search_view_version','dataset_version','label_completeness']
DERIVED=['compatible_count','requires_review','label_status','session_id','keystroke_index','leakage_group_id']
REL=['known_compatible_poi_ids']

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,t):pq.write_table(t,p,compression='zstd')
def dump(p,obj):p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--source',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();src,out=a.source.resolve(),a.output.resolve()
    (out/'audit').mkdir(parents=True,exist_ok=True);(out/'reference').mkdir(exist_ok=True)
    t=pq.read_table(src/'queries_20k.parquet');r=t.to_pylist()
    assert len(r)==20000
    for k in META:assert len({x[k] for x in r})==1,k
    assert all(x['session_id'] is None and x['keystroke_index'] is None for x in r)
    assert all(x['compatible_count']==len(x['known_compatible_poi_ids']) for x in r)
    assert all(x['requires_review']==bool(x['review_reasons']) for x in r)
    assert all(x['label_status']==('weak_review_required' if x['requires_review'] else 'weak_unique_under_matching_policy') for x in r)
    write(out/'queries_20k.parquet',t.select(CORE))
    write(out/'eligibility.parquet',t.select(ELIG))
    write(out/'audit/query_review.parquet',t.select(REVIEW))
    moved=set(CORE+ELIG+REVIEW+POI+META+DERIVED+REL)
    gen=['query_id']+[k for k in t.column_names if k not in moved]
    write(out/'audit/query_generation.parquet',t.select(gen))
    # Keep the full canonical search view, not merely selected targets.
    pois=pq.read_table(src/'corpus_search_view.parquet');by={p['canonical_id']:p for p in pois.to_pylist()}
    for x in r:
        p=by[x['intended_poi_id']]
        assert x['poi_name']==p['search_label']
        addr=json.loads(p['address_fields_json'])
        assert x['poi_address']==' '.join(addr[k] for k in ('housenumber','street','subdistrict') if addr.get(k))
        for k in POI[2:]:assert x[k]==p[k],(x['query_id'],k)
    write(out/'pois.parquet',pois.drop(['corpus_version','search_view_version']))
    m=pq.read_table(src/'corpus_split_map_v5.parquet')
    groups={p['canonical_id']:p['leakage_group_id'] for p in m.to_pylist()}
    assert all(groups[x['intended_poi_id']]==x['leakage_group_id'] for x in r)
    write(out/'poi_splits.parquet',m.select(['canonical_id','leakage_group_id','split']))
    # Streaming write; no multi-million-row Python list of dicts.
    qs=pa.schema([('query_id',pa.string()),('poi_id',pa.string())])
    n=0;qids=[];pids=[]
    with pq.ParquetWriter(out/'qrels.parquet',qs,compression='zstd') as writer:
        for x in r:
            ids=x['known_compatible_poi_ids']
            assert x['intended_poi_id'] in ids and len(ids)==len(set(ids))
            assert all(i in by and by[i]['destination_searchable'] for i in ids)
            qids.extend([x['query_id']]*len(ids));pids.extend(ids);n+=len(ids)
            if len(qids)>=100000:
                writer.write_table(pa.Table.from_arrays([pa.array(qids),pa.array(pids)],schema=qs));qids=[];pids=[]
        if qids:writer.write_table(pa.Table.from_arrays([pa.array(qids),pa.array(pids)],schema=qs))
    shutil.copyfile(src/'typing_sessions.parquet',out/'typing_sessions.parquet')
    for name,newname in [('query_lineage.parquet','initial_query_lineage.parquet'),
                          ('ai_review_log.json','ai_review_log.json'),('ai_review_edits.json','ai_review_edits.json'),
                          ('manual_review_choices.json','manual_review_choices.json'),('generation_policy.json','source_generation_policy.json')]:
        shutil.copyfile(src/name,out/'audit'/newname)
    shutil.copyfile(src/'frozen_v3_test.parquet',out/'reference/frozen_v3_test.parquet')
    fieldmap={}
    for k in t.column_names:
        if k in CORE:fieldmap[k]='queries_20k.parquet.'+k
        elif k in ELIG:fieldmap[k]='eligibility.parquet.'+k
        elif k in REVIEW:fieldmap[k]='audit/query_review.parquet.'+k
        elif k in gen:fieldmap[k]='audit/query_generation.parquet.'+k
        elif k in POI:fieldmap[k]='pois.parquet (join intended_poi_id = canonical_id); poi_name = search_label; poi_address = house/street/subdistrict rendering'
        elif k in META:fieldmap[k]='manifest.json.source_record_constants'
        elif k in REL:fieldmap[k]='qrels.parquet.poi_id grouped by query_id'
        else:fieldmap[k]='derived; see SCHEMA.md'
    dump(out/'audit/v5_field_mapping.json',fieldmap)
    stats=dict(dataset_version='hnq20k-compact-v6',query_rows=20000,query_columns=len(CORE),qrel_rows=n,
        poi_rows=pois.num_rows,destination_searchable=sum(p['destination_searchable'] for p in by.values()),
        train_eligible=sum(x['supervised_training_eligible'] for x in r),
        ai_reviewed=sum(x['ai_reviewed'] for x in r),
        splits=dict(collections.Counter(x['split'] for x in r)),
        main_metric_by_split={s:sum(x['main_metric_candidate'] for x in r if x['split']==s) for s in sorted({x['split'] for x in r})},
        core_bytes=(out/'queries_20k.parquet').stat().st_size,source_query_bytes=(src/'queries_20k.parquet').stat().st_size,
        source_sha256={'queries':sha(src/'queries_20k.parquet'),'corpus':sha(src/'corpus_search_view.parquet'),
                       'frozen_test':sha(src/'frozen_v3_test.parquet')},
        source_record_constants={k:r[0][k] for k in META},
        qrels_semantics='known-compatible weak labels only; intended target remains queries.intended_poi_id; no adjudicated relevance grades',
        change_scope='storage normalization only; no query, split, target, compatibility or eligibility changes')
    dump(out/'manifest.json',stats)
    # Validate equivalence against v5, including streaming exact qrel order.
    assert pq.read_table(out/'queries_20k.parquet').equals(t.select(CORE))
    assert pq.read_table(out/'eligibility.parquet').equals(t.select(ELIG))
    assert pq.read_table(out/'audit/query_review.parquet').equals(t.select(REVIEW))
    assert pq.read_table(out/'audit/query_generation.parquet').equals(t.select(gen))
    expected=((x['query_id'],i) for x in r for i in x['known_compatible_poi_ids'])
    seen=0
    for b in pq.ParquetFile(out/'qrels.parquet').iter_batches(batch_size=100000):
        for pair in zip(b.column(0).to_pylist(),b.column(1).to_pylist()):
            assert pair==next(expected);seen+=1
    assert next(expected,None) is None and seen==n
    assert sha(out/'reference/frozen_v3_test.parquet')==stats['source_sha256']['frozen_test']
    dump(out/'validation.json',dict(passed=True,core_equal_v5=True,qrels_equal_v5=True,
        eligibility_equal_v5=True,review_equal_v5=True,generation_audit_equal_v5=True,
        poi_fields_reconstruct_v5=True,all_64_source_fields_accounted_for=len(fieldmap)==64,
        frozen_test_byte_preserved=True,model_evaluation_performed=False))
    print(json.dumps(stats,ensure_ascii=False))

if __name__=='__main__':main()
