"""Dependency-free algorithm tests. Does not simulate an OpenSearch analyzer/model."""
import ast
from collections import defaultdict
from datetime import datetime, timedelta, UTC
import json
import math
from pathlib import Path
import re
import sys
from types import SimpleNamespace
import time
import unicodedata
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).parent))
import demo_users

ROOT = Path(__file__).parent
POLICY = json.loads((ROOT / 'search_policy.json').read_text(encoding='utf-8'))
ALGO_FILES = (
    'textnorm.py', 'lexical.py', 'ranking.py', 'geo.py', 'es_query.py', 'pipeline.py', 'app.py',
)

class HTTPException(Exception):
    def __init__(self, status_code, detail):
        self.status_code, self.detail = status_code, detail

# Execute real top-level functions; omit API decorators and import-time model loading.
functions = []
for name in ALGO_FILES:
    source = ast.parse((ROOT / name).read_text(encoding='utf-8'))
    for node in source.body:
        if isinstance(node, ast.FunctionDef):
            node.decorator_list = []
            functions.append(node)
module = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), *functions], type_ignores=[])
ns = dict(globals(), LEXICAL_CONFIG=POLICY['lexical'], RANKING_POLICY=POLICY['ranking'],
          BRANCH_DEPTH=50, RRF_CONSTANT=60, CORPUS_VERSION='hn-poi-stable-v1',
          RETRIEVAL_PROFILE='hybrid', INDEX_NAME='test', POLICY=POLICY,
          RELEASE_ID='test-release', MODEL_ID='test-model',
          EMBEDDING_SPACE_ID='test-space', PASSAGE_BUILDER_VERSION='test-passage',
          known_user=demo_users.known_user, history_snapshot=demo_users.history_snapshot,
          append_selection=demo_users.append_selection, public_users=demo_users.public_users)
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

    def test_dotted_code_stays_one_lexical_token(self):
        self.assertEqual(ns['glue_code_spans']('s10.2'), 's102')
        self.assertEqual(ns['glue_code_spans']('s1.02'), 's102')
        self.assertEqual(ns['glue_code_spans']('s2-02'), 's202')
        self.assertEqual(ns['glue_code_spans']('16/2 lê văn khương'), '16/2 lê văn khương')
        self.assertEqual(ns['compact_length']('s10.2'), ns['compact_length']('s102'))
        self.assertEqual(ns['compact_length']('s1.02'), ns['compact_length']('s1.02'.replace('.', '')))
        self.assertEqual(ns['compact_length']('16/2'), 4)
        for raw in ('s10.2', 's1.02', 's102'):
            clauses = ns['lexical_body'](raw, 20)['query']['bool']['should']
            analyzed = []
            codes = []
            for clause in clauses:
                analyzed_query = (clause.get('multi_match') or clause.get('match_phrase') or {}).get('query')
                if analyzed_query:
                    analyzed.append(analyzed_query)
                if 'codes_compact' in clause.get('terms', {}):
                    codes = clause['terms']['codes_compact']
            self.assertTrue(analyzed)
            self.assertTrue(all(item == 's102' for item in analyzed))
            self.assertIn('s102', codes)
            self.assertNotIn('s10', codes)
            self.assertNotIn('02', codes)

    def test_expansion_is_supplementary(self):
        body = json.dumps(ns['lexical_body']('bv 108', 50), ensure_ascii=False)
        self.assertIn('bv 108', body)
        self.assertIn('bệnh viện 108', body)
        for clause in ns['lexical_body']('B12',50)['query']['bool']['should']:
            self.assertNotIn('fuzziness', clause.get('multi_match', {}))

    def test_minimum_should_match_by_token_count(self):
        # Policy locks MSM at 1: a higher floor zeroed recall on multi-token gold queries.
        self.assertEqual(ns['lexical_body']('ga', 50)['query']['bool']['minimum_should_match'], 1)
        self.assertEqual(ns['lexical_body']('hàng bún', 50)['query']['bool']['minimum_should_match'], 1)
        self.assertEqual(
            ns['lexical_body']('kfc hàng bún', 50)['query']['bool']['minimum_should_match'], 1
        )

    def _lexical_parts(self, query):
        should = ns['lexical_body'](query, 20)['query']['bool']['should']
        bm25, phrases, codes, bonuses = [], [], [], []
        for clause in should:
            multi = clause.get('multi_match') or {}
            if multi.get('query') and 'fuzziness' not in multi:
                bm25.append(multi['query'])
            for payload in (clause.get('match_phrase') or {}).values():
                if isinstance(payload, dict) and payload.get('query'):
                    phrases.append(payload['query'])
            terms = clause.get('terms') or {}
            if 'codes_compact' in terms:
                codes.extend(terms['codes_compact'])
            if 'constant_score' in clause:
                bonuses.append(clause)
        return bm25, phrases, codes, bonuses

    def _number_bonus_count(self, bonuses):
        return sum(1 for clause in bonuses if clause['constant_score'].get('boost') == 1.5)

    def test_pure_number_does_not_enter_bm25_beside_letters(self):
        bm25, phrases, codes, bonuses = self._lexical_parts('33 Lạc Trung')
        self.assertTrue(bm25)
        self.assertTrue(all(item == 'lac trung' for item in bm25))
        self.assertIn('lac trung', phrases)
        self.assertIn('33 Lạc Trung', phrases)
        self.assertEqual(codes, [])
        self.assertEqual(self._number_bonus_count(bonuses), 1)
        self.assertTrue(any(clause['constant_score'].get('boost') == 1.5 for clause in bonuses))
        # Letter-only and code-only queries keep the previous BM25 text.
        letters, _, letter_codes, letter_bonuses = self._lexical_parts('hàng bún')
        self.assertIn('hàng bún', letters)
        self.assertEqual(letter_codes, [])
        self.assertEqual(letter_bonuses, [])
        code_bm25, _, code_keys, code_bonuses = self._lexical_parts('B12')
        self.assertTrue(all(item == 'B12' for item in code_bm25))
        self.assertEqual(code_keys, ['b12'])
        self.assertEqual(code_bonuses, [])
        # A slash number is a number, not a glued code.
        slash_bm25, _, slash_codes, slash_bonuses = self._lexical_parts('16/2 lê văn khương')
        self.assertTrue(all(item == 'le van khuong' for item in slash_bm25))
        self.assertEqual(slash_codes, [])
        self.assertEqual(self._number_bonus_count(slash_bonuses), 1)

    def test_query_structure_house_path_vs_name_number(self):
        slash = ns['parse_query_structure']('259/15 Nguyễn Chí Thanh')
        self.assertEqual(slash.leading_path, ('259', '15'))
        self.assertEqual(slash.named_letters, ('nguyen', 'chi', 'thanh'))
        self.assertTrue(slash.has_house_street)
        self.assertEqual(slash.path_keys, ('259 15',))
        alley = ns['parse_query_structure']('259 ngõ 15 Nguyễn Chí Thanh')
        self.assertEqual(alley.leading_path, slash.leading_path)
        self.assertEqual(alley.path_keys, slash.path_keys)
        self.assertTrue(alley.has_house_street)
        numbered_street = ns['parse_query_structure']('Đường 3 Tháng 2')
        self.assertEqual(numbered_street.leading_path, ())
        self.assertTrue(numbered_street.has_medial_number)
        self.assertFalse(numbered_street.has_house_street)
        self.assertEqual(numbered_street.path_keys, ())
        brand_number = ns['parse_query_structure']('Highlands 259')
        self.assertEqual(brand_number.leading_path, ())
        self.assertFalse(brand_number.has_house_street)
        self.assertEqual(brand_number.path_keys, ())
        brand_house_street = ns['parse_query_structure']('WinMart 30/48D Nguyễn Văn Linh')
        self.assertEqual(brand_house_street.leading_path, ())
        self.assertIn(('30', '48d'), brand_house_street.inner_paths)
        self.assertIn('30 48d', brand_house_street.path_keys)
        code = ns['parse_query_structure']('s10.2')
        self.assertEqual(code.path_keys, ())
        self.assertEqual(ns['housenumber_path_key']('259/15'), '259 15')
        self.assertEqual(ns['housenumber_path_key']('30/48D'), '30 48d')
        self.assertEqual(ns['glue_code_spans']('16/2 lê văn khương'), '16/2 lê văn khương')

    def test_house_street_lexical_uses_catalog_fields_not_name_prefix(self):
        body = json.dumps(ns['lexical_body']('259/15 Nguyễn Chí Thanh', 20), ensure_ascii=False)
        self.assertIn('housenumber_path_key', body)
        self.assertIn('259 15', body)
        self.assertNotIn('search_label.prefix', body)
        street_only = json.dumps(ns['lexical_body']('Nguyễn Chí Thanh', 20), ensure_ascii=False)
        self.assertIn('search_label.prefix', street_only)
        self.assertNotIn('housenumber_path_key', street_only)
        numbered = json.dumps(ns['lexical_body']('Đường 3 Tháng 2', 20), ensure_ascii=False)
        self.assertIn('Đường 3 Tháng 2', numbered)
        self.assertNotIn('housenumber_path_key', numbered)
        code_body = json.dumps(ns['lexical_body']('s10.2', 20), ensure_ascii=False)
        self.assertIn('s102', code_body)
        self.assertIn('codes_compact', code_body)
        brand = json.dumps(ns['lexical_body']('Highlands 259', 20), ensure_ascii=False)
        self.assertIn('search_label.prefix', brand)
        inner = json.dumps(ns['lexical_body']('WinMart 30/48D Nguyễn Văn Linh', 20), ensure_ascii=False)
        self.assertIn('30 48d', inner)
        self.assertIn('search_label.prefix', inner)

    def test_letter_span_outranks_bare_number(self):
        street = doc(1, 'Cafe Mai', '12 Lạc Trung')
        bare = doc(2, 'Shop 33', '45 Trần Phú')
        both = doc(3, 'Nhà sách', '33 Lạc Trung')
        syllable = doc(4, 'Trung tâm 33', 'Hai Bà Trưng')
        docs = [bare, syllable, street, both]
        ev = {'1': {'rrf': 0.2}, '2': {'rrf': 1.0}, '3': {'rrf': 0.3}, '4': {'rrf': 0.9}}
        ids = [row[3]['canonical_id'] for row in ns['rank_candidates']('33 Lạc Trung', docs, ev, None)]
        self.assertEqual(ids, ['3', '1', '4', '2'])
        # Unfinished final letter still counts as the same span, ahead of the number.
        prefix_ids = [
            row[3]['canonical_id']
            for row in ns['rank_candidates']('33 Lạc Tru', [bare, street], ev, None)
        ]
        self.assertEqual(prefix_ids, ['1', '2'])

    def test_house_path_rank_prefers_slash_member_over_ngo_name(self):
        cafe = doc(1, 'Cộng Cà Phê', '259/15, Nguyễn Chí Thanh', housenumber='259/15')
        decoy = doc(2, '15, Ngõ 91 Nguyễn Chí Thanh', '15, Ngõ 91 Nguyễn Chí Thanh, Phường Hải Châu', housenumber='15')
        ev = {'1': {'rrf': 1.0}, '2': {'rrf': 0.9}}
        ranked = ns['rank_candidates']('259 ngõ 15 Nguyễn Chí Thanh', [decoy, cafe], ev, None)
        self.assertEqual([row[3]['canonical_id'] for row in ranked], ['1', '2'])
        slash_ranked = ns['rank_candidates']('259/15 Nguyễn Chí Thanh', [decoy, cafe], ev, None)
        self.assertEqual(slash_ranked[0][3]['canonical_id'], '1')

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
        old_retrieve=ns['retrieve_detailed']
        def retrieve_detailed(q):
            captured.append(q)
            return {'ids':[d['canonical_id'] for d in docs],'route':'hybrid','timings':{},
                    'evidence':evidence(docs),'degraded_reasons':[]}
        ns['retrieve_detailed']=retrieve_detailed
        ns['runtime']=SimpleNamespace(sessions={'s'},documents=lambda ids:docs,exposures={})
        payload=SimpleNamespace(expected_corpus_version='hn-poi-stable-v1',session_id='s',query='bv 108',
             origin=None,top_k=5,request_id='r',context_revision=1,context_time=None,demo_user_id=None)
        try:
            result=ns['suggest'](payload,False)
            self.assertEqual(captured,['bv 108'])
            self.assertEqual(result['candidate_count'],50)
            self.assertEqual(len(result['results']),5)
            self.assertEqual(result['history_version'], None)
            self.assertEqual(result['scope_summary']['mode'], 'global')
            self.assertEqual(result['scope_summary']['coverage_id'], 'hn-poi-stable-v1')
            self.assertEqual(result['degraded_reasons'], [])
            self.assertEqual(set(result), {'request_id','context_revision','exposure_id','selectable','versions',
                'scope_summary','resolved_context_time','history_version','candidate_count','results','degraded_reasons','timings_ms'})
            self.assertEqual(set(result['results'][0]), {'poi_id','name','rank','address_text','context_text',
                'ranking_point','routing_point','pickup_access_verified','ranking_distance_m'})
        finally:
            ns['retrieve_detailed']=old_retrieve

    def test_coverage_id_is_not_hanoi_literal(self):
        for path in ROOT.glob('*.py'):
            if path.name.startswith('test_') or path.name.startswith('_'):
                continue
            self.assertNotIn('hanoi-osm-stable-v1', path.read_text(encoding='utf-8'), path.name)

    def test_unknown_demo_user_forbidden(self):
        ns['runtime']=SimpleNamespace(sessions={'s'},documents=lambda ids:[],exposures={})
        payload=SimpleNamespace(expected_corpus_version='hn-poi-stable-v1',session_id='s',query='ga',
             origin=None,top_k=5,request_id='r',context_revision=1,context_time=None,demo_user_id='no-such-user')
        with self.assertRaises(HTTPException) as caught:
            ns['suggest'](payload, True)
        self.assertEqual(caught.exception.status_code, 403)
        self.assertEqual(caught.exception.detail['code'], 'unknown_demo_user')

    def test_query_only_ignores_origin_and_history(self):
        docs=[doc(1,'Trường Tiểu học Đại Mỗ'), doc(2,'Trường Tiểu học Đại Hưng')]
        old_retrieve=ns['retrieve_detailed']
        ns['retrieve_detailed']=lambda q: {'ids':['1','2'],'route':'hybrid','timings':{},
                                            'evidence':evidence(docs),'degraded_reasons':[]}
        ns['runtime']=SimpleNamespace(sessions={'s'},documents=lambda ids:docs,exposures={})
        origin=SimpleNamespace(kind='gps', poi_id=None, accuracy_m=10, observed_at=datetime.now(UTC),
                               point=SimpleNamespace(model_dump=lambda: {'lat':21.0,'lon':105.8}))
        payload=SimpleNamespace(expected_corpus_version='hn-poi-stable-v1',session_id='s',query='tiểu học đại',
             origin=origin,top_k=5,request_id='r',context_revision=1,
             context_time=datetime(2026,6,1,tzinfo=UTC), demo_user_id='demo-repeat')
        try:
            result=ns['suggest'](payload, False)
        finally:
            ns['retrieve_detailed']=old_retrieve
        self.assertIsNone(result['history_version'])
        self.assertEqual(result['scope_summary']['mode'], 'global')
        self.assertEqual([row['poi_id'] for row in result['results']], ['1','2'])

    def test_personalized_history_reorders_equivalent_names(self):
        docs=[doc(1,'Trường Tiểu học Đại Mỗ'), doc(2,'Trường Tiểu học Đại Hưng')]
        old_retrieve=ns['retrieve_detailed']
        ns['retrieve_detailed']=lambda q: {'ids':['1','2'],'route':'hybrid','timings':{},
                                            'evidence':evidence(docs),'degraded_reasons':[]}
        ns['runtime']=SimpleNamespace(sessions={'s'},documents=lambda ids:docs,exposures={})
        ns['history_snapshot']=lambda user, session, cutoff: {'history_version':'demo-history-v1:demo-repeat:live-0','poi_ids':['2']}
        payload=SimpleNamespace(expected_corpus_version='hn-poi-stable-v1',session_id='s',query='tiểu học đại',
             origin=None,top_k=5,request_id='r',context_revision=1,context_time=None,demo_user_id='demo-repeat')
        try:
            result=ns['suggest'](payload, True)
        finally:
            ns['history_snapshot']=demo_users.history_snapshot
            ns['retrieve_detailed']=old_retrieve
        self.assertEqual(result['history_version'], 'demo-history-v1:demo-repeat:live-0')
        self.assertEqual([row['poi_id'] for row in result['results']], ['2','1'])

    def test_history_does_not_override_explicit_name_or_code(self):
        schools=[doc(1,'Trường Tiểu học Đại Mỗ'), doc(2,'Trường Tiểu học Đại Hưng')]
        ranked=ns['rank_candidates']('tiểu học đại mỗ', schools, evidence(schools), None)
        swapped=ns['apply_history_cohort']('tiểu học đại mỗ', ranked, ['2'])
        self.assertEqual(swapped[0][3]['canonical_id'], '1')
        codes=[doc(1,'Nhà B12','B12'), doc(2,'Nhà B1','')]
        code_ranked=ns['rank_candidates']('B12', codes, evidence(codes), None)
        code_swapped=ns['apply_history_cohort']('B12', code_ranked, ['2'])
        self.assertEqual(code_swapped[0][3]['canonical_id'], '1')

    def test_stale_or_inaccurate_gps_drops_anchor(self):
        point=SimpleNamespace(model_dump=lambda: {'lat':21.0,'lon':105.8})
        stale=SimpleNamespace(kind='gps', poi_id=None, accuracy_m=10,
                              observed_at=datetime.now(UTC)-timedelta(seconds=180), point=point)
        anchor, notes=ns['resolve_anchor'](stale)
        self.assertIsNone(anchor)
        self.assertEqual(notes, ['gps_stale'])
        coarse=SimpleNamespace(kind='gps', poi_id=None, accuracy_m=350,
                               observed_at=datetime.now(UTC), point=point)
        anchor, notes=ns['resolve_anchor'](coarse)
        self.assertIsNone(anchor)
        self.assertEqual(notes, ['gps_accuracy'])
        future=SimpleNamespace(kind='gps', poi_id=None, accuracy_m=10,
                               observed_at=datetime.now(UTC)+timedelta(seconds=90), point=point)
        with self.assertRaises(HTTPException) as caught:
            ns['resolve_anchor'](future)
        self.assertEqual(caught.exception.status_code, 422)

    def test_demo_registry_hides_history(self):
        users=demo_users.public_users()
        self.assertEqual([user['demo_user_id'] for user in users], ['demo-cold','demo-repeat','demo-session'])
        self.assertTrue(all(set(user)=={'demo_user_id','label'} for user in users))
        snap=demo_users.history_snapshot('demo-cold','sess', datetime.now(UTC))
        self.assertEqual(snap['poi_ids'], [])
        self.assertTrue(snap['history_version'].startswith('demo-history-v1:demo-cold:live-0'))
        version=demo_users.append_selection('sess-a','demo-session','osm:way/1', datetime.now(UTC))
        self.assertTrue(version.endswith(':live-1'))
        self.assertEqual(demo_users.history_snapshot('demo-session','sess-a', datetime.now(UTC))['poi_ids'], ['osm:way/1'])
        self.assertEqual(demo_users.history_snapshot('demo-session','sess-b', datetime.now(UTC))['poi_ids'], [])
        repeat=demo_users.history_snapshot('demo-repeat','sess-a', datetime.now(UTC))
        self.assertEqual(repeat['poi_ids'][0], 'osm:way/1386515333')

    def test_dense_failure_degrades_hybrid_only(self):
        old_profile = ns['RETRIEVAL_PROFILE']
        old_runtime = ns.get('runtime')

        def install(profile, encode, lexical):
            ns['RETRIEVAL_PROFILE'] = profile
            ns['runtime'] = SimpleNamespace(
                lexical=lexical,
                encode=encode,
                dense=lambda vector: (_ for _ in ()).throw(AssertionError('dense should not run')),
                pool=SimpleNamespace(submit=lambda fn, query: SimpleNamespace(result=lambda: fn(query))),
            )

        try:
            install('lexical_only', lambda query: None, lambda query: (['poi-a'], 1.0))
            lexical_only = ns['retrieve_detailed']('vincom')
            self.assertEqual(lexical_only['degraded_reasons'], [])
            self.assertEqual(lexical_only['route'], 'lexical_only')

            install('hybrid', lambda query: (_ for _ in ()).throw(RuntimeError('encoder')), lambda query: (['poi-a'], 1.0))
            fallback = ns['retrieve_detailed']('vincom')
            self.assertEqual(fallback['degraded_reasons'], ['dense_unavailable'])
            self.assertEqual(fallback['ids'], ['poi-a'])
            self.assertEqual(fallback['route'], 'hybrid_dense_fallback')

            install(
                'hybrid',
                lambda query: (_ for _ in ()).throw(RuntimeError('encoder')),
                lambda query: (_ for _ in ()).throw(RuntimeError('lexical')),
            )
            with self.assertRaises(HTTPException) as caught:
                ns['retrieve_detailed']('vincom')
            self.assertEqual(caught.exception.status_code, 503)
        finally:
            ns['RETRIEVAL_PROFILE'] = old_profile
            if old_runtime is not None:
                ns['runtime'] = old_runtime

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

    def test_exponential_decay_orders_same_name_inside_one_band(self):
        near = doc(2, 'Vincom')
        far = doc(1, 'Vincom')
        near['ranking_point'] = {'lat': 21.0 + 100 / 111_195, 'lon': 105.8}
        far['ranking_point'] = {'lat': 21.0 + 400 / 111_195, 'lon': 105.8}
        ev = {'1': {'rrf': 1.0}, '2': {'rrf': 0.9}}
        ids = [row[3]['canonical_id'] for row in ns['rank_candidates']('vincom', [far, near], ev, self.anchor)]
        self.assertEqual(ids, ['2', '1'])
        self.assertGreater(ns['exponential_distance_points'](100), ns['exponential_distance_points'](400))

    def test_decay_cap_cannot_pass_an_exact_tier(self):
        cap = ns['exponential_distance_points'](0)
        self.assertLess(cap, 1.0)
        self.assertAlmostEqual(cap, 0.35)
        # A full match tier is 1. The largest decay bonus stays strictly below it.
        self.assertLess(cap, 1.0)

if __name__ == '__main__':
    unittest.main()
