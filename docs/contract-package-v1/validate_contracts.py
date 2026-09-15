"""Validate deliverable contracts, not implementation or retrieval quality."""
import copy
import json
import re
from pathlib import Path

from jsonschema import Draft202012Validator
from openapi_spec_validator import validate


def main():
    root = Path(__file__).resolve().parent
    load = lambda name: json.loads((root / name).read_text(encoding='utf-8'))
    api = load('contracts/openapi.json')
    validate(api)
    for name in ['contracts/model_bundle.schema.json', 'contracts/release.schema.json']:
        Draft202012Validator.check_schema(load(name))
    examples = load('contracts/examples.json')
    def check(name, value):
        schema = {'$ref': '#/components/schemas/' + name, 'components': api['components']}
        Draft202012Validator(schema).validate(value)
    check('SuggestRequest', examples['query_only_request'])
    check('PersonalizedRequest', examples['personalized_request'])
    check('SuggestResponse', examples['empty_response'])
    rejected = []
    bad = copy.deepcopy(examples['query_only_request'])
    bad['origin'] = {'kind': 'map', 'point': {'lat': 21, 'lon': 105}}
    rejected.append(('SuggestRequest', bad, 'query-only rejects origin'))
    bad = copy.deepcopy(examples['personalized_request'])
    bad['origin']['point']['lat'] = 91
    rejected.append(('PersonalizedRequest', bad, 'invalid coordinate'))
    bad = copy.deepcopy(examples['personalized_request'])
    bad['origin'] = {'kind': 'poi', 'poi_id': 'x', 'point': {'lat': 21, 'lon': 105}}
    rejected.append(('PersonalizedRequest', bad, 'ambiguous origin type'))
    bad = copy.deepcopy(examples['query_only_request'])
    bad['top_k'] = 50
    rejected.append(('SuggestRequest', bad, 'public budget cap'))
    for schema_name, value, label in rejected:
        try:
            check(schema_name, value)
        except Exception:
            continue
        raise AssertionError(label)
    model = {'schema_version': 'model-bundle-v1', 'kind': 'encoder', 'model_id': 'schema-fixture-only',
             'checkpoint_sha256': 'a'*64, 'files': [{'path': 'weights', 'sha256': 'a'*64}],
             'training_dataset_manifest_sha256': None, 'evaluation_report_path': 'eval.json',
             'precision': 'fp32', 'base_model': 'intfloat/multilingual-e5-small',
             'tokenizer_sha256': 'b'*64, 'embedding_space_id': 'c'*64, 'dimension': 384,
             'pooling': 'attention_mask_mean', 'l2_normalize': True, 'query_prefix': 'query: ',
             'passage_prefix': 'passage: ', 'query_max_length': 64, 'passage_max_length': 192,
             'passage_builder_sha256': 'd'*64, 'fixture_vectors_path': 'smoke.npz'}
    validator = Draft202012Validator(load('contracts/model_bundle.schema.json'))
    validator.validate(model)
    model['dimension'] = 768
    assert not validator.is_valid(model)
    cfg = load('configs/search.json')
    assert cfg['retrieval']['candidate_budget'] == 50
    assert cfg['retrieval']['global_reserved_max'] > 0
    assert cfg['rescue']['geo_slots'] + cfg['rescue']['history_slots'] == 10
    assert cfg['scope']['global_lane_required']
    assert cfg['timeouts_ms']['ranker'] < cfg['timeouts_ms']['request']
    fields = load('contracts/features.json')['ordered_features']
    assert len(fields) == len({f['name'] for f in fields})
    diagrams = re.findall(
        r'```mermaid\n(.*?)```',
        (root / 'SYSTEM_DESIGN.md').read_text(encoding='utf-8'),
        re.S,
    )
    assert len(diagrams) == 5
    for i, diagram in enumerate(diagrams, 1):
        assert diagram.strip() == (
            root / 'diagrams' / f'{i:02d}.mmd'
        ).read_text(encoding='utf-8').strip()
    report = {'passed': True, 'openapi_version': api['openapi'], 'http_paths': len(api['paths']),
              'valid_examples': 3, 'rejected_bad_http_examples': len(rejected),
              'model_bundle_positive_and_dimension_negative': True,
              'feature_count': len(fields), 'mermaid_source_consistency': len(diagrams),
              'not_checked': ['application execution', 'database transactions', 'model weights',
                              'mermaid visual rendering', 'retrieval quality', 'serving latency']}
    (root / 'contract_validation.json').write_text(
        json.dumps(report, indent=2) + '\n', encoding='utf-8'
    )
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
