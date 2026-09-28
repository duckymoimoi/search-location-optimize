from pathlib import Path
import json
import sys

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from build_clean_poi_corpus_v3 import (
    build, clean_housenumber, is_duplicate_pair, load_protected_targets, plan_decisions_v3,
)


def poi(pid,lat=21.0009,**kw):
    return {'poi_id':pid,'name':'ABC','province':'Ha Noi','address':{},
            'ranking_point':{'lat':lat,'lon':105.8001},**kw}


def plan(rows,gold=None,v6=None):
    return plan_decisions_v3(rows,set(gold or []),set(v6 or []),set())


def test_house_separators_do_not_collapse_intent():
    assert len({clean_housenumber(x) for x in ['12/3','123','12-3','12 3']})==4
    assert clean_housenumber(' 12 / 3A ')==clean_housenumber('12/3a')
    assert not is_duplicate_pair(poi('a',address={'housenumber':'12/3'}),
                                 poi('b',address={'housenumber':'123'}))[0]


def test_bank_atm_and_access_points_not_merged():
    assert not is_duplicate_pair(poi('a',category='amenity=bank'),poi('b',category='amenity=atm'))[0]
    assert not is_duplicate_pair(poi('a',preserve_individual_access_point=True),poi('b'))[0]
    assert is_duplicate_pair(poi('a',category='amenity=bank'),poi('b',category='amenity=bank'))[0]


@pytest.mark.parametrize('lat_a,lat_b',[(21.0009,21.0011),(21.0011,21.0009),(21.00091,21.00092)])
def test_dedup_independent_of_input_order_and_cell_id_order(lat_a,lat_b):
    rows=[poi('a',lat_a),poi('b',lat_b)]
    assert plan(rows)[1]==plan(list(reversed(rows)))[1]=={'b':'a'}


def test_gold_and_train_positives_cannot_drop_or_merge_away():
    rows=[poi('gold',name='한국식당'),poi('train',province=None),poi('g1'),poi('g2'),poi('unprotected')]
    drop,merge,*_=plan(rows,gold=['gold','g1','g2'],v6=['train'])
    assert not drop
    assert not ({'gold','train','g1','g2'} & set(merge))
    assert 'unprotected' in merge


def test_active_registry_loads_all_positives_and_rejects_missing_release(tmp_path):
    suites=tmp_path/'stage1_eval_suite_v2';folder=suites/'gold_stage1_v2_2';folder.mkdir(parents=True)
    registry={'active_gold_poi_release':folder.name,'suites':{}}
    (suites/'suite_registry.json').write_text(json.dumps(registry))
    pq.write_table(pa.Table.from_pylist([{'intended_poi_id':'p1','acceptable_poi_ids':['p1','p2']}]),folder/'queries.parquet')
    assert load_protected_targets(tmp_path)[0]=={'p1','p2'}
    registry['active_gold_poi_release']='missing'
    (suites/'suite_registry.json').write_text(json.dumps(registry))
    with pytest.raises(FileNotFoundError):load_protected_targets(tmp_path)


def test_missing_source_does_not_destroy_existing_output(tmp_path):
    target=tmp_path/'candidate';target.mkdir();marker=target/'keep.txt';marker.write_text('keep')
    with pytest.raises(FileNotFoundError):build(tmp_path/'missing',target,overwrite=True)
    assert marker.read_text()=='keep'


def test_source_cannot_be_output(tmp_path):
    with pytest.raises(ValueError):build(tmp_path,tmp_path,overwrite=True)
