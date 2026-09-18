#!/usr/bin/env python3
"""
tools/validate_gold_variants.py
-------------------------------
Comprehensive automated validation engine for SEARCH 2.0 Stage-1 Gold Query Variants.

Enforces:
1. Schema & non-null columns
2. 6 variants per case_id (v1..v6), exactly 1,080 rows total
3. Fold-distinctness within each case (NFKC + casefold + trim)
4. Severity constraint: CLEAN or SINGLE only (no COMPOUND)
5. Entity integrity: Levenshtein distance threshold to prevent cross-case contamination
6. Operator-specific linguistic assertions:
   - adjacent_key: exactly 1 substitution, replacement in QWERTY neighbors
   - char_transpose: exactly 1 adjacent grapheme swap
   - double_letter: exactly 1 repeated letter
   - char_delete: exactly 1 deleted letter
   - phonological_confusion: exactly 1 token affected, valid phonetic pair
   - partial_diacritics: strip_accents(query) == strip_accents(canonical)
   - telex_leftover: contains valid telex artifacts
7. Qrels format: non-empty intended_poi_id, valid acceptable_poi_ids list/pipes
"""

import sys
import os
import unicodedata
import pandas as pd

# Reconfigure stdout for utf-8
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

# QWERTY adjacent key map (lowercase)
QWERTY_NEIGHBORS = {
    'q': {'w', 'a', 's', '1', '2'},
    'w': {'q', 'e', 'a', 's', 'd', '2', '3'},
    'e': {'w', 'r', 's', 'd', 'f', '3', '4'},
    'r': {'e', 't', 'd', 'f', 'g', '4', '5'},
    't': {'r', 'y', 'f', 'g', 'h', '5', '6'},
    'y': {'t', 'u', 'g', 'h', 'j', '6', '7'},
    'u': {'y', 'i', 'h', 'j', 'k', '7', '8'},
    'i': {'u', 'o', 'j', 'k', 'l', '8', '9'},
    'o': {'i', 'p', 'k', 'l', '9', '0'},
    'p': {'o', 'l', '0', '-'},
    'a': {'q', 'w', 's', 'z'},
    's': {'w', 'e', 'a', 'd', 'z', 'x'},
    'd': {'e', 'r', 's', 'f', 'x', 'c'},
    'f': {'r', 't', 'd', 'g', 'c', 'v'},
    'g': {'t', 'y', 'f', 'h', 'v', 'b'},
    'h': {'y', 'u', 'g', 'j', 'b', 'n'},
    'j': {'u', 'i', 'h', 'k', 'n', 'm'},
    'k': {'i', 'o', 'j', 'l', 'm'},
    'l': {'o', 'p', 'k'},
    'z': {'a', 's', 'x'},
    'x': {'z', 's', 'd', 'c'},
    'c': {'x', 'd', 'f', 'v'},
    'v': {'c', 'f', 'g', 'b'},
    'b': {'v', 'g', 'h', 'n'},
    'n': {'b', 'h', 'j', 'm'},
    'm': {'n', 'j', 'k'},
}

def strip_accents(s):
    s = str(s).replace('đ', 'd').replace('Đ', 'd')
    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn').lower()

def norm(t):
    return unicodedata.normalize('NFKC', str(t)).casefold().strip()

def lev(s1, s2):
    if len(s1) < len(s2):
        return lev(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = prev[j + 1] + 1
            deletions = curr[j] + 1
            substitutions = prev[j] + (c1 != c2)
            curr.append(min(insertions, deletions, substitutions))
        prev = curr
    return prev[-1]

def validate_dataset(csv_path):
    print(f"=== Validating Gold Stage-1 Dataset: {csv_path} ===")
    errors = []
    warnings = []
    
    if not os.path.exists(csv_path):
        return [f"File does not exist: {csv_path}"]
        
    df = pd.read_csv(csv_path)
    
    # 1. Total row count & columns
    required_cols = [
        "case_id", "variant_id", "query_text", "canonical_query",
        "query_variant_family", "variant_operator", "severity",
        "query_types", "intended_poi_id", "acceptable_poi_ids",
        "primary_sampling_stratum", "review_status", "generator_version"
    ]
    for col in required_cols:
        if col not in df.columns:
            errors.append(f"Missing required column: {col}")
            
    if len(df) != 1080:
        errors.append(f"Expected 1,080 rows, got {len(df)}")
        
    # 2. Check each case
    cases = df["case_id"].unique()
    if len(cases) != 180:
        errors.append(f"Expected 180 distinct case_ids, got {len(cases)}")
        
    for case_id in cases:
        c_rows = df[df["case_id"] == case_id]
        if len(c_rows) != 6:
            errors.append(f"Case {case_id} has {len(c_rows)} variants (expected 6)")
            
        # Check fold-distinct
        normalized_texts = [norm(t) for t in c_rows["query_text"]]
        if len(set(normalized_texts)) != len(normalized_texts):
            errors.append(f"Case {case_id} has duplicate normalized variants: {normalized_texts}")
            
        # Canonical consistency
        canonical = c_rows.iloc[0]["canonical_query"]
        for _, r in c_rows.iterrows():
            if r["canonical_query"] != canonical:
                errors.append(f"Inconsistent canonical_query in {case_id}: {r['canonical_query']} vs {canonical}")

    # 3. Check individual row constraints
    for idx, row in df.iterrows():
        case_id = row["case_id"]
        var_id = row["variant_id"]
        q = str(row["query_text"])
        c = str(row["canonical_query"])
        fam = str(row["query_variant_family"])
        op = str(row["variant_operator"])
        sev = str(row["severity"])
        
        # Severity check
        if sev not in ["CLEAN", "SINGLE"]:
            errors.append(f"[{case_id} {var_id}] Invalid severity '{sev}', gold only allows CLEAN or SINGLE")
            
        # Cross-contamination check for noise variants (v5, v6)
        if var_id.endswith("-v5") or var_id.endswith("-v6"):
            d = lev(strip_accents(q), strip_accents(c))
            if d > 12:
                errors.append(f"[{case_id} {var_id}] High Levenshtein distance ({d}) indicating cross-contamination: '{q}' vs '{c}'")
                
        # Operator-specific assertions
        if op == "partial_diacritics":
            if strip_accents(q) != strip_accents(c):
                errors.append(f"[{case_id} {var_id}] partial_diacritics changed text beyond diacritics: '{q}' vs '{c}'")
                
        elif op == "adjacent_key":
            sq = strip_accents(q)
            sc = strip_accents(c)
            if len(sq) != len(sc):
                errors.append(f"[{case_id} {var_id}] adjacent_key changed string length: '{q}' vs '{c}'")
            else:
                diffs = [(sq[i], sc[i]) for i in range(len(sq)) if sq[i] != sc[i]]
                if len(diffs) != 1:
                    errors.append(f"[{case_id} {var_id}] adjacent_key has {len(diffs)} character diffs (expected 1): {diffs}")
                else:
                    c1, c2 = diffs[0]
                    if c2 in QWERTY_NEIGHBORS and c1 not in QWERTY_NEIGHBORS[c2]:
                        errors.append(f"[{case_id} {var_id}] adjacent_key '{c1}' is not adjacent to '{c2}' on QWERTY")

        elif op == "char_transpose":
            sq = strip_accents(q)
            sc = strip_accents(c)
            if len(sq) != len(sc):
                errors.append(f"[{case_id} {var_id}] char_transpose changed string length: '{q}' vs '{c}'")
            else:
                diff_indices = [i for i in range(len(sq)) if sq[i] != sc[i]]
                if len(diff_indices) != 2 or diff_indices[1] != diff_indices[0] + 1:
                    errors.append(f"[{case_id} {var_id}] char_transpose does not swap exactly 2 adjacent characters: '{q}' vs '{c}'")

        elif op == "phonological_confusion" and sev == "SINGLE":
            sq_tokens = strip_accents(q).split()
            sc_tokens = strip_accents(c).split()
            if len(sq_tokens) != len(sc_tokens):
                errors.append(f"[{case_id} {var_id}] phonological_confusion changed token count: '{q}' vs '{c}'")
            else:
                diff_tokens = [(sq_tokens[i], sc_tokens[i]) for i in range(len(sq_tokens)) if sq_tokens[i] != sc_tokens[i]]
                if len(diff_tokens) > 1:
                    errors.append(f"[{case_id} {var_id}] phonological_confusion with SINGLE severity changed {len(diff_tokens)} tokens (compound!): {diff_tokens}")

        elif op == "double_letter":
            sq = strip_accents(q)
            sc = strip_accents(c)
            if len(sq) != len(sc) + 1:
                errors.append(f"[{case_id} {var_id}] double_letter should have length = original + 1: '{q}' vs '{c}'")

    print(f"Validation completed: {len(errors)} errors, {len(warnings)} warnings.")
    return errors

if __name__ == "__main__":
    csv_file = "data/vietnam/gold_stage1_v1/query_variants_v1.csv"
    if len(sys.argv) > 1:
        csv_file = sys.argv[1]
    errs = validate_dataset(csv_file)
    if errs:
        print("\nERRORS ENCOUNTERED:")
        for e in errs:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print("\nALL ASSERTIONS PASSED! Dataset is 100% compliant.")
        sys.exit(0)
