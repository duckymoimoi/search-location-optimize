"""Test metric denominators and paired decisions without model/ES."""
import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location("ablation", Path(__file__).with_name("dense_first_ablation.py"))
ablation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ablation)


def record(group, query, accepted, ann, candidate, suite="poi_dev", status="ok"):
    return dict(group_id=group, query_id=query, accepted_poi_ids=accepted,
                stages={"ann_raw": ann, "candidate": candidate}, suite=suite,
                normalizer="raw", query_text=query, status=status, timings_ms={})


def test_family_macro_does_not_weight_large_family_more():
    rows = [record("a", "1", ["a"], ["a"], [], "brand_dev"),
            record("a", "2", ["a"], ["a"], [], "brand_dev"),
            record("b", "3", ["b"], [], [], "brand_dev")]
    assert ablation.metrics(rows, "ann_raw")["Hit@1"] == 0.5


def test_error_stays_in_denominator_and_multi_positive_coverage():
    rows = [record("a", "1", ["a", "b"], ["a"], ["b"]),
            record("b", "2", ["c"], [], [], status="error")]
    result = ablation.metrics(rows, "ann_raw")
    assert result["Hit@1"] == 0.5
    assert result["coverage@20"] == 0.25


def test_replay_reports_rescue_and_harm(tmp_path):
    rows = [record("a", "1", ["a"], ["a"], ["wrong"]),
            record("b", "2", ["b"], ["wrong"], ["b"])]
    (tmp_path / "queries.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    result = ablation.evaluate(tmp_path)["poi_dev:raw"]["paired_vs_ann_raw"]["candidate"]
    assert result["rescued_queries"] == result["harmed_queries"] == 1
    assert result["group_mean_delta_hit1"] == 0
