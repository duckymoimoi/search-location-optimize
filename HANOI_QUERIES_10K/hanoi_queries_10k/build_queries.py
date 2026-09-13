"""Hanoi query pilot v3. Run with canonical Parquet and output directory.
No external generation API. Preserves v1 held-out POIs via prior_split_map.parquet.
"""
import bisect, collections, hashlib, json, random, re, sys, unicodedata
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq
from entity_resolution import short_code, resolve_entities
SEED=20260913
VERSION='hnq10k-pilot-v3'
O=Path(sys.argv[2]);O.mkdir(parents=True,exist_ok=True)
SRC=Path(sys.argv[1]); HERE=Path(__file__).parent
R=random.Random(SEED)
CONF={'ᴄ':'c','Ｃ':'C','ｃ':'c'}
def clean(s):
 s=unicodedata.normalize('NFKC',s or '')
 return re.sub(r'\s+',' ',''.join(CONF.get(c,c) for c in s)).strip()
def ascii_text(s):
 return ''.join(c for c in unicodedata.normalize('NFD',clean(s).replace('đ','d').replace('Đ','D')) if not unicodedata.combining(c))
def norm(s):
 return re.sub(r'\s+',' ',re.sub(r'[^a-z0-9/]+',' ',ascii_text(s).lower())).strip()
def hn(s):return re.sub(r'\s+','',clean(s).lower())
INTERNAL=re.compile(r'\bRAI[_ -]?\d|\b(?:parcel|cadastral|internal[_ -]?id)\b|\b(?:thửa đất|tờ bản đồ)\b',re.I)
def bad(s): return bool('_' in s or INTERNAL.search(s) or re.search(r'https?://|[\x00-\x1f]',s))
ROADREF=re.compile(r'^(?:QL|ĐT|DT|ĐH|DH|CT)\s*\.?\s*\d+[A-Z]?(?:\s*[-/]\s*\d+)?$',re.I)
def street_status(s):
 if bad(s):return 'blocked_internal_or_underscore'
 if len(s)>65 or s.count(',')>1 or s.startswith('/'):return 'blocked_malformed'
 if ROADREF.fullmatch(s):return 'road_ref_pattern'
 # Lexical plausibility, NOT authoritative road validation.
 if re.search(r'[a-zA-ZÀ-ỹ]',s) and len(norm(s).split())>=2 and not re.fullmatch(r'[A-Z]{1,5}[- ]?\d+[A-Z]?',s):
  return 'road_name_lexically_plausible'
 return 'unverified_road_name_or_ref'
P=sorted(pq.read_table(SRC).to_pylist(),key=lambda p:p['canonical_id'])
BY={p['canonical_id']:p for p in P}; audit=[]
for p in P:
 original=json.loads(p['address_fields_json']);a={}
 for k,v in original.items():
  v=clean(str(v));status='accepted'
  if bad(v):status='blocked_internal_or_underscore'
  elif k=='street':status=street_status(v)
  elif k=='housenumber' and (len(v)>45 or v.count(',')>1):status='blocked_malformed'
  elif k in ('district','subdistrict','housename','unit') and len(v)>65:status='blocked_malformed'
  if not status.startswith(('blocked','unverified')):a[k]=v
  audit.append({'canonical_id':p['canonical_id'],'field':k,'raw_value':original[k],'normalized_value':v,'status':status,'changed':str(original[k])!=v})
 name=clean(p.get('name') or p.get('brand') or p.get('operator') or p.get('ref'))
 if bad(name) or len(name)>110 or name.count(',')>1:name=''
 address=' '.join(a[k] for k in ['housenumber','street'] if a.get(k))
 label=name or (address if a.get('housenumber') and a.get('street') else '')
 p['_a']=a;p['_name']=name;p['_label']=label
 p['_aliases']=[clean(x) for x in p.get('aliases',[]) if x and not bad(clean(x))]
 p['destination_searchable']=bool(label)
 p['origin_eligibility_policy']=bool(p['origin_eligible'])
 p['origin_display_label']=label or None
 p['origin_search_eligible']=p['origin_eligibility_policy'] and bool(p['origin_display_label'])
 p['_structured']=short_code(label)
 p['_namespace']={k:a[k] for k in ('housename','street') if a.get(k)}
 p['pickup_access_verified']=p['pickup_access_status']=='verified'
 p['_forms']=[label,*p['_aliases']]
 p['_nt']=set(norm(' '.join(p['_forms'])).split())
 p['_category']=p['category'] or 'address_only'
ACTIVE=[p for p in P if p['destination_searchable']]
entity_info,entity_pairs,entity_stats=resolve_entities(P)
# Lineage groups preserve prior held-outs. Merge aliases, exact address and brand;
# these split components must never be interpreted as canonical entity merges.
prior_path=HERE/'prior_split_map.parquet'
prior={x['canonical_id']:x for x in pq.read_table(prior_path).to_pylist()}
parent={p['canonical_id']:p['canonical_id'] for p in P}
def root(i):
 while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
 return i
def union(a,b):
 a,b=root(a),root(b)
 if a!=b:parent[max(a,b)]=min(a,b)
seen={}
for p in P:
 i=p['canonical_id'];a=p['_a'];keys=[]
 if i in prior:keys.append(('prior',prior[i]['leakage_group_id']))
 if p['destination_searchable']:keys += [('name',norm(n)) for n in p['_forms'] if n]
 if a.get('street') and a.get('housenumber'):keys.append(('addr',hn(a['housenumber'])+'|'+norm(a['street'])))
 if p['brand'] and not bad(p['brand']):keys.append(('brand',norm(p['brand'])))
 for k in keys:
  if k in seen:union(i,seen[k])
  else:seen[k]=i
priority={'train':0,'dev_synthetic':1,'test_synthetic':2}
sp={}
for p in P:
 i=p['canonical_id'];g=root(i)
 old=prior.get(i,{}).get('split','train')
 if priority[old]>priority.get(sp.get(g),-1):sp[g]=old
# Search compatibility from cleaned full destination view, not origin pool.
inv=collections.defaultdict(set); sorted_forms=[]
for p in ACTIVE:
 i=p['canonical_id']
 for t in p['_nt']:inv[t].add(i)
 for f in p['_forms']:sorted_forms.append((norm(f),i))
sorted_forms.sort();formkeys=[x[0] for x in sorted_forms]
cache={}
def compatible(anchor,quals,prefix=False):
 key=(anchor,json.dumps(quals,sort_keys=True),prefix)
 if key in cache:return cache[key]
 n=norm(anchor)
 if prefix:
  left=bisect.bisect_left(formkeys,n);right=bisect.bisect_right(formkeys,n+'\uffff')
  ids={i for f,i in sorted_forms[left:right]}
 else:
  sets=[inv[t] for t in n.split()];ids=set.intersection(*sets) if sets else set()
 if quals:
  ids={i for i in ids if all((hn(BY[i]['_a'].get(k,''))==hn(v) if k in ('housenumber','unit') else norm(BY[i]['_a'].get(k,''))==norm(v)) for k,v in quals.items())}
 cache[key]=frozenset(ids);return cache[key]

def compact(s):
 for a,b in [('trung học phổ thông','THPT'),('trung học cơ sở','THCS'),('bệnh viện','BV'),('đại học','ĐH'),('trung tâm thương mại','TTTM'),('ủy ban nhân dân','UBND')]:s=re.sub(a,b,s,flags=re.I)
 return s
TONES={'\u0301':('s','1'),'\u0300':('f','2'),'\u0309':('r','3'),'\u0303':('x','4'),'\u0323':('j','5')}
def ime_keys(s,mode):
 # Rule-generated raw keystream with combined ươ -> uow. Not a browser/IME composition emulator.
 def word(m):
  out='';tone=''
  chars=list(m.group().lower())
  for idx,c in enumerate(chars):
   if c=='đ':out+=('dd' if mode=='telex' else 'd9');continue
   ds=unicodedata.normalize('NFD',c);base=ds[0];marks=ds[1:]
   for mark in marks:
    if mark in TONES:tone=TONES[mark][0 if mode=='telex' else 1]
   if '\u0302' in marks:base=base*2 if mode=='telex' else base+'6'
   elif '\u0306' in marks:base=base+'w' if mode=='telex' else base+'8'
   elif '\u031b' in marks:base=base+'w' if mode=='telex' else base+'7'
   if mode=='telex' and base=='ow' and idx>0:
    previous=unicodedata.normalize('NFD',chars[idx-1])
    if previous[0]=='u' and '\u031b' in previous[1:]:out=out[:-1]
   out+=base
  return out+tone
 return re.sub(r'[^\W\d_]+',word,clean(s),flags=re.U)
def partial_marks(s,wrong=False):
 chars=list(clean(s))
 for i,c in enumerate(chars):
  ds=unicodedata.normalize('NFD',c);marks=[m for m in ds[1:] if m in TONES]
  if marks:
   replacement='\u0301' if marks[0]!='\u0301' else '\u0300'
   ds=''.join(m for m in ds if m not in TONES)+(replacement if wrong else '')
   chars[i]=unicodedata.normalize('NFC',ds);return ''.join(chars)
 return None

def typo(s,rng):
 inds=[i for i,c in enumerate(s) if c.isalpha() and i>0 and s[i-1].isalpha() and c!=s[i-1]]
 if not inds:return None
 j=rng.choice(inds);return s[:j-1]+s[j]+s[j-1]+s[j+1:]

E={x['id']:x for x in json.loads((HERE/'editorial_seeds.json').read_text())}
selected=[];selected_set=set();namecount=collections.Counter()
def take(items,limit):
 count=0
 for p in items:
  i=p['canonical_id']
  if i in selected_set or not p['destination_searchable']:continue
  if namecount[norm(p['_label'])]>=6 and i not in E:continue
  selected.append(p);selected_set.add(i);namecount[norm(p['_label'])]+=1;count+=1
  if count==limit:return
pool=ACTIVE[:];R.shuffle(pool)
take([BY[i] for i in E],len(E))
for brand in ['kfc','starbucks','vincom']:
 take([p for p in pool if norm(p['_name'])==brand],2)
take([p for p in pool if p['_name'] and len(norm(p['_name']).split())==1],250)
take([p for p in pool if not p['_name'] and p['_a'].get('street') and p['_a'].get('housenumber')],350)
take([p for p in pool if p['_a'].get('unit') and (p['_a'].get('housename') or p['_a'].get('street'))],60)
take([p for p in pool if '/' in p['_a'].get('housenumber','') or re.search(r'\b(ngõ|ngách)\b',p['_a'].get('street',''),re.I)],100)
# Round robin category and cell for remaining diversity.
bins=collections.defaultdict(list)
for p in pool:bins[(p['_category'],int(p['ranking_lat']/.04),int(p['ranking_lon']/.04))].append(p)
order=[]
while any(bins.values()):
 for k in sorted(bins):
  if bins[k]:order.append(bins[k].pop())
take(order,2000-len(selected))
assert len(selected)==2000
rows=[]
def add(p,q,cleanq,case,anchor,quals,surface='committed_text',prefix=False,method='grounded_composition'):
 if q is None:return False
 q=clean(q).lower();i=p['canonical_id']
 if not q or bad(q) or 'ᴄ' in q:return False
 if any(r['query']==q for r in rows[-5:] if r['intended_poi_id']==i):return False
 ids=set(compatible(anchor,quals,prefix))
 if i not in ids:return False
 # Raw IME keys and prefixes have no single-target supervision in the core track.
 broad=len(q)<=3 or len(ids)>50
 track='ime_keystream' if surface=='raw_keys' else 'structured_code' if p['_structured'] else 'ambiguity_stress' if broad else 'autocomplete' if prefix else 'retrieval_core'
 missing=bool(quals and any(any(not BY[j]['_a'].get(k) for k in quals) for j in compatible(anchor,{})-ids))
 split=sp[root(i)];cross=any(sp[root(j)]!=split for j in ids)
 review=len(ids)!=1 or missing or prefix or surface=='raw_keys' or case=='editorial_paraphrase'
 rows.append({'query_id':f'hnq10k-v3-{len(rows)+1:05d}','query':q,'clean_query':cleanq,
 'is_structured_code':p['_structured'],'namespace_fields_json':json.dumps(p['_namespace'],ensure_ascii=False),
 'namespace_in_query':any(k in quals and norm(v) in norm(cleanq) for k,v in p['_namespace'].items()),
 'missing_address_sibling':missing,
 'typo_source':ascii_text(p['_label']).lower() if case=='adjacent_transpose' else None,
 'typo_result':q[:len(ascii_text(p['_label']))] if case=='adjacent_transpose' else None,
 'case_type':case,'track':track,'query_surface':surface,'intended_poi_id':i,'query_family_id':'family:'+i,
 'known_compatible_poi_ids':sorted(ids),'compatible_count':len(ids),'evidence_name_anchor':anchor,
 'evidence_qualifiers_json':json.dumps(quals,ensure_ascii=False,sort_keys=True),
 'poi_name':p['_label'],'poi_address':' '.join(p['_a'][k] for k in ['housenumber','street','subdistrict'] if p['_a'].get(k)),
 'category':p['_category'],'destination_searchable':True,'origin_search_eligible':p['origin_search_eligible'],'origin_display_label':p['origin_display_label'],'origin_eligibility_policy':p['origin_eligibility_policy'],
 'pickup_access_verified':p['pickup_access_verified'],'pickup_access_status':p['pickup_access_status'],
 'generation_method':method,'corpus_version':p['corpus_version'],'search_view_version':'hn-search-view-v3',
 'dataset_version':VERSION,'split':split,'leakage_group_id':root(i),'cross_split_compatible':cross,
 'requires_review':review,'human_reviewed':False,'label_completeness':'not_guaranteed',
 'label_status':'weak_review_required' if review else 'weak_unique_under_matching_policy',
 'supervised_training_eligible':split=='train' and not review and not cross and track=='retrieval_core',
 'main_metric_candidate':track=='retrieval_core' and len(ids)==1 and not cross and not missing,
 'keystroke_index':None,'session_id':None,'seed':SEED})
 return True
for num,p in enumerate(selected):
 start=len(rows);n=p['_label'];a=p['_a'];i=p['canonical_id'];rng=random.Random(SEED+num)
 qual={};tail=''
 if p['_name'] and a.get('street'):
  qual={'street':a['street']}
  if a.get('housenumber'):qual['housenumber']=a['housenumber']
  tail=' '.join(qual.get(k,'') for k in ['housenumber','street']).strip()
 if p['_structured'] and not tail and a.get('housename'):
  qual={'housename':a['housename']};tail=a['housename']
 base=tail if tail and norm(tail).startswith(norm(n)+' ') else n+(' '+tail if tail and norm(tail) not in norm(n) else '')
 if i in E:
  add(p,E[i]['queries'][0],E[i]['queries'][0],'editorial_paraphrase',E[i]['anchor'],{},method='codex_authored_per_poi')
 else:add(p,n,n,'clean_name' if p['_name'] else 'address_exact',n,{})
 # One explicit short-prefix case for every POI (duplicates across families valid).
 plen=min([1,2,3,5,8][num%5],max(1,len(n)-1))
 add(p,n[:plen],n[:plen],'prefix_'+str(len(clean(n[:plen]))),n[:plen],{},prefix=True,method='controlled_typing_rule')
 # Raw unfinished IME sequences are isolated from application-visible text.
 if num%5 in [0,1]:
  mode='telex' if num%5==0 else 'vni';keys=ime_keys(base,mode)
  if keys!=ascii_text(base).lower():
   add(p,keys,base,mode+'_raw_keys',n,qual,surface='raw_keys',method='controlled_ime_key_rule')
 elif num%5==2:
  q=partial_marks(base,True)
  if q:add(p,q,base,'wrong_tone',n,qual,method='controlled_typing_rule')
 elif num%5==3:
  q=partial_marks(base,False)
  if q and ascii_text(q)!=q:add(p,q,base,'partial_diacritics',n,qual,method='controlled_typing_rule')
 # Source-grounded namespace; no invented apartment/building identifier.
 if a.get('unit') and (a.get('housename') or a.get('street')):
  aq={k:a[k] for k in ['unit','housename','street','housenumber'] if a.get(k)}
  components=[a['unit'],n]
  for extra in [a.get('housename',''),tail]:
   if extra and norm(extra) not in norm(' '.join(components)):components.append(extra)
  q=' '.join(components)
  add(p,q,q,'unit_with_namespace',n,aq)
 noisy=typo(ascii_text(n).lower(),rng)
 options=[(compact(base),base,'abbreviation' if compact(base)!=base else 'name_address',n,qual),
          (ascii_text(base),base,'no_diacritics',n,qual),
          ((tail+' '+n) if tail else n,n+' '+tail,'address_first',n,qual),
          (noisy+(' '+ascii_text(tail) if tail else '') if noisy is not None else None,base,'adjacent_transpose',n,qual),
          (n+' '+a.get('street',''),n,'name_street',n,{'street':a['street']} if a.get('street') else {}),
          ('tìm '+n,n,'search_phrase',n,{}),('địa chỉ '+n,n,'search_phrase',n,{}),('đến '+n,n,'search_phrase',n,{}),('tìm địa điểm '+n,n,'search_phrase',n,{})]
 for q,c,case,anchor,qs in options:
  if len(rows)-start==5:break
  add(p,q,c,case,anchor,qs,method='controlled_typing_rule' if case in ('no_diacritics','adjacent_transpose') else 'grounded_composition')
 assert len(rows)-start==5,(i,len(rows)-start)
assert len(rows)==10000
# Identical non-stress strings across different held-outs must not become train.
collisions=collections.defaultdict(set)
for r in rows:
 if r['track'] in ('retrieval_core','structured_code'):collisions[norm(r['query'])].add(r['split'])
for r in rows:
 conflict=r['track'] in ('retrieval_core','structured_code') and len(collisions[norm(r['query'])])>1
 r['normalized_query_cross_split']=conflict
 if conflict:r['supervised_training_eligible']=False;r['main_metric_candidate']=False

# Persist every decision reason so artifacts are independently auditable.
for r in rows:
 review_reasons=[];excluded=[];train_excluded=[]
 if r['compatible_count']!=1:review_reasons.append('multiple_compatible_pois');excluded.append('multiple_compatible_pois')
 if r['missing_address_sibling']:review_reasons.append('missing_sibling_address');excluded.append('missing_sibling_address')
 if r['case_type'].startswith('prefix_'):review_reasons.append('unfinished_prefix')
 if r['query_surface']=='raw_keys':review_reasons.append('unverified_ime_keystream')
 if r['case_type']=='editorial_paraphrase':review_reasons.append('editorial_paraphrase')
 if r['track']!='retrieval_core':excluded.append('track:'+r['track'])
 if r['cross_split_compatible']:excluded.append('cross_split_compatible');review_reasons.append('cross_split_compatible')
 if r['normalized_query_cross_split']:excluded.append('normalized_query_cross_split');review_reasons.append('normalized_query_cross_split')
 if r['is_structured_code']:
  review_reasons.append('structured_code_or_short_label')
  if not r['namespace_in_query']:review_reasons.append('namespace_not_in_query')
 r['review_reasons']=review_reasons;r['main_metric_exclusion_reasons']=excluded
 r['requires_review']=bool(review_reasons)
 r['label_status']='weak_review_required' if review_reasons else 'weak_unique_under_matching_policy'
 r['main_metric_candidate']=not excluded
 if r['split']!='train':train_excluded.append('not_train_split')
 train_excluded += excluded+review_reasons
 r['training_exclusion_reasons']=list(dict.fromkeys(train_excluded))
 r['supervised_training_eligible']=not r['training_exclusion_reasons']
 r['structured_metric_candidate']=bool(r['track']=='structured_code' and r['namespace_in_query'] and r['compatible_count']==1 and not r['cross_split_compatible'] and not r['missing_address_sibling'] and not r['normalized_query_cross_split'] and not r['case_type'].startswith('prefix_'))

# Sessions: direct Unicode text is a virtual input simulation; Telex/VNI is a raw
# key stream only, not a claim about text emitted by a specific browser IME.
sessions=[]
for idx,p in enumerate(selected[::10]):
 n=p['_label'];i=p['canonical_id'];mode=['direct_unicode','telex','vni'][idx%3]
 stream=n if mode=='direct_unicode' else ime_keys(n,mode)
 sid=f'hn-session-v3-{idx+1:04d}'
 for j in range(1,len(stream)+1):
  sessions.append({'session_id':sid,'event_index':j,'keystroke_index':j,'query':stream[:j].lower(),
  'input_mode':mode,'query_surface':'committed_text' if mode=='direct_unicode' else 'raw_keys',
  'event_model':'virtual_unicode_character' if mode=='direct_unicode' else 'rule_generated_raw_key_append',
  'input_event':stream[j-1],'is_final':j==len(stream),'intended_poi_id':i,
  'query_family_id':'family:'+i,'split':sp[root(i)],'corpus_version':p['corpus_version'],
  'dataset_version':VERSION,'ime_engine_verified':False})

def writep(name,rs):
 table=pa.Table.from_pylist(rs)
 for column,dtype in [('complex_id',pa.string()),('branch_id',pa.string()),('routing_lat',pa.float64()),('routing_lon',pa.float64())]:
  if column in table.column_names and pa.types.is_null(table.schema.field(column).type):table=table.set_column(table.schema.get_field_index(column),column,table[column].cast(dtype))
 pq.write_table(table,O/name,compression='zstd')
def writej(name,obj):(O/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
def writel(name,rs):
 with (O/name).open('w') as f:
  for r in rs:f.write(json.dumps(r,ensure_ascii=False)+'\n')
writep('queries_10k.parquet',rows);writel('queries_10k.jsonl',rows)
for split in priority:writep(split+'.parquet',[r for r in rows if r['split']==split])
writep('typing_sessions.parquet',sessions)
writep('address_field_audit.parquet',audit)
vocab=collections.Counter((x['normalized_value'],x['status']) for x in audit if x['field']=='street')
writep('street_vocabulary.parquet',[{'street':k[0],'status':k[1],'object_count':v,'evidence':'canonical_OSM_address_field_only'} for k,v in sorted(vocab.items())])
view=[]
for p in P:
 view.append({'canonical_id':p['canonical_id'],'name_raw':p['name'],'display_label_raw':p['display_label'],
 'is_structured_code':p['_structured'],'namespace_fields_json':json.dumps(p['_namespace'],ensure_ascii=False),'search_label':p['_label'],'search_aliases':p['_aliases'],'address_fields_json':json.dumps(p['_a'],ensure_ascii=False,sort_keys=True),
 'category':p['_category'],'destination_searchable':p['destination_searchable'],'origin_search_eligible':p['origin_search_eligible'],'origin_display_label':p['origin_display_label'],'origin_eligibility_policy':p['origin_eligibility_policy'],
 'pickup_access_verified':p['pickup_access_verified'],'pickup_access_status':p['pickup_access_status'],'routing_lat':p['routing_lat'],'routing_lon':p['routing_lon'],'ranking_lat':p['ranking_lat'],'ranking_lon':p['ranking_lon'],
 'corpus_version':p['corpus_version'],'search_view_version':'hn-search-view-v3'})
for v in view:v.update(entity_info[v['canonical_id']])
writep('entity_resolution.parquet',list(entity_info.values()))
writep('entity_candidates.parquet',entity_pairs)
writej('entity_policy.json',entity_stats)
writep('corpus_search_view.parquet',view)
writep('selected_pois.parquet',[v for v in view if v['canonical_id'] in selected_set])
writep('origin_display_candidates.parquet',[v for v in view if v['origin_search_eligible']])
writep('corpus_split_map.parquet',[{'canonical_id':p['canonical_id'],'leakage_group_id':root(p['canonical_id']),
 'split':sp[root(p['canonical_id'])],'has_generated_query':p['canonical_id'] in selected_set} for p in P])
# Exposed v1 test is development evidence, never relabelled as a fresh locked test.
# This version's test is also provisional pending an independent future freeze.
review=[r for r in rows if r['split'] in ('train','dev_synthetic')]
R.shuffle(review)
writel('review_worksheet.jsonl',[{'query_id':r['query_id'],'query':r['query'],'split':r['split'],'track':r['track'],
 'naturalness_1_to_5':None,'acceptable_poi_ids':None,'reviewer':None,'notes':None} for r in review[:280]])
checks={
 '10000_rows':len(rows)==10000,'2000_destinations':len(selected_set)==2000,
 'no_blocked_query_text':all(not bad(r['query']) and 'ᴄ' not in r['query'] for r in rows),
 'all_targets_destination_searchable':all(BY[r['intended_poi_id']]['destination_searchable'] for r in rows),
 'destinations_include_non_origins':any(not r['origin_search_eligible'] for r in rows),
 'targets_in_compatible':all(r['intended_poi_id'] in r['known_compatible_poi_ids'] for r in rows),
 'query_id_unique':len({r['query_id'] for r in rows})==10000,
 'prior_heldouts_not_moved_to_train':all(not (prior.get(p['canonical_id'],{}).get('split') in ('dev_synthetic','test_synthetic') and sp[root(p['canonical_id'])]=='train') for p in P),
 'no_cross_split_core_supervision':all(not r['cross_split_compatible'] and not r['normalized_query_cross_split'] for r in rows if r['supervised_training_eligible']),
 'broad_and_raw_ime_excluded_from_main':all(not r['main_metric_candidate'] for r in rows if r['track'] in ('ambiguity_stress','ime_keystream','autocomplete')),
 'worksheet_has_no_test':all(r['split']!='test_synthetic' for r in review[:280]),
 'prefix_lengths_1_2_3_5_8_present':all(any(r['case_type']=='prefix_'+str(n) for r in rows) for n in [1,2,3,5,8]),
 'ime_and_wrong_tone_present':all(any(r['case_type']==k for r in rows) for k in ['telex_raw_keys','vni_raw_keys','wrong_tone','partial_diacritics']),
 'all_sessions_replay':all(s['query']==(BY[s['intended_poi_id']]['_label'] if s['input_mode']=='direct_unicode' else ime_keys(BY[s['intended_poi_id']]['_label'],s['input_mode']))[:s['keystroke_index']].lower() for s in sessions),
}
assert all(checks.values()),checks
stats={'dataset_version':VERSION,'rows':len(rows),'selected_pois':len(selected_set),
 'entity_resolution':entity_stats,'usable_origin_pool':sum(p['origin_search_eligible'] for p in P),'structured_target_count':sum(p['_structured'] for p in selected),'source_corpus_rows':len(P),'destination_searchable_count':len(ACTIVE),
 'selected_non_origin':sum(not p['origin_search_eligible'] for p in selected),
 'selected_single_token_names':sum(bool(p['_name']) and len(norm(p['_name']).split())==1 for p in selected),
 'selected_address_only':sum(not p['_name'] for p in selected),
 'selected_with_slash':sum('/' in p['_a'].get('housenumber','') or '/' in p['_a'].get('street','') for p in selected),
 'selected_with_unit':sum(bool(p['_a'].get('unit')) for p in selected),
 'cases':dict(collections.Counter(r['case_type'] for r in rows)),
 'tracks':dict(collections.Counter(r['track'] for r in rows)),
 'splits':dict(collections.Counter(r['split'] for r in rows)),
 'generation_methods':dict(collections.Counter(r['generation_method'] for r in rows)),
 'supervised_training_eligible_rows':sum(r['supervised_training_eligible'] for r in rows),
 'main_metric_candidate_rows':sum(r['main_metric_candidate'] for r in rows),
 'unique_query_casefold':len({r['query'].casefold() for r in rows}),
 'query_lengths_1_2_3':dict(collections.Counter(len(r['query']) for r in rows if len(r['query'])<=3)),
 'sessions':200,'session_rows':len(sessions),'blocked_address_fields':sum(x['status'].startswith('blocked') for x in audit),
 'unverified_address_fields':sum(x['status'].startswith('unverified') for x in audit),
 'address_audit_statuses':dict(collections.Counter(x['status'] for x in audit)),
 'source_sha256':hashlib.sha256(SRC.read_bytes()).hexdigest(),'corpus_version':P[0]['corpus_version'],
 'seed':SEED,'pyarrow_version':pa.__version__,'checks':checks,'test_status':'provisional_not_locked'}
writej('validation_report.json',stats)
writej('generation_policy.json',{'version':VERSION,'destination_gate':'clean name/brand/operator/ref OR accepted house+street','origin_gate_used_for_targets':False,'origin_display_gate':'source eligibility AND usable origin_display_label','structured_code_rule':'label length <=2 OR alphanumeric code with digits <=12 characters; heuristic track, not validity verdict','structured_code_main_metric':False,'entity_policy_version':'entity-v1',
 'unicode':'NFKC plus explicit ᴄ -> c mapping; raw retained','street_validation':'lexical plausibility / road-ref regex; not an authoritative road gazetteer',
 'blocked_address':'underscore, internal/cadastral signature, malformed; unverified roads omitted',
 'ime':'raw keystream; no claim of browser composition behavior','split':'prior held-out groups preserved, conflicts promoted to more restrictive split',
 'broad':'after raw IME and structured_code routing, query length <= 3 or compatible_count > 50 -> ambiguity_stress','test_status':'provisional_not_locked','seed':SEED})
print(json.dumps(stats,ensure_ascii=False,indent=2))
