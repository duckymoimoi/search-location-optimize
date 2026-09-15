"""Build a conservative, versioned POI contract from frozen local evidence.

Run: python build_corpus.py --inputs inputs --output rebuilt
No network, model inference, nearest-house inference or split generation.
"""
import argparse
import hashlib
import json
import math
import re
import unicodedata
from collections import Counter
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from shapely import from_wkb
from shapely.geometry import Point

VERSION = 'hn-poi-stable-v1'
POLICY = 'conservative-address-v1'
ADDRESS_FIELDS = ['housenumber', 'street', 'place', 'unit', 'floor', 'block',
                  'building', 'housename', 'quarter', 'hamlet', 'subdistrict',
                  'district', 'city', 'province', 'postcode', 'country', 'full',
                  'suburb', 'ward', 'neighborhood', 'neighbourhood', 'state']
CONFUSABLES = str.maketrans({'ᴄ': 'c'})  # Deliberately bounded; not all scripts.


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf8')


def clean(value, kind='text'):
    if not isinstance(value, str):
        return None
    if any(unicodedata.category(c) in {'Cc', 'Cf'} for c in value):
        return None
    value = ' '.join(unicodedata.normalize('NFKC', value).translate(CONFUSABLES).split()).strip(' ,;')
    if not value or len(value) > (240 if kind == 'full' else 160):
        return None
    if re.search(r'_|https?://|www\.|\bRAI[- ]\d{2}[- ]|\bR\d{5}\b', value, re.I):
        return None
    # Number / alley slash / building codes survive. Free-form location prose does not.
    if kind in {'housenumber', 'unit', 'floor', 'block'}:
        if len(value) > 40 or not re.fullmatch(r'[\w\s/.,;+()\-]+', value, re.UNICODE):
            return None
        if kind == 'housenumber' and (not any(c.isdigit() for c in value) or len(value.split()) > 5):
            return None
    if kind in {'street', 'place'} and (len(value) > 120 or value.count(',') > 1):
        return None
    return value


def norm(v):
    # Accent-sensitive equality: do not collapse Van Hanh and Van Hạnh.
    return re.sub(r'\s+', ' ', v.casefold()).strip()


def sanitize_address(original):
    result, rejected = {}, {}
    rename = {}  # OSM suburb/ward are not automatically equivalent to subdistrict.
    # Canonical keys take precedence; preserve conflicting alternatives in audit.
    for key in sorted(original, key=lambda k: k in rename):
        dest = rename.get(key, key)
        value = clean(original[key], dest)
        if dest not in ADDRESS_FIELDS or value is None:
            rejected[key] = {'value': original[key], 'reason': 'unsupported_or_invalid_field'}
        elif dest in result and norm(result[dest]) != norm(value):
            rejected[key] = {'value': original[key], 'reason': 'field_alias_conflict'}
        else:
            result[dest] = value
    return result, rejected


def full_pair(a):
    return bool(a.get('housenumber') and (a.get('street') or a.get('place')))


def render_address(a):
    if a.get('full'):
        return a['full']
    parts = []
    # Preserve distinctions: unit A of number 32 is not number 32A.
    for key, prefix in [('unit', 'căn '), ('floor', 'tầng '), ('block', 'khối '), ('building', '')]:
        if a.get(key):
            parts.append(prefix + a[key])
    for key in ADDRESS_FIELDS:
        if key not in {'unit', 'floor', 'block', 'building', 'country', 'full'} and a.get(key):
            if norm(a[key]) not in {norm(v) for v in parts}:
                parts.append(a[key])
    return ', '.join(parts)


def passage(row, mode='context'):
    """Same deterministic text builder for training and corpus encoding."""
    parts = [row['name'] or '']
    if row['aliases']:
        parts.append('Tên khác: ' + '; '.join(row['aliases']))
    if row['brand']:
        parts.append('Thương hiệu: ' + row['brand'])
    if row['ref']:
        parts.append('Mã: ' + row['ref'])
    parts.append('Loại: ' + row['category'])
    address = render_address(row['address'])
    if address:
        parts.append('Địa chỉ OSM: ' + address)
    if mode == 'context':
        c = row['context']
        if c['container_name']:
            parts.append('Khuôn viên: ' + c['container_name'])
        if c['nearby_street']:
            parts.append('Gần: ' + c['nearby_street'])
        if c['admin']:
            parts.append('Vùng theo polygon OSM: ' + ', '.join(v for _, v in c['admin']))
    elif mode != 'address':
        raise ValueError(mode)
    return ' | '.join(p for p in parts if p)


def build(inputs, output):
    output.mkdir(parents=True, exist_ok=True)
    old = pq.read_table(inputs / 'v8_pois.parquet').to_pylist()
    canonical = {r['canonical_id']: r for r in pq.read_table(inputs / 'canonical_evidence.parquet').to_pylist()}
    sources = {'osm:' + r['source_id']: r for r in pq.read_table(inputs / 'osm_source_evidence.parquet').to_pylist()}
    rows, audits, members = [], [], []
    stats = Counter()
    for source in old:
        pid = source['canonical_id']
        base = canonical[pid]
        direct_raw = json.loads(source['address_fields_json'])
        direct, rejected = sanitize_address(direct_raw)
        address = dict(direct)
        provenance = {k: {'source': 'direct_v8_osm_field', 'osm_id': pid} for k in address}
        # v8 omissions act as tombstones: enrichment cannot restore previously removed fields.
        original_address = json.loads(base['address_fields_json'])
        blocked = set(original_address) - set(direct_raw)
        blocked |= set(rejected)
        inherited_accepted, pending = [], []
        v8_enriched = json.loads(source['enriched_address_fields_json'])
        for event in json.loads(source['address_provenance_json']):
            fields = [k for k in event.get('fields', []) if k in v8_enriched and k not in direct_raw]
            if not fields:
                continue
            reason = None
            donor = sources.get(event.get('source_osm_id'))
            if event['source'] != 'containing_osm_area':
                reason = 'node_consensus_or_nearby_not_promoted_to_address'
            elif donor is None:
                reason = 'donor_not_in_frozen_evidence'
            else:
                tags = json.loads(donor['raw_tags_json'])
                geometry = from_wkb(donor['geometry_wkb'])
                candidate, donor_rejected = sanitize_address(json.loads(donor['address_fields_json']))
                is_building = (tags.get('building') or tags.get('building:part')) not in {None, 'no'}
                if not is_building or geometry.geom_type not in {'Polygon', 'MultiPolygon'}:
                    reason = 'only_building_address_inheritance_allowed'
                elif not geometry.is_valid or not donor['geometry_source_complete']:
                    reason = 'invalid_or_incomplete_donor_geometry'
                elif not geometry.covers(Point(source['ranking_lon'], source['ranking_lat'])):
                    reason = 'donor_does_not_cover_ranking_point'
                elif not full_pair(candidate):
                    reason = 'donor_missing_number_and_street_or_place'
                elif any(norm(candidate[k]) != norm(address[k]) for k in candidate.keys() & address.keys()):
                    reason = 'address_conflict'
                elif any(k in blocked for k in ['housenumber', 'street', 'place'] if candidate.get(k)):
                    reason = 'previously_rejected_field'
                elif any(k in donor_rejected for k in ['housenumber', 'street', 'place']):
                    reason = 'donor_address_invalid'
                else:
                    # One coherent number-road tuple; never inherit unit/floor or unrelated admin.
                    for k in ['housenumber', 'street', 'place']:
                        if candidate.get(k) and not address.get(k):
                            address[k] = candidate[k]
                            provenance[k] = {'source': 'validated_containing_building', 'osm_id': event['source_osm_id']}
                            inherited_accepted.append(k)
            if reason:
                pending.append({'event': event, 'reason': reason, 'values': {k: v8_enriched[k] for k in fields}})

        name = clean(source['search_label'])
        aliases = sorted({v for a in source['search_aliases'] if (v := clean(a)) and (not name or norm(v) != norm(name))})
        nearby = clean(source['nearby_street'], 'street')
        distance = source['nearby_street_distance_m']
        if distance is None or not math.isfinite(distance) or not 0 <= distance <= 100:
            nearby = None
        admin = {k: v for k, raw in json.loads(source['admin_context_json']).items() if (v := clean(raw))}
        # Preserve admin context separately: direct tags can describe another naming epoch.
        container = clean(source['spatial_container_name'])
        if container and not source['spatial_container_osm_id']:
            container = None
        context = {'container_name': container,
                   'container_osm_id': source['spatial_container_osm_id'] if container else None,
                   'nearby_street': nearby,
                   'nearby_street_osm_id': source['nearby_street_osm_id'] if nearby else None,
                   'nearby_street_distance_m_approx': distance if nearby else None,
                   'admin': sorted(admin.items())}
        searchable = bool(source['destination_searchable'] and name)
        origin = bool(source['origin_search_eligible'] and name)
        # Routing is accepted only with explicit verification evidence.
        verified = bool(source['pickup_access_verified'] and source['routing_lat'] is not None and source['routing_lon'] is not None)
        routing = {'lat': source['routing_lat'], 'lon': source['routing_lon'], 'quality': 'source_verified'} if verified else None
        status = ('inherited_building' if inherited_accepted else 'direct') if address else 'missing'
        row = {'poi_id': pid, 'name': name, 'aliases': aliases, 'category': source['category'],
               'brand': clean(base['brand']), 'ref': clean(base['ref']),
               'address': {k: address.get(k) for k in ADDRESS_FIELDS}, 'address_status': status,
               'context': context,
               'ranking_point': {'lat': source['ranking_lat'], 'lon': source['ranking_lon'], 'quality': base['ranking_point_method']},
               'routing_point': routing, 'destination_searchable': searchable,
               'origin_search_eligible': origin, 'pickup_access_verified': verified,
               'entity_group_id': source['entity_group_id'], 'branch_id': source['branch_id'],
               'complex_id': source['complex_id'], 'preserve_individual_access_point': source['preserve_individual_access_point']}
        rows.append(row)
        audits.append({'poi_id': pid, 'direct_address_original_json': json.dumps(direct_raw, ensure_ascii=False),
                       'address_provenance_json': json.dumps(provenance, ensure_ascii=False, sort_keys=True),
                       'rejected_fields_json': json.dumps(rejected, ensure_ascii=False, sort_keys=True),
                       'blocked_reintroduction_fields': sorted(blocked),
                       'pending_enrichment_json': json.dumps(pending, ensure_ascii=False, sort_keys=True),
                       'context_provenance_json': source['address_provenance_json'],
                       'admin_provenance_json': source['admin_provenance_json'],
                       'source_osm_timestamp': base['osm_timestamp'],
                       'source_osm_version': base['osm_version'],
                       'entity_resolution_status': source['entity_resolution_status'],
                       'origin_policy': 'v8_origin_policy_and_usable_name',
                       'dropped_aliases': [a for a in source['search_aliases'] if clean(a) is None]})
        for member in source['entity_member_ids']:
            members.append({'poi_id': pid, 'source_osm_id': member, 'entity_group_id': source['entity_group_id']})
        stats['rows'] += 1
        stats['destination_searchable'] += searchable
        stats['origin_search_eligible'] += origin
        stats['pickup_access_verified'] += verified
        stats['with_direct_address'] += bool(direct)
        stats['with_validated_building_inheritance'] += bool(inherited_accepted)
        stats['with_pending_enrichment'] += bool(pending)
        stats['with_rejected_direct_fields'] += bool(rejected)
        if searchable:
            stats['destination_number_street_or_place'] += full_pair(address)
            stats['destination_missing_address'] += not bool(address)

    s = pa.string()
    point = pa.struct([('lat', pa.float64()), ('lon', pa.float64()), ('quality', s)])
    schema = pa.schema([('poi_id', s), ('name', s), ('aliases', pa.list_(s)), ('category', s),
                        ('brand', s), ('ref', s), ('address', pa.struct([(k, s) for k in ADDRESS_FIELDS])),
                        ('address_status', s), ('context', pa.struct([('container_name', s), ('container_osm_id', s),
                         ('nearby_street', s), ('nearby_street_osm_id', s), ('nearby_street_distance_m_approx', pa.float64()),
                         ('admin', pa.map_(s, s))])), ('ranking_point', point), ('routing_point', point),
                        ('destination_searchable', pa.bool_()), ('origin_search_eligible', pa.bool_()),
                        ('pickup_access_verified', pa.bool_()), ('entity_group_id', s), ('branch_id', s),
                        ('complex_id', s), ('preserve_individual_access_point', pa.bool_())])
    table = pa.Table.from_pylist(rows, schema=schema)
    pq.write_table(table, output / 'pois.parquet', compression='zstd')
    pq.write_table(pa.Table.from_pylist(audits), output / 'poi_audit.parquet', compression='zstd')
    pq.write_table(pa.Table.from_pylist(members), output / 'entity_members.parquet', compression='zstd')
    schema_json = {'schema_version': VERSION, 'fields': [{'name': f.name, 'type': str(f.type)} for f in schema]}
    dump(output / 'schema.json', schema_json)
    index = [{'poi_id': r['poi_id'], 'name': r['name'], 'aliases': r['aliases'],
              'address_text': render_address(r['address']),
              'passage_address': passage(r, 'address'), 'passage_context': passage(r, 'context')}
             for r in rows if r['destination_searchable']]
    pq.write_table(pa.Table.from_pylist(index), output / 'search_documents.parquet', compression='zstd')
    # Validate actual artifacts, not unconditional pass flags.
    loaded = pq.read_table(output / 'pois.parquet').to_pylist()
    assert len({r['poi_id'] for r in loaded}) == len(loaded) == len(old)
    assert {r['poi_id'] for r in loaded} == {r['canonical_id'] for r in old}
    assert all(-90 <= r['ranking_point']['lat'] <= 90 and -180 <= r['ranking_point']['lon'] <= 180 for r in loaded)
    assert all(not r['origin_search_eligible'] or r['name'] for r in loaded)
    assert all(not r['destination_searchable'] or r['name'] for r in loaded)
    assert all(not r['pickup_access_verified'] or r['routing_point'] is not None for r in loaded)
    assert all(clean(v, k) == v for r in loaded for k, v in r['address'].items() if v)
    assert all(not re.search(r'_|\bRAI[- ]\d{2}[- ]', d['address_text']) for d in index)
    assert len(index) == stats['destination_searchable']
    dump(output / 'validation.json', {'passed': True, 'statistics': dict(stats),
         'checks': ['unique_and_preserved_ids', 'coordinates', 'search_and_origin_names', 'routing_verification',
                    'sanitized_address', 'no_internal_address_codes', 'index_row_count'],
         'not_verified': ['physical_pickup_access', 'real_world_address_correctness', 'model_retrieval_gain',
                          'freshness_of_admin_labels', 'all_entity_duplicates', 'v8_context_geometry_replay']})
    dump(output / 'manifest.json', {'corpus_version': VERSION, 'policy_version': POLICY,
         'source_dataset_version': 'hnq20k-address-v8', 'source_osm_corpus_version': 'hn-260910-7f1b69b167',
         'source_pbf_sha256': '867d3d6d721b50737b39eedf49fd3542254b7c31831485cce38f3bee4f8908b2',
         'source_snapshot_timestamp': '2026-09-10T20:21:06Z',
         'boundary_relation': 1903516, 'statistics': dict(stats),
         'inputs': {f.name: sha(f) for f in sorted(inputs.glob('*.parquet'))},
         'files': {f.name: sha(f) for f in sorted(output.iterdir()) if f.suffix == '.parquet'},
         'label_policy': 'OSM-source-backed weak evidence; not ground truth or pickup verification',
         'context_policy': 'v8 spatial hints retained separately; approximate distances; never training address truth',
         'entity_policy': 'preserved v8; no new merges; container is not complex membership',
         'license': 'OSM-derived data; retain OpenStreetMap contributors attribution and ODbL metadata from source'})
    return stats


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--inputs', type=Path, default=Path(__file__).parent / 'inputs')
    ap.add_argument('--output', type=Path, default=Path(__file__).parent / 'rebuilt')
    args = ap.parse_args()
    print(json.dumps(dict(build(args.inputs, args.output)), ensure_ascii=False, indent=2))
