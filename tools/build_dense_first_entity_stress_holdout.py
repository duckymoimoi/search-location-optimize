"""Freeze a source-identity synthetic entity test before inference, not a traffic gold."""
import hashlib
import argparse
import json
from pathlib import Path
import re
import sys

import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'apps/poi-search/api'))
from textnorm import fold


def main(args):
    packet=ROOT/args.packet
    out=ROOT/args.out
    out.mkdir(parents=True,exist_ok=False)
    docs=pd.read_parquet(ROOT/'data/vietnam/poi_corpus_v3/search_documents.parquet')
    identities={}
    for row in docs.itertuples(index=False):
        for name in [row.name,*list(row.aliases)]:
            if name:identities.setdefault(fold(name),set()).add(row.poi_id)
    rows=[];rejected=[]
    for line in packet.read_text(encoding='utf-8').splitlines():
        row=json.loads(line);name=row['source_name'];target=row['intended_poi_id'];address=row['source_address'] or ''
        if fold(name)==name.casefold() or identities.get(fold(name))!={target} or not address or len(name+' '+address)>200:
            rejected.append(row['case_id']);continue
        tokens=list(re.finditer(r'[^\W\d_]{4,}',name,re.UNICODE))
        if not tokens:
            rejected.append(row['case_id']);continue
        token=tokens[-1];word=token.group();offset=next((i for i in range(1,len(word)-1) if word[i]!=word[i+1]),None)
        if offset is None:
            rejected.append(row['case_id']);continue
        changed=word[:offset]+word[offset+1]+word[offset]+word[offset+2:]
        typo=name[:token.start()]+changed+name[token.end():]
        if identities.get(fold(typo),set())-{target}:
            rejected.append(row['case_id']);continue
        texts=[name,fold(name),typo,name+' '+address]
        if len(set(texts))!=4:
            rejected.append(row['case_id']);continue
        assert re.findall(r'\d+',name)==re.findall(r'\d+',typo)
        for index,text in enumerate(texts,1):
            rows.append({'suite':'generated_cold_entity','query_id':row['case_id']+f'-q{index:02d}',
                         'group_id':row['case_id'],'query_text':text,'accepted_poi_ids':[target],
                         'stratum':['canonical_name','accent_fold','letter_transpose','address_context'][index-1]})
    if len(rows)<400:raise ValueError('Too few eligible cases; do not relax identity checks')
    text=''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows)
    (out/'sessions.jsonl').write_text(text,encoding='utf-8')
    manifest={'status':'locked_before_inference','role':'generated_cold_entity_stress_test','n_cases':len(rows)//4,'n_queries':len(rows),
              'packet_sha256':hashlib.sha256(packet.read_bytes()).hexdigest(),'sessions_sha256':hashlib.sha256(text.encode('utf-8')).hexdigest(),
              'rejected_cases':rejected,'qrels_basis':'Canonical full name/alias uniquely identifies source POI in frozen corpus; original source-identity invariant under accent fold and one letter transposition. Address copied from same source.',
              'limitations':'Deterministic synthetic queries, not independently human-authored real traffic; not a brand/prefix/address-fallback/geo holdout. Singleton labels do not establish all semantic equivalences.',
              'candidate_outputs_used':False,'prelocked_comparison':'raw ANN vs hybrid current at depth100/budget100; tolerance1pp, paired case bootstrap95% CI. No policy tuning on this test.'}
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Locked',len(rows)//4,'cases /',len(rows),'queries')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--packet',default='artifacts/results/dense_first/holdout_authoring_packet_20260928/targets.jsonl')
    parser.add_argument('--out',default='artifacts/results/dense_first/entity_stress_holdout_20260928')
    main(parser.parse_args())
