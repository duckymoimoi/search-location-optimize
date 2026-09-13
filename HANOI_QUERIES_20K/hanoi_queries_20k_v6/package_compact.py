"""Describe and package the compact v6 tables after equivalence validation."""
import hashlib, json, shutil, zipfile
from pathlib import Path
import pyarrow.parquet as pq
from load_dataset import load_training, load_evaluation, iter_qrels, load_pois

P=Path(__file__).resolve().parent
m=json.loads((P/'manifest.json').read_text());v=json.loads((P/'validation.json').read_text())
assert v['passed']
assert load_training(P).num_rows==m['train_eligible']
assert load_evaluation(P).num_rows==m['main_metric_by_split']['dev_synthetic']
assert load_pois(P).num_rows==m['destination_searchable']
q=load_evaluation(P).slice(0,1).to_pylist()[0]
hits=[x for t in iter_qrels(P,[q['query_id']]) for x in t.to_pylist()]
assert q['intended_poi_id'] in {x['poi_id'] for x in hits}
v['loaders_checked']=True
(P/'validation.json').write_text(json.dumps(v,indent=2)+'\n')

docs={
'query_id':'Khóa query trong version bundle; không tự chứa version.',
'query':'Chuỗi gõ đầu vào Stage 1; không dùng clean_query thay thế.',
'intended_poi_id':'Đích giả định lúc sinh; FK tới pois.canonical_id, không phải đáp án duy nhất đã xác minh.',
'query_family_id':'Family để nhóm biến thể/bootstrap. Khác leakage_group_id.',
'split':'train / dev_synthetic / test_synthetic / architecture_holdout.',
'track':'retrieval_core / autocomplete / ambiguity_stress / ime_keystream / structured_code.',
'case_type':'Loại biến thể cụ thể; không phải feature lúc serving.',
'query_surface':'committed_text hoặc raw_keys; raw_keys chưa replay bằng engine thật.',
'poi_id':'FK tới pois.canonical_id; một known-compatible weak label.',
'supervised_training_eligible':'Cờ cho phép train đơn đích theo policy v5, bao gồm split=train.',
'main_metric_candidate':'Cờ cho phép core metric; vẫn phải chọn split eval.',
'structured_metric_candidate':'Subset structured có namespace theo policy; không đồng nghĩa main metric.',
'training_exclusion_reasons':'Rỗng iff supervised_training_eligible=true.',
'main_metric_exclusion_reasons':'Rỗng iff main_metric_candidate=true.',
'canonical_id':'Khóa POI, giữ ID corpus.',
'leakage_group_id':'Nhóm chống rò rỉ; không phải entity group.',
'ai_reviewed':'Codex trực tiếp đọc trong scope ghi kèm; không phải human-gold.',
'ai_review_decision':'kept / edited / diagnostic_source_or_intent_uncertain / not_individually_reviewed.',
'ai_review_scope':'Phạm vi review tính hợp lý query và source label, không xác minh địa điểm thực.',
'ai_review_note':'Nhận xét riêng, thường lý do diagnostic.',
'human_reviewed':'Toàn bộ false trong snapshot hiện tại.',
'review_reasons':'Các nghi vấn về nhãn/nguồn, không phải indicator đã có review.'}
tables={}
for f in sorted(P.rglob('*.parquet')):
    pf=pq.ParquetFile(f)
    tables[str(f.relative_to(P))]=dict(rows=pf.metadata.num_rows,fields=[dict(name=x.name,arrow_type=str(x.type),nullable=x.nullable,
        description=docs.get(x.name,'Trường nguồn/audit giữ từ v5; xem audit/v5_field_mapping.json và audit/source_generation_policy.json.')) for x in pf.schema_arrow])
def fieldtable(name):
    return '\n'.join('| `'+x['name']+'` | `'+x['arrow_type']+'` | '+x['description']+' |' for x in tables[name]['fields'])
schema='''# Schema Hanoi POI 20k — compact v6

Version: `hnq20k-compact-v6`, lưu ở manifest.json, không lặp trên từng query. Các bảng active chỉ có một version bundle. Tên và nội dung query, target, split, weak qrels và eligibility giữ nguyên v5.

## Queries: 8 trường

`queries_20k.parquet`: 20.000 dòng, khóa query_id. Đây là bảng dùng hằng ngày.

| Trường | Kiểu Arrow | Ý nghĩa |
|---|---|---|
'''+fieldtable('queries_20k.parquet')+'''

## Nhãn tương thích

`qrels.parquet`: 4.621.105 liên kết, khóa ghép (query_id, poi_id).

| Trường | Kiểu Arrow | Ý nghĩa |
|---|---|---|
'''+fieldtable('qrels.parquet')+'''

Mỗi dòng là một POI đã biết tương thích theo rule. Đây không phải qrels được người adjudicate, không có relevance grade và cũng không phải hard negative. Đích giả định lưu trong queries.intended_poi_id; không lặp thêm cờ is_intended ở qrels. Đích này thuộc tập compatible theo snapshot, nhưng compatible không bảo đảm đầy đủ.

## Eligibility

`eligibility.parquet`: 20.000 dòng; join query_id, một nguồn quyết định train/core eval.

| Trường | Kiểu Arrow | Ý nghĩa |
|---|---|---|
'''+fieldtable('eligibility.parquet')+'''

## Các bảng còn lại

| File | Khóa | Nội dung |
|---|---|---|
| pois.parquet | canonical_id | 46.792 object, tên/alias/address JSON, tọa độ, origin flags, entity/branch/complex. Index 45.693 dòng destination_searchable=true |
| poi_splits.parquet | canonical_id | leakage_group_id và split; không thay entity_group_id |
| typing_sessions.parquet | (session_id,event_index) | 800 phiên / 16.190 trạng thái, ngoài 20k; giữ schema lịch sử và version nguồn |
| audit/query_generation.parquet | query_id | Evidence, namespace, phép biến đổi, nguồn/version/seed, collision flags… Chỉ mở khi cần audit |
| audit/query_review.parquet | query_id | Trạng thái AI/human review, scope, notes và review_reasons |
| audit/initial_query_lineage.parquet | query_id / source_query_id | Lượt refine ban đầu; không phải lịch sử đầy đủ mọi sửa |
| audit/ai_review_log.json, ai_review_edits.json | query_id | Bằng chứng review và nội dung sửa sau lượt refine |
| reference/frozen_v3_test.parquet | ID lịch sử | Test v3 nguyên bản để so với kết quả đã công bố; không trộn vào v6 train |

`HANOI_QUERIES_20K_SCHEMA.json` liệt kê kiểu Arrow thực tế của toàn bộ bảng. Kiểu null ở metadata kế thừa nghĩa chưa có giá trị, không tự chuyển thành false hay chuỗi rỗng. Hậu tố _json nghĩa chuỗi JSON cần json.loads, không phải Arrow struct.

## Trường đã bỏ khỏi bảng query chính

- Tên/địa chỉ/category/origin: nối query.intended_poi_id → pois.canonical_id. poi_name cũ là search_label. poi_address cũ là các trường housenumber/street/subdistrict nối bằng khoảng trắng, bỏ trường thiếu.
- known_compatible_poi_ids: nhóm qrels theo query_id; compatible_count là số dòng trong nhóm, không lưu hai lần.
- corpus_version/search_view_version và completeness: manifest.json.source_record_constants. dataset_version tại đó là version record nguồn v5; manifest.json.dataset_version mới là version bundle v6.
- requires_review: bool(review_reasons). label_status cũ có thể suy từ review_reasons rỗng hay không; nó không phải ground truth.
- session_id/keystroke_index của query v5 toàn null nên bỏ. Thông tin session thật của bộ mô phỏng nằm ở typing_sessions, không nối bằng session_id của bảng query.
- leakage_group_id: lấy từ poi_splits theo intended_poi_id. Flags/metadata còn lại chuyển audit, không xóa mất bằng chứng.

Mapping từng trường v5 nằm trong `audit/v5_field_mapping.json`. Không xóa qrels, eligibility hoặc audit rồi cho rằng bảng 8 trường đủ tự chứng minh chất lượng nhãn.

## Quan hệ và quy tắc sử dụng

Train: queries → eligibility bằng query_id, lọc split=train và supervised_training_eligible=true; nối pois theo intended_poi_id để dựng passage bằng đúng text builder đã chọn. Loader không tự đổi passage template của checkpoint E5 hiện tại.

Eval core: chọn split và track, lọc main_metric_candidate; đánh giá target hoặc qrels theo đúng metric protocol. Prefix/ambiguity/IME/structured phải báo riêng; không ép tất cả thành Hit@1 đơn đích. Routing Stage 1 không được dùng track/case_type/target/audit như feature lúc serving.

Review được giữ nguyên: 1.790 dòng đã đọc trực tiếp; phần còn lại không được nâng thành AI-reviewed khi đổi schema. Corpus vẫn chưa có pickup point được xác minh; ranking_lat/lon không phải routing_lat/lon. Dataset không có user/time/origin counterfactual của Stage 2.
'''
(P/'HANOI_QUERIES_20K_SCHEMA.md').write_text(schema)
(P/'HANOI_QUERIES_20K_SCHEMA.json').write_text(json.dumps(dict(dataset_version=m['dataset_version'],tables=tables),ensure_ascii=False,indent=2)+'\n')
readme=f'''# Hanoi POI 20k — compact v6

**Bảng query chính còn 8 trường**, gồm query_id, query, intended_poi_id, query_family_id, split, track, case_type, query_surface. Nội dung dữ liệu giữ nguyên v5; đây là thay đổi cách lưu trữ và cách đọc, không phải một lần sinh/train/review mới.

## Dùng các file nào?

| Nhu cầu | File |
|---|---|
| Đọc query, chia nhóm/split | queries_20k.parquet |
| Train đơn đích hoặc chọn core eval | queries_20k.parquet + eligibility.parquet |
| Nội dung/tọa độ/alias POI | pois.parquet |
| Tập compatible nhãn yếu | qrels.parquet |
| Kiểm tra split theo nhóm POI | poi_splits.parquet |
| Đánh giá tiến trình gõ | typing_sessions.parquet |
| Xem nguồn sinh và quyết định review | audit/ |
| So với test E5 v3 cũ | reference/frozen_v3_test.parquet |
| Từ điển trường | HANOI_QUERIES_20K_SCHEMA.md / .json |

Không còn các bản train/dev/test, eligibility và corpus trùng lặp trong nhiều file active. Loader lọc từ bảng chính. Không random-split lại dữ liệu.

## Số lượng

- 20.000 query: train 13.190, dev 2.925, test v5 885, architecture holdout 3.000.
- {m['train_eligible']:,} query train đơn đích đủ điều kiện theo policy v5.
- {m['destination_searchable']:,} destination-searchable POI trong catalog đầy đủ.
- {m['qrel_rows']:,} liên kết compatible nhãn yếu được tách khỏi bảng query.
- Bảng query chính {m['core_bytes']:,} byte; không cần nạp qrels/audit để đọc query.
- Trạng thái review giữ nguyên: 1.790 dòng được Codex đọc trực tiếp, 18.210 dòng chưa được đọc riêng. Không có human-gold mới.

## Ví dụ nạp

```python
from load_dataset import load_training, load_evaluation, load_pois, iter_qrels

root = '/path/hanoi_queries_20k_v6'
train = load_training(root)  # Chỉ nạp queries và eligibility.
dev = load_evaluation(root, 'dev_synthetic', 'retrieval_core')
catalog = load_pois(root)    # Chỉ destination_searchable=true.

queries = dev['query'].to_pylist()
target_ids = dev['intended_poi_id'].to_pylist()
for labels in iter_qrels(root, dev['query_id'].to_pylist()):
    pass  # Batch các weak-compatible pairs, không nạp toàn bộ vào RAM.
```

Loader trả bảng query 8 trường. Passage POI được nối từ catalog theo canonical_id và dựng bằng text builder của experiment; không lấy clean_query từ audit làm input model. iter_qrels hiện quét theo batch rồi lọc; chưa phải dịch vụ indexed lookup.

## Tái tạo và kiểm chứng

```bash
pip install -r requirements.txt
python build_compact.py --source /path/hanoi_queries_20k_v5 --output /path/rebuild_v6
```

Cần input v5 để chạy migration; gói v6 không nhét lại toàn bộ v5 và các snapshot cũ. Manifest giữ hash nguồn. Quy trình đã kiểm tra bằng nhau với v5: 8 trường query, mọi cặp qrels, eligibility, review, generation audit và các trường POI được tách; frozen test giữ nguyên byte. Các loader đã chạy kiểm tra số dòng và liên kết target.

Mọi thông tin trong audit và reference chỉ phục vụ kiểm chứng; không đưa trực tiếp vào feature serving. Nhãn compatible vẫn yếu, IME chưa replay engine thật, test v5 không thay thế frozen v3 test, và Stage 2 chưa có dữ liệu cá nhân hóa mới.
'''
(P/'README.md').write_text(readme);shutil.copyfile(P/'README.md',P.parent/'HANOI_QUERIES_20K_README.md')
# Include hashes after all current documentation has been written.
members=sorted(p for p in P.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='manifest.json')
m['files']=[dict(path=str(p.relative_to(P)),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in members]
(P/'manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
zp=P.parent/'HANOI_QUERIES_20K.zip'
with zipfile.ZipFile(zp,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for p in members+[P/'manifest.json']:z.write(p,arcname='hanoi_queries_20k_v6/'+str(p.relative_to(P)))
with zipfile.ZipFile(zp) as z:assert z.testzip() is None
print(json.dumps(dict(zip=str(zp),bytes=zp.stat().st_size,files=len(members)+1,query_columns=8)))
