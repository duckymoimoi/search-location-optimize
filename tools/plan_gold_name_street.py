"""Source-only plan for a name + street, no-house Gold variant per named POI.

Writes a review packet. It never changes authored queries or qrels.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "data/vietnam/stage1_eval_suite_v2/staging/gold_poi_draft"
CORPUS = ROOT / "data/vietnam/poi_corpus_v3/search_documents.parquet"
STREET_TYPES = {"duong", "pho", "hem", "ngo", "ngach", "kiet", "ql", "quoc", "lo"}
EXCEPTIONS = {
    "g150-001": "CC2 is a unit/code, not an ordinary house number; bank and ATM share the street.",
    "g150-026": "SH16-130 is a shop-unit code retained as an identity discriminator.",
    "g150-035": "Source street is the malformed 'Hồ Tùng Mâuj'; verify the source before authoring a street query.",
    "g150-115": "Several Long Châu branches share Trần Hưng Đạo in Bắc Ninh, including a train target; no house-free singleton label is supported.",
    "g150-129": "Several VinFast charging stations share Xương Giang in Bắc Giang; no house-free singleton label is supported.",
}
NON_HOUSE_CODES = {"g150-001", "g150-026"}


def fold(value: object) -> str:
    value = unicodedata.normalize("NFKC", str(value or "")).casefold().replace("đ", "d")
    return "".join(ch for ch in unicodedata.normalize("NFD", value)
                   if not unicodedata.combining(ch))


def tokens(value: object) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", fold(value)))


def street_core(value: str) -> str:
    parts = re.findall(r"[a-z0-9]+", fold(value))
    while parts and parts[0] in STREET_TYPES:
        parts.pop(0)
    return " ".join(parts)


def remove_house(text: str, house: str) -> str | None:
    # Never remove a digit substring embedded in a tower/street code.
    pattern = re.compile(r"(?<![\w/-])" + re.escape(house) + r"(?![\w/-])", re.IGNORECASE)
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        return None
    start, end = matches[0].span()
    return " ".join((text[:start] + " " + text[end:]).split())


def main() -> None:
    cards = {row["case_id"]: row for row in
             (json.loads(line) for line in (STAGING / "authoring_packet.jsonl").read_text(encoding="utf-8").splitlines())}
    authored = {row["case_id"]: row for path in sorted((STAGING / "authored").glob("batch_*.jsonl"))
                for row in (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())}
    same_name: dict[str, list[dict]] = defaultdict(list)
    for row in pq.read_table(CORPUS, columns=["poi_id", "name", "address_text"]).to_pylist():
        same_name[fold(row["name"])].append(row)
    plan = []
    for case_id, card in cards.items():
        source = card["source"]
        house, street, name = source.get("housenumber"), source.get("street"), source["name"]
        if not house or not street or name[0].isdigit() or card["primary_sampling_stratum"] in {
            "address_street_building", "building_code"
        }:
            continue
        street_terms = tokens(street) - STREET_TYPES
        if not street_terms:
            continue
        qrows = authored[case_id]["queries"]
        existing = []
        candidates = []
        for role in ("q01", "q02", "q03", "q04"):
            text = qrows[role]["text"]
            if remove_house(text, str(house)) is None:
                if str(house).casefold() not in text.casefold():
                    # A query without the house is useful only if its street is visible.
                    if street_terms & tokens(text):
                        existing.append({"role": role, "text": text})
                continue
            stripped = remove_house(text, str(house))
            if stripped and street_terms & tokens(stripped):
                candidates.append({"role": role, "old_text": text, "proposed_text": stripped,
                                   "street_terms_found": sorted(street_terms & tokens(stripped))})
        core = street_core(street)
        nearby = [row for row in same_name[fold(name)]
                  if row["poi_id"] != card["poi_id"] and core
                  and core in " ".join(re.findall(r"[a-z0-9]+", fold(row["address_text"])))]
        covered_roles = [role for role, query in qrows.items()
                         if "name_street_no_house" in query["tags"]]
        plan.append({"case_id": case_id, "poi_id": card["poi_id"], "name": name,
                     "house": house, "street": street, "existing": existing,
                     "candidates": candidates, "same_name_street_collisions": [
                         {"poi_id": row["poi_id"], "name": row["name"], "address_text": row["address_text"]}
                         for row in nearby[:20]],
                     "collision_count": len(nearby), "covered_roles": covered_roles,
                     "exception_reason": EXCEPTIONS.get(case_id)})
    out = STAGING / "draft" / "name_street_no_house_plan.jsonl"
    out.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in plan) + "\n", encoding="utf-8")
    tag_validation_errors = []
    for row in plan:
        street_terms = tokens(row["street"]) - STREET_TYPES
        for role in row["covered_roles"]:
            text = authored[row["case_id"]]["queries"][role]["text"]
            if not (street_terms & tokens(text)):
                tag_validation_errors.append(f"{row['case_id']}-{role}: source street absent")
            if remove_house(text, str(row["house"])) is not None:
                tag_validation_errors.append(f"{row['case_id']}-{role}: source house remains")
    coverage = {
        "status": "source_only_name_street_no_house_audit",
        "named_pois_with_house_and_street": len(plan),
        "covered_cases": sum(bool(row["covered_roles"]) for row in plan),
        "exception_cases": [{"case_id": row["case_id"], "reason": row["exception_reason"]}
                            for row in plan if row["exception_reason"]],
        "needs_adjudication_cases": [row["case_id"] for row in plan
                                     if row["exception_reason"] and row["case_id"] not in NON_HOUSE_CODES
                                     and not row["covered_roles"]],
        "unresolved_cases": [row["case_id"] for row in plan
                             if not row["covered_roles"] and not row["exception_reason"]],
        "tag_validation_errors": tag_validation_errors,
    }
    coverage_path = STAGING / "draft" / "name_street_no_house_coverage.json"
    coverage_path.write_text(json.dumps(coverage, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"eligible_named_pois": len(plan),
                      "existing_name_street_no_house": sum(bool(row["existing"]) for row in plan),
                      "with_removal_candidate": sum(bool(row["candidates"]) for row in plan),
                      "same_name_street_collision_cases": sum(bool(row["collision_count"]) for row in plan),
                      "covered_cases": coverage["covered_cases"],
                      "exception_cases": len(coverage["exception_cases"]),
                      "needs_adjudication_cases": coverage["needs_adjudication_cases"],
                      "unresolved_cases": coverage["unresolved_cases"],
                      "tag_validation_errors": tag_validation_errors,
                      "output": str(out.relative_to(ROOT))}, ensure_ascii=False))


if __name__ == "__main__":
    main()
