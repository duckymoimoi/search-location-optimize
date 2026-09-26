# -*- coding: utf-8 -*-
"""
Prefix Sampler for SEARCH 2.0 Stage 1 Training Pipeline.
Implements the training protocol derived table specification:
- Samples 2-4 points per query from v01-v03 (and reduced rate from v04-v06):
  1. early word boundary
  2. mid word boundary
  3. mid-token cut
  4. full query
- Normalizes sample_weight per case_id
- Evaluates collision against corpus 186k to set label_state:
  * 'positive' (unique)
  * 'multi_positive' (finite cluster <= 20 POIs)
  * 'ignore' (broad prefix > 20 POIs or len <= 3)
- Schema:
  prefix_id, parent_variant_id, case_id, prefix_text, prefix_char_len,
  is_word_boundary, is_full_query, acceptable_poi_ids, label_state, sample_weight, split
"""

import os
import sys
import io
import json
import argparse
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def sample_prefix_points(text: str):
    """Generate 2-4 distinct prefix points for a given query text."""
    text = text.strip()
    words = text.split()
    n_words = len(words)
    points = []
    
    # 1. Early word boundary (1st or 2nd word)
    if n_words >= 2:
        early_text = " ".join(words[:1])
        points.append({
            'prefix_text': early_text,
            'is_word_boundary': True,
            'is_full_query': False
        })
    
    # 2. Mid word boundary
    if n_words >= 3:
        mid_idx = n_words // 2
        mid_text = " ".join(words[:mid_idx + 1])
        if mid_text != text and not any(p['prefix_text'] == mid_text for p in points):
            points.append({
                'prefix_text': mid_text,
                'is_word_boundary': True,
                'is_full_query': False
            })
            
    # 3. Mid-token cut (incomplete word)
    # Find a good cut point in the last word or middle word
    if len(text) >= 8:
        cut_len = max(4, int(len(text) * 0.6))
        # ensure not ending at space
        cut_text = text[:cut_len].rstrip()
        if not any(p['prefix_text'] == cut_text for p in points) and cut_text != text:
            points.append({
                'prefix_text': cut_text,
                'is_word_boundary': False,
                'is_full_query': False
            })
            
    # 4. Full query
    points.append({
        'prefix_text': text,
        'is_word_boundary': True,
        'is_full_query': True
    })
    
    return points


def build_prefix_derived_table(
    queries_path: str,
    corpus_path: str,
    output_path: str,
    max_cases: int = None,
    default_split: str = 'train'
):
    print(f"Reading queries from: {queries_path}")
    df_queries = pd.read_parquet(queries_path)
    if max_cases:
        cids = df_queries['case_id'].unique()[:max_cases]
        df_queries = df_queries[df_queries['case_id'].isin(cids)]
        print(f"Subsampled to {len(cids)} cases ({len(df_queries)} queries).")

    print(f"Reading corpus from: {corpus_path}")
    df_corpus = pd.read_parquet(corpus_path, columns=['poi_id', 'name', 'brand'])
    
    # Build prefix index from corpus (first 4-10 chars of name and brand)
    print("Indexing corpus prefix collisions...")
    corpus_names = df_corpus['name'].dropna().str.lower().tolist()
    corpus_brands = df_corpus['brand'].dropna().str.lower().tolist()
    all_corpus_strings = set(corpus_names + corpus_brands)

    derived_rows = []
    case_prefix_counts = {}

    print("Sampling prefixes across queries...")
    for idx, r in df_queries.iterrows():
        cid = r['case_id']
        vid = r['variant_id']
        qtext = str(r['query_text']).strip()
        poi_id = r['intended_poi_id']
        slot = vid.split('-')[-1] # v01..v06
        
        # Primary sampling from v01-v03; reduced from v04-v06 (full query only for compound)
        if slot in ('v01', 'v02', 'v03'):
            pts = sample_prefix_points(qtext)
        else:
            # Compound variants only sampled at full query
            pts = [{
                'prefix_text': qtext,
                'is_word_boundary': True,
                'is_full_query': True
            }]
            
        for p_idx, pt in enumerate(pts):
            ptext = pt['prefix_text']
            ptext_lower = ptext.lower()
            plen = len(ptext)
            
            # Determine label_state based on collision
            if pt['is_full_query']:
                label_state = 'positive'
                acc_ids = [poi_id]
            elif plen <= 3:
                # Too broad prefix (e.g. 'nh', 'tr', 'w')
                label_state = 'ignore'
                acc_ids = []
            else:
                # Count approximate matches in corpus strings
                matches = [s for s in all_corpus_strings if s.startswith(ptext_lower)]
                match_count = len(matches)
                if match_count <= 1:
                    label_state = 'positive'
                    acc_ids = [poi_id]
                elif match_count <= 20:
                    label_state = 'multi_positive'
                    # Find POIs
                    matched_pois = df_corpus[df_corpus['name'].fillna('').str.lower().str.startswith(ptext_lower)]['poi_id'].tolist()
                    acc_ids = list(set([poi_id] + matched_pois[:19]))
                else:
                    label_state = 'ignore'
                    acc_ids = []
                    
            p_id = f"{vid}-p{p_idx:02d}"
            case_prefix_counts[cid] = case_prefix_counts.get(cid, 0) + 1
            
            derived_rows.append({
                'prefix_id': p_id,
                'parent_variant_id': vid,
                'case_id': cid,
                'prefix_text': ptext,
                'prefix_char_len': plen,
                'is_word_boundary': pt['is_word_boundary'],
                'is_full_query': pt['is_full_query'],
                'acceptable_poi_ids': acc_ids,
                'label_state': label_state,
                'split': default_split
            })

    print(f"Total derived prefix rows: {len(derived_rows)}")
    df_derived = pd.DataFrame(derived_rows)
    
    # Normalize sample_weight per case_id so all cases have equal total weight
    df_derived['sample_weight'] = df_derived['case_id'].apply(lambda c: 1.0 / case_prefix_counts[c])
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    table = pa.Table.from_pandas(df_derived, preserve_index=False)
    pq.write_table(table, output_path)
    print(f"Saved prefix derived table to: {output_path}")
    print(f"Label state distribution:\n{df_derived['label_state'].value_counts()}")
    return df_derived


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Prefix Sampler for Stage 1 Training")
    parser.add_argument('--queries', default=r'data/vietnam/train_stage1_20k/queries_stage1_4900_pilot.parquet')
    parser.add_argument('--corpus', default=r'data/vietnam/poi_corpus_v1/pois_core.parquet')
    parser.add_argument('--output', default=r'data/vietnam/train_stage1_20k/prefix_training_pairs_pilot.parquet')
    parser.add_argument('--max_cases', type=int, default=None)
    args = parser.parse_args()

    build_prefix_derived_table(args.queries, args.corpus, args.output, max_cases=args.max_cases)
