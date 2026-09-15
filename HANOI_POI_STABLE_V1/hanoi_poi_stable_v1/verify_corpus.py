"""Integrity and regression checks against frozen OSM evidence."""
import json
from pathlib import Path
import pyarrow.parquet as pq
from shapely import from_wkb
from shapely.geometry import Point
from build_corpus import clean, sanitize_address, norm


def verify(root):
    rows = {x['poi_id']: x for x in pq.read_table(root / 'pois.parquet').to_pylist()}
    audit = pq.read_table(root / 'poi_audit.parquet').to_pylist()
    sources = {'osm:' + x['source_id']: x for x in pq.read_table(root / 'inputs/osm_source_evidence.parquet').to_pylist()}
    assert clean('Nhà mồ Gia Rai') == 'Nhà mồ Gia Rai'
    assert clean('RAI_64_MD_003', 'street') is None
    assert clean('16/2', 'housenumber') == '16/2'
    assert clean('59,67', 'housenumber') == '59,67'
    assert clean('tiêm ᴄhủng') == 'tiêm chủng'
    assert rows['osm:node/5103138232']['address']['street'] is None
    assert rows['osm:node/5101080628']['address']['street'] is None
    accepted = 0
    for a in audit:
        row = rows[a['poi_id']]
        provenance = json.loads(a['address_provenance_json'])
        for key, proof in provenance.items():
            assert row['address'][key] is not None
            if proof['source'] != 'validated_containing_building':
                continue
            donor = sources[proof['osm_id']]
            geometry = from_wkb(donor['geometry_wkb'])
            assert geometry.covers(Point(row['ranking_point']['lon'], row['ranking_point']['lat']))
            candidate, _ = sanitize_address(json.loads(donor['address_fields_json']))
            assert candidate[key] == row['address'][key]
            assert all(norm(candidate[k]) == norm(row['address'][k]) for k in ['housenumber', 'street', 'place']
                       if candidate.get(k) and row['address'].get(k))
            assert key not in a['blocked_reintroduction_fields']
            accepted += 1
    print(json.dumps({'passed': True, 'accepted_inherited_fields_checked': accepted,
                      'poi_rows': len(rows)}, indent=2))


if __name__ == '__main__':
    verify(Path(__file__).resolve().parent)
