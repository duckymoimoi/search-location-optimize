"""Source-only conservative suggestions for earlier q01 entity-ready boundaries.

This reads corpus v3 search documents and Gold draft labels. It never writes
authored evidence and does not consult model ranks. A suggestion still needs
manual adjudication before changing a Gold label.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "data/vietnam/stage1_eval_suite_v2/staging/gold_stage1_v2_1"
CORPUS = ROOT / "data/vietnam/poi_corpus_v3/search_documents.parquet"


def fold(text: object) -> str:
    value = unicodedata.normalize("NFKC", str(text or "")).casefold().replace("đ", "d")
    return "".join(ch for ch in unicodedata.normalize("NFD", value)
                   if not unicodedata.combining(ch))


def tokens(text: object) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", fold(text)))


def main() -> None:
    packet = {row["case_id"]: row for row in
              (json.loads(line) for line in (STAGING / "authoring_packet.jsonl").read_text(encoding="utf-8").splitlines())}
    authored = [json.loads(line) for path in sorted((STAGING / "authored").glob("batch_*.jsonl"))
                for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    postings: dict[str, set[str]] = defaultdict(set)
    for row in pq.read_table(CORPUS, columns=["poi_id", "name", "aliases", "address_text"]).to_pylist():
        searchable = " ".join([row["name"] or "", row["address_text"] or ""] + (row["aliases"] or []))
        for token in tokens(searchable):
            postings[token].add(row["poi_id"])
    report = []
    for row in authored:
        q = row["queries"]["q01"]
        text = q["text"]
        intended = packet[row["case_id"]]["poi_id"]
        accepted = {intended} if q["positives"] == "target" else set(q["positives"])
        group_parts = tokens(q["group_ready_prefix"])
        group_matches = (set.intersection(*(postings[part] for part in group_parts))
                         if group_parts and all(part in postings for part in group_parts) else set())
        leading_name = re.split(r"\s+(?=\S*\d)", text, maxsplit=1)[0]
        name_parts = tokens(leading_name)
        name_matches = (set.intersection(*(postings[part] for part in name_parts))
                        if name_parts and all(part in postings for part in name_parts) else set())
        candidates = []
        for match in re.finditer(r"\S+", text):
            prefix = text[:match.end()]
            parts = tokens(prefix)
            if not parts or any(part not in postings for part in parts):
                continue
            matches = set.intersection(*(postings[part] for part in parts))
            if intended in matches and matches <= accepted:
                candidates.append({"prefix": prefix, "char_len": len(prefix), "matched_poi_ids": sorted(matches)})
                break
        report.append({"case_id": row["case_id"], "query_id": row["case_id"] + "-q01",
                       "q01": text, "current_entity_ready_prefix": q["entity_ready_prefix"],
                       "group_prefix": q["group_ready_prefix"],
                       "group_prefix_match_count": len(group_matches),
                       "group_prefix_exact_positive": intended in group_matches and group_matches <= accepted,
                       "leading_name_candidate": leading_name,
                       "leading_name_match_count": len(name_matches),
                       "leading_name_exact_positive": intended in name_matches and name_matches <= accepted,
                       "suggestion": candidates[0] if candidates else None,
                       "note": "Token-set uniqueness is only a source-only candidate, not proof of user intent."})
    out = STAGING / "draft" / "prefix_source_candidates.jsonl"
    out.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in report) + "\n", encoding="utf-8")
    earlier = [row for row in report if row["suggestion"] and
               len(row["suggestion"]["prefix"]) < len(row["q01"])]
    print(json.dumps({"cases": len(report), "earlier_unique_token_candidates": len(earlier),
                      "output": str(out.relative_to(ROOT))}, ensure_ascii=False))


if __name__ == "__main__":
    main()
