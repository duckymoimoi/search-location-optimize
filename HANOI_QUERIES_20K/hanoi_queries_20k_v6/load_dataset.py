"""Read v6 without loading qrels/audit unless explicitly requested."""
from pathlib import Path
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

def load_queries(root, split=None, track=None):
    filters=[]
    if split is not None:filters.append(('split','=',split))
    if track is not None:filters.append(('track','=',track))
    return pq.read_table(Path(root)/'queries_20k.parquet',filters=filters or None)

def load_training(root):
    root=Path(root)
    eligible=pq.read_table(root/'eligibility.parquet',columns=['query_id'],
                           filters=[('supervised_training_eligible','=',True)])
    q=load_queries(root,split='train')
    return q.filter(pc.is_in(q['query_id'],value_set=eligible['query_id'].combine_chunks()))

def load_evaluation(root,split='dev_synthetic',track='retrieval_core'):
    if split not in ('dev_synthetic','test_synthetic','architecture_holdout'):raise ValueError('Explicit evaluation split required')
    root=Path(root);q=load_queries(root,split,track)
    if track=='retrieval_core':
        eligible=pq.read_table(root/'eligibility.parquet',columns=['query_id'],filters=[('main_metric_candidate','=',True)])
        q=q.filter(pc.is_in(q['query_id'],value_set=eligible['query_id'].combine_chunks()))
    return q

def iter_qrels(root,query_ids,batch_size=100000):
    """Streaming compatible labels for explicitly chosen queries."""
    ids=pa.array(list(query_ids),type=pa.string())
    for b in pq.ParquetFile(Path(root)/'qrels.parquet').iter_batches(batch_size=batch_size):
        t=pa.Table.from_batches([b]);t=t.filter(pc.is_in(t['query_id'],value_set=ids))
        if t.num_rows:yield t

def load_pois(root):
    return pq.read_table(Path(root)/'pois.parquet',filters=[('destination_searchable','=',True)])
