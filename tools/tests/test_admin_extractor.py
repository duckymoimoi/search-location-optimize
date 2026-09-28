from pathlib import Path
import sys

import pytest
from shapely.geometry import LineString

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from extract_admin_regions import assemble, extract


def test_open_and_missing_rings_are_not_filled():
    shape,status=assemble([LineString([(0,0),(1,0),(1,1)])],[],[])
    assert shape is None and status=='unclosed_outer_rings'
    assert assemble([],[],['way:1'])==(None,'missing_members')


def test_inner_ring_is_hole():
    outer=LineString([(0,0),(4,0),(4,4),(0,4),(0,0)])
    inner=LineString([(1,1),(2,1),(2,2),(1,2),(1,1)])
    shape,status=assemble([outer],[inner],[])
    assert status=='ok' and shape.area==15


def test_extract_tiny_osm_and_reject_overwrite(tmp_path):
    import pyarrow.parquet as pq
    source=tmp_path/'fixture.osm'
    source.write_text('''<osm version="0.6">
<node id="1" lat="21" lon="105"/><node id="2" lat="21" lon="106"/>
<node id="3" lat="22" lon="106"/><node id="4" lat="22" lon="105"/>
<way id="1"><nd ref="1"/><nd ref="2"/><nd ref="3"/><nd ref="4"/><nd ref="1"/></way>
<relation id="1" version="1"><member type="way" ref="1" role="outer"/>
<tag k="type" v="multipolygon"/><tag k="boundary" v="administrative"/>
<tag k="admin_level" v="4"/><tag k="name" v="Fixture"/></relation></osm>''')
    out=tmp_path/'admin'
    result=extract(source,out)
    assert result['relation_count']==result['geometry_count']==1
    assert result['status']=='candidate_not_activated'
    assert pq.read_table(out/'region_catalog.parquet')['geometry_status'].to_pylist()==['ok']
    with pytest.raises(FileExistsError):extract(source,out)
