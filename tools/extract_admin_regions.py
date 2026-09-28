"""Rebuild an admin candidate from OSM PBF/XML into a NEW directory.

No active dataset is overwritten. Missing rings/members remain explicit; only
valid closed polygons are emitted. Requires osmium, shapely and pyarrow.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from shapely.geometry import LineString, MultiPolygon, mapping
from shapely.ops import polygonize_full, unary_union


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def assemble(outer, inner, missing):
    """Do not join across missing ways or guess which open ring should close."""
    if missing:
        return None, 'missing_members'
    if not outer:
        return None, 'no_outer_ways'
    shell, cuts, dangles, invalid = polygonize_full(outer)
    if any(not g.is_empty for g in (cuts, dangles, invalid)):
        return None, 'unclosed_outer_rings'
    shape = unary_union(list(shell.geoms))
    if inner:
        holes, cuts, dangles, invalid = polygonize_full(inner)
        if any(not g.is_empty for g in (cuts, dangles, invalid)):
            return None, 'unclosed_inner_rings'
        hole_shape = unary_union(list(holes.geoms))
        if not shape.covers(hole_shape):
            return None, 'inner_outside_outer'
        shape = shape.difference(hole_shape)
    if shape.geom_type == 'Polygon':
        shape = MultiPolygon([shape])
    if shape.is_empty or not shape.is_valid or shape.geom_type != 'MultiPolygon':
        return None, 'invalid_polygon'
    return shape, 'ok'


def extract(source: Path, output: Path):
    import osmium
    if output.exists():
        raise FileExistsError(f'Output must be new: {output}')
    if not source.is_file():
        raise FileNotFoundError(source)
    relations = {}; ways = {}; nodes = {}; wanted_ways = set(); wanted_nodes = set()

    class Relations(osmium.SimpleHandler):
        def relation(self, obj):
            tags = dict(obj.tags)
            if tags.get('boundary') != 'administrative' or not tags.get('admin_level', '').isdigit():
                return
            members = [(m.type, m.ref, m.role) for m in obj.members if m.role in {'outer', 'inner', ''}]
            relations[obj.id] = {'id':obj.id, 'version':obj.version, 'tags':tags, 'members':members}
            wanted_ways.update(ref for kind, ref, _ in members if kind == 'w')

    class Ways(osmium.SimpleHandler):
        def way(self, obj):
            if obj.id in wanted_ways:
                refs = [n.ref for n in obj.nodes]
                ways[obj.id] = refs; wanted_nodes.update(refs)

    class Nodes(osmium.SimpleHandler):
        def node(self, obj):
            if obj.id in wanted_nodes and obj.location.valid():
                nodes[obj.id] = (obj.location.lon, obj.location.lat)

    for handler, entities, name in [(Relations(),osmium.osm.RELATION,'relations'),
                                    (Ways(),osmium.osm.WAY,'ways'),(Nodes(),osmium.osm.NODE,'nodes')]:
        with osmium.io.Reader(str(source), entities) as reader:
            osmium.apply(reader, handler)
        print('Read admin',name,flush=True)
    scheme='vn-osm-search-admin-candidate-v2'
    catalog=[]; geometry=[]; shapes={}
    for rel_id, rel in sorted(relations.items()):
        tags=rel['tags'];outer=[];inner=[];missing=[]
        for kind,ref,role in rel['members']:
            if kind!='w':
                if kind=='r':missing.append(f'nested_relation:{ref}')
                continue
            refs=ways.get(ref,[])
            if len(refs)<2 or any(n not in nodes for n in refs):
                missing.append(f'way_or_nodes:{ref}');continue
            (inner if role=='inner' else outer).append(LineString([nodes[n] for n in refs]))
        shape,status=assemble(outer,inner,missing)
        rid=f'osm:relation/{rel_id}';level=int(tags['admin_level'])
        point=shape.representative_point() if shape is not None else None
        role='primary' if level in {2,4,6} else 'audit_only'
        if point is not None and not (102<=point.x<=110 and 8<=point.y<=24):
            role='border_sliver_or_foreign';status='ok_outside_vn_bbox'
        raw=shape.wkb if shape is not None else None
        h=hashlib.sha256(raw).hexdigest() if raw else None
        label=tags.get('name:vi') or tags.get('name') or str(rel_id)
        aliases=sorted({v for k,v in tags.items() if k.startswith(('name:','alt_name')) and v!=label})
        catalog.append({'region_osm_id':rid,'osm_type':'relation','osm_id':rel_id,'osm_version':rel['version'],
                        'admin_level':level,'label':label,'aliases':aliases,
                        'name_tags_json':json.dumps({k:v for k,v in tags.items() if 'name' in k},ensure_ascii=False),
                        'wikidata':tags.get('wikidata'),'parent_ids':[],
                        'bbox':list(shape.bounds) if shape is not None else None,
                        'rep_lon':point.x if point is not None else None,'rep_lat':point.y if point is not None else None,
                        'area_deg2':shape.area if shape is not None else None,'geometry_ref':rid if raw else None,
                        'geometry_status':status,'geometry_missing_json':json.dumps(missing),
                        'boundary_hash':h,'admin_scheme_version':scheme,'scheme_role':role,
                        'member_way_count':sum(kind=='w' for kind,_,_ in rel['members'])})
        if raw:
            shapes[rid]=shape
            geometry.append({'region_osm_id':rid,'osm_id':rel_id,'admin_level':level,'boundary_hash':h,'geometry_wkb':raw})
    # Parent metadata is a representative-point association, not an official
    # administrative hierarchy or a full polygon containment assertion.
    for row in catalog:
        if row['region_osm_id'] not in shapes or row['admin_level'] not in {4,6}:
            continue
        parent_level=2 if row['admin_level']==4 else 4
        point=shapes[row['region_osm_id']].representative_point()
        row['parent_ids']=[r['region_osm_id'] for r in catalog if r['admin_level']==parent_level
                           and r['scheme_role']=='primary' and r['region_osm_id'] in shapes
                           and shapes[r['region_osm_id']].covers(point)]
    schema=pa.schema([(name,typ) for name,typ in [
        ('region_osm_id',pa.string()),('osm_type',pa.string()),('osm_id',pa.int64()),('osm_version',pa.int64()),
        ('admin_level',pa.int64()),('label',pa.string()),('aliases',pa.list_(pa.string())),('name_tags_json',pa.string()),
        ('wikidata',pa.string()),('parent_ids',pa.list_(pa.string())),('bbox',pa.list_(pa.float64())),
        ('rep_lon',pa.float64()),('rep_lat',pa.float64()),('area_deg2',pa.float64()),('geometry_ref',pa.string()),
        ('geometry_status',pa.string()),('geometry_missing_json',pa.string()),('boundary_hash',pa.string()),
        ('admin_scheme_version',pa.string()),('scheme_role',pa.string()),('member_way_count',pa.int64())]])
    gs=pa.schema([('region_osm_id',pa.string()),('osm_id',pa.int64()),('admin_level',pa.int64()),
                  ('boundary_hash',pa.string()),('geometry_wkb',pa.binary())])
    output.mkdir(parents=True,exist_ok=False)
    pq.write_table(pa.Table.from_pylist(catalog,schema=schema),output/'region_catalog.parquet')
    pq.write_table(pa.Table.from_pylist(geometry,schema=gs),output/'region_geometries.parquet')
    preview={'type':'FeatureCollection','features':[{'type':'Feature','geometry':mapping(shapes[r['region_osm_id']]),
             'properties':{'region_osm_id':r['region_osm_id'],'label':r['label']}}
             for r in catalog if r['admin_level']==4 and r['scheme_role']=='primary' and r['region_osm_id'] in shapes]}
    (output/'preview_admin_level_4.geojson').write_text(json.dumps(preview,ensure_ascii=False),encoding='utf-8')
    manifest={'status':'candidate_not_activated','admin_scheme_version':scheme,'source_pbf':str(source),
              'source_pbf_sha256':digest(source),'builder_sha256':digest(__file__),
              'relation_count':len(catalog),'geometry_count':len(geometry),
              'geometry_status_counts':dict(Counter(r['geometry_status'] for r in catalog)),
              'notes':['Representative-point parent association; not an official administrative registry.',
                       'Incomplete rings/nested relation members remain unresolved; never silently filled.'],
              'artifact_hashes':{p.name:digest(p) for p in output.iterdir()}}
    (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pbf',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(extract(args.pbf.resolve(),args.output.resolve()),ensure_ascii=False,indent=2))
