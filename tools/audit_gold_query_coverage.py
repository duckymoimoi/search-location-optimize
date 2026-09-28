"""Report evidenced Gold-owned coverage without inventing or relabelling queries.

This is a release gate diagnostic, not a query generator. Counts are conservative:
only explicit tags/trace qualify; ambiguous requirements stay under review.
"""

from __future__ import annotations

import json
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "data/vietnam/stage1_eval_suite_v2/staging/gold_poi_draft"

# Gold-owned minima from GOLD_STAGE1_V2_CONSTRUCTION_PLAYBOOK.md.
REQUIREMENTS = {
    1: ("khong_dau", 40, ("khong_dau",)),
    2: ("sai_dau", 12, ("sai_dau",)),
    3: ("raw_telex", 12, ("raw_telex", "ime_telex_residual")),
    4: ("raw_vni", 8, ("raw_vni",)),
    5: ("phim_ke", 20, ("phim_ke",)),
    6: ("dau_nua_voi", 25, ("dau_nua_voi",)),
    7: ("chinh_ta_tuong_duong", 8, ("chinh_ta_tuong_duong", "phonetic_confusion")),
    8: ("double_tap", 10, ("double_tap",)),
    9: ("dinh_roi_space", 24, ("dinh_roi_space",)),
    10: ("dao_token", 12, ("dao_token", "token_order_variant")),
    11: ("omission", 16, ("omission",)),
    12: ("bo_type_context_dau_q01", 80, ("bo_type_context_dau",)),
    13: ("acronym", 16, ("acronym", "acronym_expand_contract")),
    16: ("doan_giua_cuoi", 20, ("doan_giua_cuoi",)),
    17: ("so_nha_doan_ten_duong", 20, ("so_nha_doan_ten_duong",)),
    19: ("ngo_ngach_hem_kiet", 10, ("ngo_ngach_hem_kiet",)),
    20: ("slash_number", 10, ("slash_number",)),
    21: ("dan_dia_chi_day_du", 12, ("dan_dia_chi_day_du",)),
    22: ("ma_toa_lo", 12, ("ma_toa_lo",)),
}

KEY_NEIGHBORS = {
    "q": "wa", "w": "qesa", "e": "wsdr", "r": "edft", "t": "rfgy",
    "y": "tghu", "u": "yhji", "i": "ujko", "o": "iklp", "p": "ol",
    "a": "qwsz", "s": "awedxz", "d": "serfcx", "f": "drtgcv", "g": "ftyhbv",
    "h": "gyujbn", "j": "huikmn", "k": "jiolm", "l": "kop",
    "z": "asx", "x": "zsdc", "c": "xdfv", "v": "cfgb", "b": "vghn",
    "n": "bhjm", "m": "njk",
}


def plain(value: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFD", value.casefold().replace("đ", "d"))
                   if not unicodedata.combining(ch))


def keyboard_neighbor_trace(trace: str) -> bool:
    if "→" not in trace:
        return False
    before, after = trace.split("→", 1)
    before, after = plain(before.split(":")[-1].strip()), plain(after.strip())
    if len(before) != len(after):
        return False
    changed = [(a, b) for a, b in zip(before, after) if a != b]
    return len(changed) == 1 and changed[0][1] in KEY_NEIGHBORS.get(changed[0][0], "")


def main() -> None:
    rows = [json.loads(line) for path in sorted((STAGING / "authored").glob("batch_*.jsonl"))
            for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    counts: Counter[str] = Counter()
    examples: dict[str, list[str]] = {}
    evidence_errors: list[str] = []
    for row in rows:
        for role, query in row["queries"].items():
            if "phim_ke" in query["tags"] and not any(
                keyboard_neighbor_trace(trace) for trace in query.get("mutation_evidence", [])
            ):
                evidence_errors.append(f"{row['case_id']}-{role}: phim_ke lacks adjacent-key trace")
            for tag in set(query["tags"]):
                counts[tag] += 1
                examples.setdefault(tag, []).append(f"{row['case_id']}-{role}")
    results = []
    for number, (name, minimum, tags) in REQUIREMENTS.items():
        actual = sum(bool(set(query["tags"]) & set(tags))
                     for row in rows for query in row["queries"].values())
        # q01 context omission is a distinct requirement, not any omission tag.
        if number == 12:
            actual = sum(bool(set(row["queries"]["q01"]["tags"]) & set(tags)) for row in rows)
        results.append({"id": number, "name": name, "minimum": minimum,
                        "explicit_tag_rows": actual, "status": "tag_gate_pass" if actual >= minimum else "needs_evidence",
                        "tag_examples": {tag: examples.get(tag, [])[:5] for tag in tags}})
    report = {
        "status": "draft_coverage_diagnostic",
        "cases": len(rows),
        "note": "Tag counts are only evidence candidates. Manual semantic review is required before any PASS claim.",
        "requirements": results,
        "derived_prefix_requirements": [14, 15],
        "address_scope_handoff": 18,
        "unmet_explicit_tag_gates": [r["id"] for r in results if r["status"] != "tag_gate_pass"],
        "tag_evidence_errors": evidence_errors,
    }
    out = STAGING / "draft" / "coverage_diagnostic.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"cases": len(rows), "unmet_explicit_tag_gates": report["unmet_explicit_tag_gates"],
                      "tag_evidence_errors": evidence_errors,
                      "output": str(out.relative_to(ROOT))}, ensure_ascii=False))


if __name__ == "__main__":
    main()
