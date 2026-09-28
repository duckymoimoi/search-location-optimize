"""Read-only integrity, spatial linkage and cleaning-policy audit. Never rebuilds data."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import shapely

from build_clean_poi_corpus_v3 import (
    classify_junk_or_foreign, clean_housenumber, is_duplicate_pair,
    load_protected_targets, plan_decisions_v3,
)

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def synthetic_policy_checks():
    def row(pid, lat=21.0009, **kw):
        return {'poi_id': pid, 'name': 'ABC', 'province': 'Hà Nội', 'address': {},
                'ranking_point': {'lat': lat, 'lon': 105.8001}, **kw}
    a, b = row('a'), row('b', lat=21.0011)
    forward = plan_decisions_v3([a, b], set(), set(), set())[1]
    reverse = plan_decisions_v3([b, a], set(), set(), set())[1]
    protected = plan_decisions_v3([row('gold', name='한국식당')], {'gold'}, set(), set())[0]
    protected_pair = plan_decisions_v3([row('gold1'), row('gold2')], {'gold1','gold2'}, set(), set())[1]
    return {
        'non_latin_name_inside_assigned_province': classify_junk_or_foreign(row('x', name='한국식당')),
        'missing_province_with_valid_point': classify_junk_or_foreign(row('x', province=None)),
        'housenumber_keys': {'12/3': clean_housenumber('12/3'), '123': clean_housenumber('123')},
        'slash_housenumber_collision_duplicate': is_duplicate_pair(row('a', address={'housenumber':'12/3','street':'A'}), row('b', address={'housenumber':'123','street':'A'})),
        'different_category_same_name_duplicate': is_duplicate_pair(row('a',category='amenity=bank'),row('b',category='amenity=atm')),
        'gold_marked_as_junk_is_dropped': protected,
        'two_gold_targets_one_merged': protected_pair,
        'cross_grid_input_order_forward_merges': forward,
        'cross_grid_input_order_reverse_merges': reverse,
        'note': 'Synthetic counterexamples to current code, not counts of confirmed errors in the released corpus.',
    }


def main(out):
    out.mkdir(parents=True,exist_ok=False)
    corpus=ROOT/'data/vietnam/poi_corpus_v3';admin=ROOT/'data/vietnam/admin_regions_v1'
    cm=json.loads((corpus/'manifest.json').read_text(encoding='utf-8'))
    am=json.loads((admin/'manifest.json').read_text(encoding='utf-8'))
    core=pq.read_table(corpus/'pois_core.parquet').to_pylist()
    ids=[r['poi_id'] for r in core]; idset=set(ids)
    result={'corpus':{'rows':len(ids),'unique_ids':len(idset),
                      'artifact_hash_matches':{n:sha(corpus/n)==h for n,h in cm['artifact_hashes'].items()},
                      'missing_build_sources':[n for n in cm['source_hashes'] if not (Path(cm['source_corpus_path'])/n).exists()]},
            'admin':{},'policy_counterexamples':synthetic_policy_checks()}
    for name in ['pois.parquet','search_documents.parquet','pois_access_enrichment.parquet']:
        other=pq.read_table(corpus/name,columns=['poi_id'])['poi_id'].to_pylist()
        result['corpus'][name+'_id_order_matches']=other==ids
    gold,v6,train=load_protected_targets(ROOT/'data/vietnam')
    result['protected_target_loader']={'gold_ids_loaded':len(gold),'train_v6_ids_loaded':len(v6),'train_pool_ids_loaded':len(train)}
    print('Integrity and policy audit complete',flush=True)
    catalog=pq.read_table(admin/'region_catalog.parquet').to_pylist()
    geometry_rows=pq.read_table(admin/'region_geometries.parquet').to_pylist()
    geoms=shapely.from_wkb([r['geometry_wkb'] for r in geometry_rows])
    geometry_by_id={r['region_osm_id']:g for r,g in zip(geometry_rows,geoms)}
    meta={r['region_osm_id']:r for r in catalog}
    valid=shapely.is_valid(geoms);empty=shapely.is_empty(geoms)
    result['admin'].update({'catalog_rows':len(catalog),'unique_catalog_ids':len(meta),
                            'geometry_rows':len(geometry_rows),'unique_geometry_ids':len(geometry_by_id),
                            'invalid_geometry':int((~valid).sum()),'empty_geometry':int(empty.sum()),
                            'geometry_types':dict(Counter(shapely.get_type_id(geoms).tolist())),
                            'geometry_ids_outside_catalog':len(set(geometry_by_id)-set(meta)),
                            'status_counts':dict(Counter(r['geometry_status'] for r in catalog)),
                            'role_counts':dict(Counter(r['scheme_role'] for r in catalog)),
                            'missing_geometry_by_level':dict(Counter(str(r['admin_level']) for r in catalog if r['region_osm_id'] not in geometry_by_id)),
                            'boundary_hash_mismatch':sum(r['boundary_hash']!=meta[r['region_osm_id']]['boundary_hash'] for r in geometry_rows),
                            'artifact_hashes':{p.name:sha(p) for p in admin.iterdir() if p.is_file()},
                            'manifest_has_artifact_hashes':bool(am.get('artifact_hashes'))})
    primary=[r for r in catalog if r['scheme_role']=='primary']
    result['admin']['primary_by_level']=dict(Counter(str(r['admin_level']) for r in primary))
    points=shapely.points([r['ranking_point']['lon'] for r in core],[r['ranking_point']['lat'] for r in core])
    shapely.prepare(geoms)
    for column in ['province_region_id','subdistrict_region_id']:
        buckets=defaultdict(list);missing=0;unknown=0;no_geometry=0;outside=[]
        for i,r in enumerate(core):
            rid=r.get(column)
            if not rid:missing+=1;continue
            if rid not in meta:unknown+=1;continue
            if rid not in geometry_by_id:no_geometry+=1;continue
            buckets[rid].append(i)
        for rid,indices in buckets.items():
            covered=shapely.covers(geometry_by_id[rid],points[np.asarray(indices)])
            for i,ok in zip(indices,covered):
                if not ok:outside.append({'poi_id':ids[i],'region_id':rid,'label':meta[rid]['label'],'name':core[i]['name']})
        result['admin'][column]={'missing':missing,'unknown_region':unknown,'assigned_without_geometry':no_geometry,
                                'point_not_covered_by_assigned_polygon':len(outside),'examples':outside[:15]}
        print('Checked',column,flush=True)
    regions=pq.read_table(corpus/'poi_regions.parquet').to_pylist()
    result['memberships']={'rows':len(regions),'unknown_poi':sum(r['poi_id'] not in idset for r in regions),
                           'unknown_region':sum(r['region_osm_id'] not in meta for r in regions),
                           'duplicate_poi_region_pairs':len(regions)-len({(r['poi_id'],r['region_osm_id']) for r in regions}),
                           'boundary_hash_mismatch':sum(r['boundary_hash']!=meta.get(r['region_osm_id'],{}).get('boundary_hash') for r in regions),
                           'levels':dict(Counter(str(r['admin_level']) for r in regions))}
    membership={(r['poi_id'],r['region_osm_id']) for r in regions}
    result['memberships']['core_primary_region_absent_from_membership']=sum(
        (r['poi_id'],r[c]) not in membership for r in core for c in ['province_region_id','subdistrict_region_id'] if r[c])
    migration=pq.read_table(corpus/'poi_id_migration.parquet').to_pylist()
    result['migration']={'rows':len(migration),'unique_source_ids':len({r['old_poi_id'] for r in migration}),
                         'actions':dict(Counter(r['action'] for r in migration)),
                         'bad_destination_ids':sum(r['canonical_poi_id'] is not None and r['canonical_poi_id'] not in idset for r in migration),
                         'drop_reasons':dict(Counter(r['reason'] for r in migration if r['action']=='drop_junk_or_foreign'))}
    pbf=ROOT/'vietnam-260910.osm.pbf'
    result['source_pbf']={'exists':pbf.exists(),'hash_matches_admin_manifest':pbf.exists() and sha(pbf)==am['source_pbf_sha256']}
    result['raw_extract_entrypoint_exists']=(ROOT/'tools/extract_admin_regions.py').exists()
    result['scope']='Read-only artifact/code audit; no source data, label, geometry or index changed.'
    (out/'audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    main(parser.parse_args().out)
