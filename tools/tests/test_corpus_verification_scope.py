from pathlib import Path
import json
import sys

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from build_clean_poi_corpus_v3 import digest
from verify_clean_poi_corpus_v3 import verify


def make_release(folder):
    folder.mkdir()
    records={
        'pois_core.parquet':[{'poi_id':'a','name':'ABC'}],
        'search_documents.parquet':[{'poi_id':'a','name':'ABC','passage_context':'ABC | address'}],
        'pois.parquet':[{'poi_id':'a','name':'ABC'}],
        'pois_access_enrichment.parquet':[{'poi_id':'a'}],
        'poi_regions.parquet':[{'poi_id':'a'}],
        'poi_id_migration.parquet':[{'old_poi_id':'a','canonical_poi_id':'a','action':'keep','distance_to_canonical_m':None}],
    }
    for name,rows in records.items():pq.write_table(pa.Table.from_pylist(rows),folder/name)
    manifest={'source_corpus_path':str(folder/'missing_source'),'source_hashes':{'input.parquet':'missing'},
              'artifact_hashes':{name:digest(folder/name) for name in records},
              'migration_actions':{'keep':1},'counts':{'output_rows':1}}
    (folder/'manifest.json').write_text(json.dumps(manifest))


def test_artifact_scope_is_explicit_and_never_claims_provenance(tmp_path):
    folder=tmp_path/'release';make_release(folder)
    with pytest.raises(ValueError,match='Full provenance unavailable'):verify(folder)
    report=verify(folder,scope='artifacts')
    assert report['verdict']=='PASS' and report['source_provenance_verified'] is False
    assert report['missing_source_files']==['input.parquet']


def test_artifact_scope_still_rejects_tampered_payload(tmp_path):
    folder=tmp_path/'release';make_release(folder)
    (folder/'pois_core.parquet').write_bytes(b'corrupted')
    with pytest.raises(ValueError,match='Artifact hash mismatch'):verify(folder,scope='artifacts')
