"""Regression checks for destination scope, dirty fields and autocomplete tracks."""
from pathlib import Path
import json
import pyarrow.parquet as pq
O=Path(__file__).parent
r=pq.read_table(O/'queries_10k.parquet').to_pylist()
v={x['canonical_id']:x for x in pq.read_table(O/'corpus_search_view.parquet').to_pylist()}
p=pq.read_table(O/'selected_pois.parquet').to_pylist()
s=pq.read_table(O/'typing_sessions.parquet').to_pylist()
w=[json.loads(x) for x in (O/'review_worksheet.jsonl').read_text().splitlines()]
assert len(r)==10000 and len(p)==2000
assert len({(x['query'],x['intended_poi_id']) for x in r})==10000
assert all(v[x['intended_poi_id']]['destination_searchable'] for x in r)
assert sum(not x['origin_search_eligible'] for x in p)>1000
assert sum(len(x['search_label'].split())==1 for x in p)>200
assert all(any(len(x['query'])==n for x in r) for n in [1,2,3,5,8])
assert all('_' not in x['query'] and 'rai_64' not in x['query'].lower() and 'ᴄ' not in x['query'] for x in r)
assert all(not x['main_metric_candidate'] for x in r if len(x['query'])<=3 or x['compatible_count']>50 or x['query_surface']=='raw_keys')
assert not any(x['split']=='test_synthetic' for x in w)
assert {x['input_mode'] for x in s}=={'direct_unicode','telex','vni'}
for sid in {x['session_id'] for x in s}:
 events=[x for x in s if x['session_id']==sid]
 assert [x['event_index'] for x in events]==list(range(1,len(events)+1))
 assert sum(x['is_final'] for x in events)==1 and events[-1]['is_final']
 assert len({x['split'] for x in events})==1
 assert all(x['query'].startswith(prev['query']) for prev,x in zip(events,events[1:]))
for name in ['HANOI_POI_TWO_STAGE_TECHNICAL_DESIGN.md','HANOI_POI_TECHSTACK_AND_MODELS.md']:
 assert 'hnq10k-pilot-v3' in (O/name).read_text()
result={'passed':True,'rows':len(r),'selected_pois':len(p),'session_states':len(s),'scope':'structural regressions; not semantic ground truth or real IME validation'}
(O/'regression_results.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))

# Behavioral checks for the six pre-training issues, independent of build flags.
import ast,re,unicodedata,random
from shapely.geometry import Point,Polygon
from entity_resolution import collapse_evidence,resolve_entities,collapse_ranked_candidates
module=ast.parse((O/'build_queries.py').read_text())
helpers=[n for n in module.body if isinstance(n,ast.FunctionDef) and n.name in ('clean','ascii_text','ime_keys','typo')]
constants={}
for n in module.body:
 if isinstance(n,ast.Assign):
  for target in n.targets:
   if isinstance(target,ast.Name) and target.id in ('CONF','TONES'):constants[target.id]=ast.literal_eval(n.value)
ns={'unicodedata':unicodedata,'re':re,**constants}
exec(compile(ast.Module(body=helpers,type_ignores=[]),'query_helper_tests','exec'),ns)
assert ns['typo']('7',random.Random(0)) is None
assert ns['typo']('B12',random.Random(0)) is None
assert ns['typo']('B11C',random.Random(0)) is None
assert ns['ime_keys']('trường','telex')=='truowngf'
assert ns['ime_keys']('đường','telex')=='dduowngf'
assert ns['ime_keys']('uwow','telex')=='uwow'  # Do not rewrite literal Latin text.
for x in r:
 if x['case_type']=='adjacent_transpose':
  a,b=x['typo_source'],x['typo_result']
  assert len(a)==len(b)
  diff=[i for i,(aa,bb) in enumerate(zip(a,b)) if aa!=bb]
  assert len(diff)==2 and diff[1]==diff[0]+1 and a[diff[0]]==b[diff[1]] and a[diff[1]]==b[diff[0]]
  assert all(a[i].isalpha() for i in diff)
 assert x['main_metric_candidate']==(not x['main_metric_exclusion_reasons'])
 assert x['requires_review']==bool(x['review_reasons'])
 assert x['supervised_training_eligible']==(not x['training_exclusion_reasons'])
 if x['missing_address_sibling']:assert 'missing_sibling_address' in x['main_metric_exclusion_reasons']
 if x['is_structured_code']:assert not x['main_metric_candidate'] and not x['supervised_training_eligible']
assert all(x['origin_display_label'] for x in v.values() if x['origin_search_eligible'])

def fixture(cid,kind,geometry,**tags):
 return {'canonical_id':cid,'osm_type':kind,'geometry_wkb':geometry.wkb,'ranking_lat':21.,'ranking_lon':105.8,
 '_name':'Cafe Test','_label':'Cafe Test','_category':'amenity=cafe','_a':{'housenumber':'12','street':'Test Street'},'raw_tags_json':json.dumps(tags)}
a=fixture('node/1','node',Point(105.8,21))
b=fixture('way/2','way',Polygon([(105.7999,20.9999),(105.8001,20.9999),(105.8001,21.0001),(105.7999,21.0001)]))
assert collapse_evidence(a,b)[0]
assert not collapse_evidence(a,{**b,'_a':{'housenumber':'14','street':'Test Street'}})[0]
assert not collapse_evidence({**a,'raw_tags_json':'{"entrance":"yes"}'},b)[0]
assert not collapse_evidence({**a,'raw_tags_json':'{"public_transport":"platform"}'},b)[0]
assert not collapse_evidence({**a,'raw_tags_json':'{"branch":"B"}'},b)[0]
assert not collapse_evidence(a,{**b,'osm_type':'node'})[0]
third={**a,'canonical_id':'node/3','_label':'Other','_name':'Other'}
mapping,pairs,stats=resolve_entities([a,b,third])
ranked=[{'canonical_id':'node/1','score':.9},{'canonical_id':'way/2','score':.8},{'canonical_id':'node/3','score':.7}]
assert [x['canonical_id'] for x in collapse_ranked_candidates(ranked,mapping,2)]==['node/1','node/3']
assert len(collapse_ranked_candidates(ranked,mapping,3,enabled=False))==3
ambiguous={**b,'canonical_id':'way/4'}
assert resolve_entities([a,b,ambiguous])[2]['inferred_node_way_links']==0
entity_map=pq.read_table(O/'entity_resolution.parquet').to_pylist()
assert all(len(x['entity_member_ids'])==1 for x in entity_map if x['preserve_individual_access_point'])
result['pretrain_regressions_passed']=True
result['real_ime_replay_verified']=False
(O/'regression_results.json').write_text(json.dumps(result,indent=2)+'\n')
print('Pre-training regressions passed')
