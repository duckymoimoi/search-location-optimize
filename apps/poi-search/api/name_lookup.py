"""Bounded catalog full-name lookup; independent of dense similarity scores."""
import re
import time

from brand_router import within_one_edit
from lexical import lexical_body
from settings import INDEX_NAME
from textnorm import fold, letter_compact


def strong_full_name_match(query, document):
    q = fold(query)
    address = fold(document.get('address') or '')
    for raw in [document.get('search_label', ''), *(document.get('search_aliases') or [])]:
        name = fold(raw)
        if not name:
            continue
        if q == name:
            return 'full_name_exact'
        if address and q == name + ' ' + address:
            return 'full_name_address_exact'
        if re.findall(r'\d+', q) != re.findall(r'\d+', name):
            continue
        left, right = letter_compact(q), letter_compact(name)
        if min(len(left), len(right)) < 7:
            continue
        if within_one_edit(left, right):
            return 'full_name_letter_edit1'
        if len(left) == len(right):
            different = [i for i, (a,b) in enumerate(zip(left,right)) if a != b]
            if len(different) == 2:
                i,j = different
                if j == i+1 and left[i] == right[j] and left[j] == right[i]:
                    return 'full_name_letter_transpose'
    return None


def lookup_name_candidates(client, query, limit=50):
    started = time.perf_counter()
    body = lexical_body(query, limit)
    body['_source'] = ['canonical_id','search_label','search_aliases','address']
    response = client.request('POST',f'/{INDEX_NAME}/_search',body)
    trusted = {}
    for hit in response['hits']['hits']:
        kind = strong_full_name_match(query,hit.get('_source') or {})
        if kind:
            trusted[hit['_id']] = {'poi_id':hit['_id'],'source':'name_lookup','raw_score':hit.get('_score'),
                                    'score_kind':'bm25_composite','match_type':kind}
    # Ambiguous strong matches are not promoted. This is bounded candidate
    # uniqueness, not a proof of global uniqueness across the whole catalog.
    candidates = list(trusted.values()) if len(trusted) == 1 else []
    return candidates, (time.perf_counter()-started)*1000
