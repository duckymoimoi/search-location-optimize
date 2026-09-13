"""Conservative, inferred node/way collapse; raw canonical records stay intact."""
import collections, hashlib, json, math, re, unicodedata
from shapely import wkb

def key(s):return ' '.join(unicodedata.normalize('NFKC',s or '').casefold().split())
def short_code(s):
 s=key(s)
 return bool(s and (len(s)<=2 or re.fullmatch(r'(?=.{1,12}$)(?=.*\d)[a-z0-9.-]+',s)))
def distance(a,b):
 la,lb=math.radians(a['ranking_lat']),math.radians(b['ranking_lat'])
 x=math.sin((lb-la)/2)**2+math.cos(la)*math.cos(lb)*math.sin(math.radians(b['ranking_lon']-a['ranking_lon'])/2)**2
 return 6371008.8*2*math.asin(min(1,math.sqrt(x)))
def protected(p):
 t=json.loads(p['raw_tags_json']);cat=p.get('_category',p.get('category','')) or ''
 return (t.get('entrance') not in (None,'no') or t.get('public_transport') in ('platform','stop_position')
         or t.get('railway') in ('platform','subway_entrance','tram_stop')
         or t.get('highway')=='bus_stop' or 'platform' in cat)
def collapse_evidence(a,b):
 if {a['osm_type'],b['osm_type']}!={'node','way'}:return False,'not_node_way'
 if protected(a) or protected(b):return False,'protected_platform_entrance_or_stop'
 if short_code(a['_label']) or short_code(b['_label']):return False,'short_or_code_label'
 if not a['_name'] or not b['_name']:return False,'not_named_venue'
 if key(a['_label'])!=key(b['_label']) or a['_category']!=b['_category']:return False,'name_or_category_differs'
 for k in ('housenumber','street'):
  if not a['_a'].get(k) or not b['_a'].get(k):return False,'missing_exact_address'
  if key(a['_a'][k])!=key(b['_a'][k]):return False,'address_conflict'
 ta,tb=json.loads(a['raw_tags_json']),json.loads(b['raw_tags_json'])
 # Extra specificity present on only one side also blocks an automatic merge.
 for k in ('branch','ref','addr:unit','level','brand','operator'):
  if key(ta.get(k))!=key(tb.get(k)):return False,'specificity_conflict:'+k
 node,way=(a,b) if a['osm_type']=='node' else (b,a)
 try:
  geom=wkb.loads(way['geometry_wkb']);point=wkb.loads(node['geometry_wkb'])
  if geom.geom_type not in ('Polygon','MultiPolygon') or not geom.is_valid or not geom.covers(point):return False,'no_valid_polygon_containment'
 except Exception:return False,'geometry_unavailable'
 return True,'same_named_category_exact_address_node_inside_way'

def resolve_entities(pois):
 by={p['canonical_id']:p for p in pois};bins=collections.defaultdict(list)
 for p in pois:
  if p['_label']:bins[(key(p['_label']),p['_category'])].append(p)
 pairs=[];qualified=collections.defaultdict(list)
 for records in bins.values():
  records.sort(key=lambda p:p['ranking_lat'])
  for j,a in enumerate(records):
   for b in records[j+1:]:
    if b['ranking_lat']-a['ranking_lat']>.000901:break
    if distance(a,b)>100:continue
    ok,reason=collapse_evidence(a,b)
    pair={'left_id':a['canonical_id'],'right_id':b['canonical_id'],'distance_m':distance(a,b),
          'pair_qualifies':ok,'reason':reason,'collapse_applied':False,'semantic_verification':'not_human_verified'}
    pairs.append(pair)
    if ok:
     node,way=(a,b) if a['osm_type']=='node' else (b,a)
     qualified[node['canonical_id']].append((way['canonical_id'],pair))
 # A node must match one polygon only. No unrestricted proximity transitivity.
 groups={i:i for i in by}
 for node,options in qualified.items():
  if len(options)==1:
   way,pair=options[0];groups[node]=way;pair['collapse_applied']=True
  else:
   for way,pair in options:pair['reason']='multiple_qualifying_polygons'
 members=collections.defaultdict(list)
 for i,g in groups.items():members[g].append(i)
 result={}
 for i,p in by.items():
  g=groups[i];tags=json.loads(p['raw_tags_json']);branch_id=None
  if tags.get('branch') and p['_a'].get('street') and p['_a'].get('housenumber'):
   # Local serving identity backed by explicit branch tag plus address.
   identity=[key(tags.get('brand') or p['_label']),key(tags['branch']),key(p['_a']['housenumber']),key(p['_a']['street'])]
   branch_id='branch:'+hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:20]
  result[i]={'canonical_id':i,'entity_group_id':'entity:'+g,'entity_member_ids':sorted(members[g]),
   'entity_resolution_status':'inferred_node_way' if len(members[g])>1 else 'singleton',
   'entity_policy_version':'entity-v1','branch_id':branch_id,
   'branch_evidence':'explicit_osm_branch_and_address' if branch_id else 'unknown',
   'complex_id':None,'complex_evidence':'unknown_no_membership_evidence',
   'complex_name_hint':p['_a'].get('housename'),'preserve_individual_access_point':protected(p)}
 stats={'candidate_pairs_100m':len(pairs),'inferred_node_way_links':sum(x['collapse_applied'] for x in pairs),
        'inferred_entity_groups':sum(len(v)>1 for v in members.values()),'explicit_branch_ids':len({x['branch_id'] for x in result.values() if x['branch_id']}),
        'complex_ids_assigned':0,'policy_version':'entity-v1','default':'keep separate unless strict node-way evidence',
        'candidate_radius_m':100,'label_normalization':'NFKC casefold whitespace; preserve accents',
        'auto_collapse_requirements':['node-way pair','same non-code named venue and category','same non-empty house and street','matching branch/ref/unit/level/brand/operator presence and values','node inside valid way polygon','node matches exactly one polygon'],
        'protected_objects':['entrance','platform','stop_position','bus_stop','tram_stop','subway_entrance'],
        'branch_rule':'explicit OSM branch tag plus exact address; local stable ID, not external branch registry',
        'complex_rule':'null without membership evidence; addr:housename is only a name hint'}
 return result,pairs,stats

def collapse_ranked_candidates(candidates,entity_map,top_k=5,enabled=True):
 """Input already sorted by relevance. Keep highest-ranked representative.
 Fetch a deeper ranked list to backfill top_k; never collapse by name/proximity.
 """
 out=[];seen=set()
 for row in candidates:
  cid=row['canonical_id'];info=entity_map[cid]
  group=info['entity_group_id'] if enabled else cid
  if group in seen:continue
  seen.add(group);out.append({**row,'entity_group_id':info['entity_group_id'],
    'entity_member_ids':info['entity_member_ids'],'collapse_enabled':enabled})
  if len(out)>=top_k:break
 return out
