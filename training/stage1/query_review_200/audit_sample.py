"""Heuristic + rule-based quality audit on the 200-query sample."""
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

sample = Path(r"d:\vsf\training\stage1\query_review_200\sample_200.jsonl")
rows = [json.loads(l) for l in sample.read_text(encoding="utf-8").splitlines() if l.strip()]


def fold(s: str) -> str:
    s = (s or "").lower().replace("đ", "d").replace("Đ", "d")
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", s).strip()


def tokens(s: str):
    return re.findall(r"[a-z0-9/]+", fold(s))


ISSUE_DEFS = {
    "ok_clear": "Query khớp rõ với POI, dùng được cho train/metric",
    "ok_intentional_noise": "Lỗi gõ/prefix/IME có chủ đích, vẫn giữ được neo định danh",
    "ok_ambiguous_flagged": "Mơ hồ nhưng đã loại khỏi main metric / train đúng policy",
    "weak_naturalness": "Diễn đạt gượng / template / ít giống người thật gõ",
    "identity_risk": "Query có thể khớp POI khác hoặc mất định danh quan trọng",
    "label_doubt": "Nhãn intended/compat đáng nghi so với text query",
    "ime_not_realistic": "IME keystream quá thô / khó coi là input app thật",
    "structured_thin": "Mã/structured quá ngắn hoặc thiếu namespace",
}


def review_one(r):
    issues = []
    notes = []
    q = r["query"] or ""
    cq = r["clean_query"] or ""
    name = r["poi_name"] or ""
    addr = r["poi_address"] or ""
    track = r["track"]
    case = r["case_type"]
    compat = r["compatible_count"] or 0
    train = r["supervised_training_eligible"]
    main = r["main_metric_candidate"]

    qf, nf, af = fold(q), fold(name), fold(addr)
    qt, nt, at = tokens(q), tokens(name), tokens(addr)

    # Naturalness heuristics for grounded phrases
    if case in {"grounded_search_phrase", "search_phrase", "editorial_paraphrase"}:
        templates = [
            r"^cho tôi tới ",
            r"^tìm địa chỉ ",
            r"^tìm ",
            r"^địa chỉ ",
            r"^đến ",
            r"^tôi muốn đến ",
            r"^đi tới ",
        ]
        if any(re.search(p, q.lower()) for p in templates):
            # still ok if short and grounded; mark weak if very formulaic + exact copy
            if fold(q.replace("cho tôi tới ", "").replace("tìm địa chỉ ", "").replace("tìm ", "").replace("địa chỉ ", "").replace("đến ", "").replace("tôi muốn đến ", "").replace("đi tới ", "")) in {nf, af}:
                issues.append("weak_naturalness")
                notes.append("phrase = wrapper + exact name/address")

    # Prefix realism
    if case.startswith("prefix_"):
        n = int(case.split("_")[1])
        if len(q) != n and len(q) < n:
            issues.append("identity_risk")
            notes.append(f"prefix length mismatch case={n} len={len(q)}")
        if compat > 50 and main:
            issues.append("label_doubt")
            notes.append("very ambiguous but still main_metric")
        elif compat > 50:
            issues.append("ok_ambiguous_flagged")
            notes.append(f"compat={compat} excluded/flagged appropriately?" if not main else "")

    # Typo ops: check source/result consistency with query
    if r.get("typo_source") and r.get("typo_result"):
        if fold(r["typo_result"]) not in {qf, fold(cq)} and qf not in {fold(r["typo_result"]), fold(r["typo_source"])}:
            # query may be further mutated; soft check
            if case in {"adjacent_transpose", "character_deletion", "keyboard_neighbor", "space_edit", "repeated_character"}:
                if fold(r["typo_result"]) != qf and fold(r["typo_source"]) != fold(name) and fold(r["typo_source"]) not in {nf, af}:
                    issues.append("label_doubt")
                    notes.append("typo_source/result not clearly linked to query/POI")

    # No-diacritics should be folded form of name/address-ish
    if case == "no_diacritics":
        if q != fold(q):
            issues.append("label_doubt")
            notes.append("no_diacritics still has diacritics")
        # should resemble folded name or address
        if nf and qf not in nf and nf not in qf and af and qf not in af and not set(qt) & set(nt + at):
            issues.append("identity_risk")
            notes.append("no_diacritics query shares little with POI")

    # Address exact: house number presence
    if case in {"address_exact", "slash_alley_address", "address_namespace", "unit_with_namespace"}:
        if not re.search(r"\d", q):
            issues.append("identity_risk")
            notes.append("address-like case missing digits")
        # if intended address digits not in query
        addr_nums = re.findall(r"\d+[a-zA-Z]?(?:/\d+[a-zA-Z]?)?", addr)
        q_nums = re.findall(r"\d+[a-zA-Z]?(?:/\d+[a-zA-Z]?)?", q)
        if addr_nums and q_nums:
            if not set(a.lower() for a in addr_nums) & set(b.lower() for b in q_nums):
                if case == "address_exact":
                    issues.append("label_doubt")
                    notes.append(f"address numbers diverge addr={addr_nums} q={q_nums}")

    # IME
    if track == "ime_keystream" or case in {"ime_raw_keys", "telex_raw_keys", "vni_raw_keys"}:
        if re.search(r"[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]", q.lower()):
            issues.append("ime_not_realistic")
            notes.append("raw IME still contains Vietnamese diacritics")
        # very short keystream with high compat
        if len(q) <= 2:
            issues.append("ime_not_realistic")
            notes.append("extremely short IME stream")
        if not main:
            issues.append("ok_ambiguous_flagged")
        else:
            issues.append("label_doubt")
            notes.append("IME in main metric")

    # Structured code
    if track == "structured_code" or r.get("is_structured_code"):
        if len(q.strip()) <= 2 and not r.get("namespace_in_query"):
            issues.append("structured_thin")
            notes.append("short code without namespace")
        if main and not r.get("namespace_in_query"):
            issues.append("structured_thin")
            notes.append("structured without namespace still main?")

    # Alias
    if case == "source_alias_or_abbreviation":
        if not (set(qt) & set(nt + at)) and fold(q) not in fold(name + " " + addr):
            # aliases may not overlap tokens; soft
            notes.append("alias has weak surface overlap with name/address")
            issues.append("identity_risk")

    # Mixed errors with huge mean rank risk: if query barely overlaps
    if case == "mixed_two_errors":
        overlap = set(qt) & set(nt + at)
        if not overlap and len(qt) >= 2:
            issues.append("identity_risk")
            notes.append("mixed errors lost all token overlap")

    # Ambiguity track expectations
    if track == "ambiguity_stress":
        if compat <= 1 and len(q) > 3:
            notes.append("ambiguity track but compat<=1")
        if main:
            issues.append("label_doubt")
            notes.append("ambiguity_stress marked main_metric")
        else:
            issues.append("ok_ambiguous_flagged")

    # Clean / exact good cases
    if case in {"clean_name", "address_exact", "name_address", "name_street"} and not issues:
        if qf == nf or qf == af or nf in qf or af in qf or set(qt) <= set(nt + at) or set(nt) <= set(qt):
            issues.append("ok_clear")

    # Default intentional noise if mutation case and not flagged badly
    if case in {
        "no_diacritics",
        "partial_diacritics",
        "wrong_tone",
        "adjacent_transpose",
        "character_deletion",
        "keyboard_neighbor",
        "space_edit",
        "repeated_character",
    } and not any(x.startswith("ok_") or x in {"identity_risk", "label_doubt"} for x in issues):
        issues.append("ok_intentional_noise")

    if not issues:
        # fallback judgment
        if track in {"autocomplete", "ambiguity_stress", "ime_keystream", "structured_code"} and not main:
            issues.append("ok_ambiguous_flagged")
        elif main or train:
            issues.append("ok_clear")
        else:
            issues.append("ok_intentional_noise")

    # severity
    bad = {"identity_risk", "label_doubt", "ime_not_realistic", "structured_thin", "weak_naturalness"}
    severity = "bad" if any(i in bad for i in issues) else ("ok" if any(i.startswith("ok_") for i in issues) else "mixed")
    # if both ok and bad, mixed/bad
    if any(i in bad for i in issues) and any(i.startswith("ok_") for i in issues):
        severity = "mixed"

    return {
        "query_id": r["query_id"],
        "query": q,
        "poi_name": name,
        "poi_address": addr,
        "case_type": case,
        "track": track,
        "split": r["split"],
        "compatible_count": compat,
        "main_metric_candidate": main,
        "supervised_training_eligible": train,
        "issues": sorted(set(issues)),
        "notes": [n for n in notes if n],
        "severity": severity,
    }


audits = [review_one(r) for r in rows]
sev = Counter(a["severity"] for a in audits)
issue_c = Counter(i for a in audits for i in a["issues"])

out = Path(r"d:\vsf\training\stage1\query_review_200\audit_200.json")
out.write_text(json.dumps({"summary": {"severity": dict(sev), "issues": dict(issue_c)}, "items": audits}, ensure_ascii=False, indent=2), encoding="utf-8")

# Print compact tables for manual reading of concerning + random ok
print("SEVERITY", dict(sev))
print("ISSUES", dict(issue_c))
print("\n=== BAD / MIXED (for manual read) ===")
for a in audits:
    if a["severity"] in {"bad", "mixed"}:
        print(f"[{a['severity']}] {a['track']}/{a['case_type']} | {a['query']!r}")
        print(f"    POI: {a['poi_name']} | {a['poi_address']}")
        print(f"    issues={a['issues']} notes={a['notes']} compat={a['compatible_count']} main={a['main_metric_candidate']} train={a['supervised_training_eligible']}")

print("\n=== SAMPLE OK CLEAR (first 25) ===")
n = 0
for a in audits:
    if a["severity"] == "ok" and "ok_clear" in a["issues"]:
        print(f"{a['query']!r}  <-  {a['poi_name']} | {a['poi_address']}  ({a['case_type']})")
        n += 1
        if n >= 25:
            break

print("\n=== SAMPLE INTENTIONAL NOISE (first 20) ===")
n = 0
for a in audits:
    if "ok_intentional_noise" in a["issues"] and a["severity"] == "ok":
        print(f"{a['query']!r}  <-  {a['poi_name']} ({a['case_type']})")
        n += 1
        if n >= 20:
            break
