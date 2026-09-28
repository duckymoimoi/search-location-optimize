"""Small contract smoke for compact Gold v2.1 authoring serialization."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


SCRIPT = Path(__file__).resolve().parents[1] / "serialize_gold_poi_draft.py"


def test_one_manual_case_serializes_query_specific_qrels_and_prefix(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("gold_v21_serializer", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    corpus = tmp_path / "corpus.parquet"
    pq.write_table(pa.table({"poi_id": ["osm:node/1", "osm:node/2"]}), corpus)
    monkeypatch.setattr(module, "CORPUS", corpus)
    card = {
        "case_id": "g-test-001", "poi_id": "osm:node/1",
        "case_origin": "heldout_supplement",
        "exposure_class": "poi_heldout_namespace_seen",
        "primary_sampling_stratum": "named_clear",
        "source": {"entity_group_id": "osm:node/1"},
    }
    packet = tmp_path / "authoring_packet.jsonl"
    packet.write_text(json.dumps(card) + "\n", encoding="utf-8")
    (tmp_path / "authoring_packet_manifest.json").write_text(
        json.dumps({"packet_sha256": hashlib.sha256(packet.read_bytes()).hexdigest()}),
        encoding="utf-8",
    )
    authored = tmp_path / "authored"
    authored.mkdir()
    queries = {}
    for role, text, difficulty in (
        ("q01", "Quán An Nguyễn Trãi", "clean"),
        ("q02", "Quà n An Nguyễn Trai", "mild"),
        ("q03", "Quanan nguen trai", "compound"),
        ("q04", "Quánn An nguyễ trai", "mild"),
    ):
        queries[role] = {
            "text": text, "difficulty": difficulty, "tags": [],
            "positives": ["osm:node/1", "osm:node/2"] if role == "q02" else "target",
            "qrel_evidence": ["test:source"], "review_status": "needs_review",
        }
    queries["q01"]["group_ready_prefix"] = "Quán An"
    queries["q01"]["entity_ready_prefix"] = "Quán An Nguyễn Trãi"
    queries["q02"]["mutation_evidence"] = ["early:Quán→Quà n", "Trãi→Trai"]
    queries["q03"]["mutation_evidence"] = ["early:Quán An→Quanan", "Nguyễn→nguen"]
    queries["q04"]["mutation_evidence"] = ["early:Quán→Quánn", "Nguyễn→nguyễ"]
    (authored / "batch_001.jsonl").write_text(
        json.dumps({"case_id": card["case_id"], "queries": queries}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--staging", str(tmp_path)])
    module.main()
    sessions = pq.read_table(tmp_path / "draft/query_sessions_v2_1_draft.parquet").to_pylist()
    qrels = pq.read_table(tmp_path / "draft/qrels_v2_1_draft.parquet").to_pylist()
    prefixes = [json.loads(x) for x in
                (tmp_path / "draft/prefix_evidence_v2_1_draft.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(sessions) == 4
    assert len(qrels) == 5
    assert len(prefixes) == 1
    assert prefixes[0]["group_ready_grapheme"] < prefixes[0]["entity_ready_grapheme"]
    assert sessions[1]["difficulty"] == "mild"
    assert sessions[3]["difficulty"] == "mild"  # not inferred from q04 slot
    assert module.mutation_points(["early:Quán An→QuánAn", "space_merge:Quán An→QuánAn"]) == {"Quán An→QuánAn"}
