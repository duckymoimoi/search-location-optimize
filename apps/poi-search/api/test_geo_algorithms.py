"""Dependency-free algorithm tests. Does not simulate an OpenSearch analyzer/model."""
import ast
from collections import defaultdict
from datetime import datetime, UTC
import json
import math
from pathlib import Path
import re
from types import SimpleNamespace
import time
import unicodedata
import unittest
import uuid

ROOT = Path(__file__).parent
SOURCE = ast.parse((ROOT / 'app.py').read_text(encoding='utf-8'))
POLICY = json.loads((ROOT / 'search_policy.json').read_text(encoding='utf-8'))

class HTTPException(Exception):
    def __init__(self, status_code, detail):
        self.status_code, self.detail = status_code, detail

# Execute real top-level functions; omit API decorators and import-time model loading.
functions = [node for node in SOURCE.body if isinstance(node, ast.FunctionDef)]
for node in functions:
    node.decorator_list = []
module = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), *functions], type_ignores=[])
ns = dict(globals(), LEXICAL_CONFIG=POLICY['lexical'], RANKING_POLICY=POLICY['ranking'],
          BRANCH_DEPTH=50, RRF_CONSTANT=60, CORPUS_VERSION='hn-poi-stable-v1',
          RETRIEVAL_PROFILE='hybrid', INDEX_NAME='test')
exec(compile(ast.fix_missing_locations(module), str(ROOT / 'app.py'), 'exec'), ns)

def doc(i, name='Bệnh viện 108', address='Trần Hưng Đạo', **kw):
    return dict(canonical_id=str(i), search_label=name, search_aliases=[], address=address,
                ranking_point={'lat':21.0, 'lon':105.8}, **kw)

def evidence(docs):
    return {d['canonical_id']: {'rrf': 1/(60+i)} for i,d in enumerate(docs,1)}

class Algorithms(unittest.TestCase):
    def test_no_destructive_name_rewrite(self):
        for q in ['Hoàng Mai','cửa hàng Tiến','Việt Anh','Trương Định']:
            self.assertEqual(ns['expand_query'](q), q)

    def test_expansion_is_supplementary(self):
        body = json.dumps(ns['lexical_body']('bv 108', 50), ensure_ascii=False)
        self.assertIn('bv 108', body)
        self.assertIn('bệnh viện 108', body)
        for clause in ns['lexical_body']('B12',50)['query']['bool']['should']:
            self.assertNotIn('fuzziness', clause.get('multi_match', {}))

    def test_minimum_should_match_by_token_count(self):
        self.assertEqual(ns['lexical_body']('ga', 50)['query']['bool']['minimum_should_match'], 1)
        self.assertEqual(ns['lexical_body']('hàng bún', 50)['query']['bool']['minimum_should_match'], 1)
        self.assertEqual(
            ns['lexical_body']('kfc hàng bún', 50)['query']['bool']['minimum_should_match'], 2
        )

    def test_name_address_evidence_brand_street(self):
        street = doc(1, 'Phố Bồ Đề', 'Phường Bồ Đề, Long Biên')
        shop = doc(2, 'Phở Bò 149', '149, Đường Đê La Thành, Nam Đồng, Đống Đa')
        decoy = doc(3, 'Phở Bò Yến', '86, Phố Cửa Bắc, Phường Ba Đình, Hà Nội, Thành phố Hà Nội')
        school = doc(5, 'Trường Tiểu học Bồ Đề', '103-105, Phố Bồ Đề')
        # Street name that shares tokens with a city word still counts via contiguous span.
        cafe = doc(4, 'Highlands Coffee', '12, Phố Hà Nội, Phường Cầu Giấy')
        self.assertGreaterEqual(
            ns['name_address_evidence']('pho bo de la thanh', shop), 0.5
        )
        self.assertEqual(ns['name_address_evidence']('pho bo de la thanh', street), 0.0)
        # Lone «thành» inside «Thành phố…» is not a contiguous street span.
        self.assertEqual(ns['name_address_evidence']('pho bo de la thanh', decoy), 0.0)
        # «Phố Bồ Đề» must not satisfy «pho bo de la thanh» without la/thanh.
        self.assertEqual(ns['name_address_evidence']('pho bo de la thanh', school), 0.0)
        self.assertGreaterEqual(
            ns['name_address_evidence']('highlands coffee ha noi', cafe), 0.5
        )
        # Short / street-only queries stay inactive.
        self.assertEqual(ns['name_address_evidence']('pho bo', shop), 0.0)
        self.assertEqual(ns['name_address_evidence']('đê la thành', shop), 0.0)

    def test_name_address_priority_promotes_over_street_collision(self):
        street = doc(1, 'Phố Bồ Đề', 'Phường Bồ Đề, Long Biên')
        shop = doc(2, 'Phở Bò 149', '149, Đường Đê La Thành, Nam Đồng, Đống Đa')
        docs = [street, shop]
        ev = {'1': {'rrf': 1.0}, '2': {'rrf': 0.25}}
        ranked = ns['rank_candidates']('pho bo de la thanh', docs, ev, None)
        self.assertEqual([row[3]['canonical_id'] for row in ranked], ['2', '1'])
        # Contiguous full-name street query is not rewritten by the gate.
        only_street = ns['rank_candidates']('pho bo de', docs, ev, None)
        self.assertEqual(only_street[0][3]['canonical_id'], '1')

    def test_merge_nearby_name_rescue_prepends(self):
        ids = ['far1', 'far2']
        evidence = {
            'far1': {'rrf': 0.02, 'lexical_rank': 1, 'dense_rank': 2},
            'far2': {'rrf': 0.015, 'lexical_rank': 3, 'dense_rank': 4},
        }
        merged, evidence2, n = ns['merge_nearby_name_rescue'](
            'winmart+', ids, evidence, ['near1', 'far1', 'near2']
        )
        self.assertEqual(n, 2)
        self.assertEqual(merged[:2], ['near1', 'near2'])
        self.assertTrue(evidence2['near1']['nearby_rescue'])
        self.assertGreater(evidence2['near1']['rrf'], evidence2['far1']['rrf'])

    def test_accent_match_priority_beats_fold_collision(self):
        lang = doc(1, 'Di Tích Lịch Sử Chùa Láng')
        mausoleum = doc(2, 'Lăng Chủ tịch Hồ Chí Minh')
        docs = [lang, mausoleum]
        ev = {'1': {'rrf': 1.0}, '2': {'rrf': 0.5}}
        ranked = ns['rank_candidates']('lăng chủ tịch', docs, ev, None)
        self.assertEqual(ranked[0][3]['canonical_id'], '2')
        # Unaccented phrase must also beat a 1-token fold hit («Láng»).
        unaccented = ns['rank_candidates']('lang chu tich', docs, ev, None)
        self.assertEqual(unaccented[0][3]['canonical_id'], '2')

    def test_numeric_slash_and_prefix(self):
        self.assertEqual(ns['token_overlap']('B12', doc(1,'B1','')),0)
        self.assertEqual(ns['token_overlap']('16/2', doc(1,'Nhà','16/20')),0)
        self.assertEqual(ns['token_overlap']('star', doc(1,'Starbucks','')),0.5)
        self.assertEqual(ns['token_overlap']('starbucks', doc(1,'Star','')),0)

    def test_address_evidence(self):
        self.assertEqual(ns['token_overlap']('bệnh viện 108 trần hưng đạo',doc(1)),1)

    def test_accent_exact_distinction(self):
        self.assertTrue(ns['is_exact_text_match']('VẠN HẠNH',doc(1,'Vạn Hạnh')))
        self.assertFalse(ns['is_exact_text_match']('Van Hanh',doc(1,'Vạn Hạnh')))

    def test_candidate_budget_no_rank_gate(self):
        docs=[doc(i, f'POI {i}') for i in range(100)]
        output=ns['candidate_documents']([d['canonical_id'] for d in docs], docs[::-1])
        self.assertEqual(len(output),50)
        self.assertEqual(output[-1]['canonical_id'],'49')

    def test_nearby_branches_not_collapsed(self):
        # Same name but far apart → keep both (distinct places / branches).
        near = doc(1, 'Cafe')
        far = doc(2, 'Cafe')
        far['ranking_point'] = {'lat': 21.05, 'lon': 105.8}  # ~5.5 km
        self.assertEqual(len(ns['candidate_documents'](['1', '2'], [near, far])), 2)

    def test_normalized_name_within_m_collapses_osm_dupes(self):
        a = doc(1, 'Gần ngã tư DT379 - Rừng Cọ', category='public_transport=platform')
        b = doc(2, 'Gần ngã tư DT379 - Rừng Cọ', category='public_transport=platform')
        b['ranking_point'] = {'lat': 21.0 + 20 / 111_195, 'lon': 105.8}  # ~20 m
        self.assertEqual(
            [d['canonical_id'] for d in ns['candidate_documents'](['1', '2'], [a, b])],
            ['1'],
        )
        # Distinct branch_id → keep both even when close.
        b['branch_id'] = 'b2'
        a['branch_id'] = 'b1'
        self.assertEqual(len(ns['candidate_documents'](['1', '2'], [a, b])), 2)

    def test_entity_and_access_point_collapse(self):
        docs=[doc(1,entity_group_id='g'),doc(2,entity_group_id='g'),
              doc(3,'Branch Cafe',entity_group_id='g',branch_id='b'),
              doc(4,'Entrance A',entity_group_id='g',preserve_individual_access_point=True),
              doc(5,'Platform B',entity_group_id='g',category='public_transport=platform')]
        self.assertEqual([d['canonical_id'] for d in ns['candidate_documents'](['1','2','3','4','5'],docs)],['1','3','4','5'])

    def test_query_only_keeps_retrieval_order(self):
        # Same phrase quality → keep retrieval order. Better phrase still wins.
        docs=[doc(1,'Khac'),doc(2,'Van Hanh')]
        ranked=ns['rank_candidates']('Van Hanh',docs,evidence(docs),None)
        self.assertEqual(ranked[0][3]['canonical_id'], '2')
        tied=[doc(1,'Van Hanh A'),doc(2,'Van Hanh B')]
        tied_ranked=ns['rank_candidates']('Van Hanh',tied,evidence(tied),None)
        self.assertEqual([row[3]['canonical_id'] for row in tied_ranked],['1','2'])

    def test_geo_cannot_rescue_wrong_numeric_identifier(self):
        d=doc(1,'B1','')
        anchor=d['ranking_point']
        base=ns['rank_candidates']('B12',[d],evidence([d]),None)[0][0]
        contextual=ns['rank_candidates']('B12',[d],evidence([d]),anchor)[0][0]
        self.assertEqual(base,contextual)

    def test_suggest_shape_budget_and_raw_query(self):
        docs=[doc(i, f'POI {i}') for i in range(50)]
        captured=[]
        old_retrieve=ns['retrieve']
        ns['retrieve']=lambda q: (captured.append(q) or [d['canonical_id'] for d in docs], 'hybrid', {}, evidence(docs))
        ns['runtime']=SimpleNamespace(sessions={'s'},documents=lambda ids:docs,exposures={})
        payload=SimpleNamespace(expected_corpus_version='hn-poi-stable-v1',session_id='s',query='bv 108',
             origin=None,top_k=5,request_id='r',context_revision=1,context_time=None)
        try:
            result=ns['suggest'](payload,False)
            self.assertEqual(captured,['bv 108'])
            self.assertEqual(result['candidate_count'],50)
            self.assertEqual(len(result['results']),5)
            self.assertEqual(set(result), {'request_id','context_revision','exposure_id','selectable','versions',
                'scope_summary','resolved_context_time','history_version','candidate_count','results','degraded_reasons','timings_ms'})
            self.assertEqual(set(result['results'][0]), {'poi_id','name','rank','address_text','context_text',
                'ranking_point','routing_point','pickup_access_verified','ranking_distance_m'})
        finally:
            ns['retrieve']=old_retrieve

    def test_selection_ownership(self):
        ns['runtime']=SimpleNamespace(exposures={'e':dict(session_id='owner',context_revision=1,displayed=True,shown_ids=['p'])},selections={})
        payload=SimpleNamespace(session_id='other',exposure_id='e',context_revision=1,idempotency_key='k',selected_poi_id='p')
        with self.assertRaises(HTTPException) as caught:
            ns['select'](payload)
        self.assertEqual(caught.exception.status_code,409)

class GeoReranking(unittest.TestCase):
    def setUp(self):
        self.anchor = {'lat': 21.0, 'lon': 105.8}
        self.docs = [doc(1,'Trường Tiểu học Đại Mỗ'), doc(2,'Trường Tiểu học Đại Từ'),
                     doc(3,'Trường Tiểu học Đại Hưng'), doc(4,'Trường Tiểu học Đại Áng')]
        for d, km in zip(self.docs, [19.7,11.5,0.885,14.8]):
            d['ranking_point'] = {'lat':21.0 + km/111.195,'lon':105.8}
        self.ev = {d['canonical_id']: {'rrf':score} for d,score in zip(self.docs,[1,.95,.52,.50])}

    def ids(self, query, anchor=True):
        return [r[3]['canonical_id'] for r in ns['rank_candidates'](query,self.docs,self.ev,self.anchor if anchor else None)]

    def test_screenshot_ambiguous_school_near_first(self):
        self.assertEqual(self.ids('tiểu học đại')[0], '3')

    def test_explicit_far_school_preserved(self):
        self.assertEqual(self.ids('tiểu học đại mỗ')[0], '1')

    def test_query_only_unchanged(self):
        self.assertEqual(self.ids('tiểu học đại',False), ['1','2','3','4'])

    def test_incompatible_near_poi_cannot_take_head(self):
        self.docs[2]['search_label'] = 'Trường Trung học Đại Hưng'
        ids = self.ids('tiểu học đại')
        self.assertNotEqual(ids[0], '3')
        # Weaker phrase match sorts after contiguous «tiểu học đại» hits.
        self.assertEqual(ids[-1], '3')

    def test_tail_low_evidence_not_promoted(self):
        self.ev['3']['rrf'] = .1
        self.assertNotEqual(self.ids('tiểu học đại')[0], '3')

    def test_numeric_and_accent_equivalence(self):
        self.assertIsNone(ns['name_match_class']('B12',doc(1,'B1')))
        self.assertIsNone(ns['name_match_class']('16/2',doc(1,'16/20')))
        self.assertNotEqual(ns['name_match_class']('Vạn Hạnh',doc(1,'Vạn Hạnh Mall')),
                            ns['name_match_class']('Vạn Hạnh',doc(1,'Van Hanh Mall')))

    def test_unknown_head_distance_preserves_order(self):
        self.docs[0]['ranking_point'] = None
        self.assertEqual(self.ids('tiểu học đại'), ['1','2','3','4'])

    def test_same_band_uses_retrieval_order(self):
        for d in self.docs:
            d['ranking_point'] = self.anchor.copy()
        self.assertEqual(self.ids('tiểu học đại'), ['1','2','3','4'])

if __name__ == '__main__':
    unittest.main()
