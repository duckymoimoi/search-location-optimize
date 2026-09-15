"""Count Vietnam-wide OSM searchable candidates from the project PBF.

Approximates the documented Hanoi corpus tag policy (design §2.1–2.3).
No Hanoi polygon filter and no canonical dedup.
"""

from __future__ import annotations

import json
import re
import time
from collections import Counter
from pathlib import Path

import osmium

PBF = Path(r"d:\vsf\vietnam-260910.osm.pbf")
OUT_DIR = Path(r"d:\vsf\training\corpus_audit")
OUT_DIR.mkdir(parents=True, exist_ok=True)

FUNCTIONAL_KEYS = (
    "amenity",
    "shop",
    "tourism",
    "office",
    "healthcare",
    "craft",
    "leisure",
    "public_transport",
)
IDENTITY_KEYS = ("name", "name:vi", "name:en", "brand", "operator", "ref")
ADDR_HOUSE = ("addr:housenumber", "addr:housename")
ADDR_STREET = ("addr:street", "addr:place")
KEY_TRACK = FUNCTIONAL_KEYS + ("building", "addr:housenumber", "addr:street", "addr:housename", "addr:place")


def has_any(tags, keys) -> bool:
    return any(k in tags and tags.get(k) for k in keys)


def clean(s: str | None) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", s).strip()


def looks_hanoi_admin(tags) -> bool:
    blob = " ".join(
        clean(tags.get(k))
        for k in (
            "addr:city",
            "addr:province",
            "addr:state",
            "is_in",
            "is_in:city",
            "is_in:province",
        )
        if tags.get(k)
    ).lower()
    return ("hà nội" in blob) or ("ha noi" in blob) or ("hanoi" in blob)


def empty_bucket() -> Counter:
    return Counter(
        {
            "intake_objects": 0,
            "functional": 0,
            "functional_with_identity": 0,
            "addressable_house_street": 0,
            "building_named": 0,
            "searchable_union": 0,
            "destination_like_label": 0,
        }
    )


class CounterHandler(osmium.SimpleHandler):
    def __init__(self) -> None:
        super().__init__()
        self.n_nodes = 0
        self.n_ways = 0
        self.n_rels = 0
        self.tagged_nodes = 0
        self.by_key = Counter()
        self.vn = empty_bucket()
        self.hn_proxy = empty_bucket()

    def _add(self, bucket: Counter, functional, identity, addressable, building_named, searchable, dest_like) -> None:
        bucket["intake_objects"] += 1
        if functional:
            bucket["functional"] += 1
        if functional and identity:
            bucket["functional_with_identity"] += 1
        if addressable:
            bucket["addressable_house_street"] += 1
        if building_named:
            bucket["building_named"] += 1
        if searchable:
            bucket["searchable_union"] += 1
        if dest_like:
            bucket["destination_like_label"] += 1

    def _handle(self, obj) -> None:
        tags = obj.tags
        if not tags:
            return
        for k in KEY_TRACK:
            if k in tags:
                self.by_key[k] += 1

        functional = has_any(tags, FUNCTIONAL_KEYS)
        identity = has_any(tags, IDENTITY_KEYS)
        addressable = has_any(tags, ADDR_HOUSE) and has_any(tags, ADDR_STREET)
        building_named = ("building" in tags) and identity
        intake = functional or addressable or building_named
        if not intake:
            return

        searchable = (functional and identity) or addressable or building_named
        dest_like = searchable and (identity or addressable)
        self._add(self.vn, functional, identity, addressable, building_named, searchable, dest_like)
        if looks_hanoi_admin(tags):
            self._add(self.hn_proxy, functional, identity, addressable, building_named, searchable, dest_like)

    def node(self, n) -> None:
        self.n_nodes += 1
        if n.tags:
            self.tagged_nodes += 1
            self._handle(n)

    def way(self, w) -> None:
        self.n_ways += 1
        if w.tags:
            self._handle(w)

    def relation(self, r) -> None:
        self.n_rels += 1
        if r.tags:
            self._handle(r)


def main() -> None:
    if not PBF.exists():
        raise SystemExit(f"missing PBF: {PBF}")

    h = CounterHandler()
    t0 = time.time()
    print(f"Scanning {PBF} ({PBF.stat().st_size} bytes)...", flush=True)
    h.apply_file(str(PBF), locations=False)
    elapsed = time.time() - t0
    vn = dict(h.vn)
    hn_proxy = dict(h.hn_proxy)

    searchable = vn["searchable_union"]
    report = {
        "source": {
            "filename": PBF.name,
            "size_bytes": PBF.stat().st_size,
            "scan_seconds": round(elapsed, 2),
            "policy_note": (
                "functional∈{amenity,shop,tourism,office,healthcare,craft,leisure,public_transport}; "
                "identity∈{name,name:vi,name:en,brand,operator,ref}; "
                "addressable=(addr:housenumber|housename)∧(addr:street|place); "
                "building_named=building∧identity; "
                "searchable_union=(functional∧identity)∨addressable∨building_named; "
                "destination_like=searchable_union∧(identity∨addressable). "
                "No polygon clip; no canonical dedup."
            ),
        },
        "vietnam_all_objects": {
            "nodes": h.n_nodes,
            "ways": h.n_ways,
            "relations": h.n_rels,
            "total": h.n_nodes + h.n_ways + h.n_rels,
            "tagged_nodes": h.tagged_nodes,
        },
        "vietnam_tag_key_counts": dict(h.by_key.most_common()),
        "vietnam_searchable_policy_raw": vn,
        "hanoi_admin_tag_proxy_searchable_policy_raw": hn_proxy,
        "hanoi_pilot_frozen_for_comparison": {
            "functional_raw": 32900,
            "functional_with_identity": 24277,
            "addressable_raw": 26394,
            "building_named": 6512,
            "searchable_raw_union": 55029,
            "canonical_pilot": 46792,
            "destination_searchable": 45693,
        },
        "totals": {
            "vietnam_searchable_union_raw": searchable,
            "vietnam_destination_like_raw": vn["destination_like_label"],
            "vietnam_functional": vn["functional"],
            "vietnam_functional_with_identity": vn["functional_with_identity"],
            "vietnam_addressable": vn["addressable_house_street"],
            "vietnam_building_named": vn["building_named"],
            "approx_canonical_if_same_dedup_ratio": int(round(searchable * (46792 / 55029))),
            "approx_destination_if_same_dest_ratio": int(round(searchable * (45693 / 55029))),
            "hanoi_pilot_destination_searchable": 45693,
            "ratio_vietnam_searchable_to_hanoi_searchable_raw": round(searchable / 55029, 2),
        },
    }

    out_json = OUT_DIR / "vietnam_nationwide_poi_count_report.json"
    out_md = OUT_DIR / "vietnam_nationwide_poi_count_report.md"
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    t = report["totals"]
    md = f"""# Báo cáo đếm POI/địa chỉ — PBF toàn quốc

Nguồn: `{PBF.name}` ({PBF.stat().st_size:,} bytes).

Thời gian scan thực tế: **{report['source']['scan_seconds']} s**.
Policy: xấp xỉ intake Stage 1 trong thiết kế. **Chưa** cắt polygon Hà Nội, **chưa** dedup canonical.

## 1. Toàn bộ object trong PBF Việt Nam

| Loại | Số |
|---|---:|
| Nodes | {report['vietnam_all_objects']['nodes']:,} |
| Ways | {report['vietnam_all_objects']['ways']:,} |
| Relations | {report['vietnam_all_objects']['relations']:,} |
| **Tổng** | **{report['vietnam_all_objects']['total']:,}** |
| Nodes có ≥1 tag | {report['vietnam_all_objects']['tagged_nodes']:,} |

## 2. Sau lọc kiểu search (raw, chưa dedup)

| Lớp | Việt Nam (scan này) | Hà Nội pilot (đã khóa) |
|---|---:|---:|
| Functional | {vn['functional']:,} | 32,900 |
| Functional + định danh | {vn['functional_with_identity']:,} | 24,277 |
| Addressable (số + phố) | {vn['addressable_house_street']:,} | 26,394 |
| Building có tên | {vn['building_named']:,} | 6,512 |
| **Searchable union** | **{searchable:,}** | **55,029** |
| Destination-like trong union | {vn['destination_like_label']:,} | sau audit: **45,693** |

Tỷ lệ searchable VN / searchable HN raw ≈ **{t['ratio_vietnam_searchable_to_hanoi_searchable_raw']}×**.

## 3. Ước lượng nếu dedup theo tỷ lệ pilot HN

Pilot: 55,029 → canonical 46,792 → destination 45,693.

| Ước lượng VN | Số |
|---|---:|
| Canonical xấp xỉ | {t['approx_canonical_if_same_dedup_ratio']:,} |
| Destination searchable xấp xỉ | {t['approx_destination_if_same_dest_ratio']:,} |

## 4. Proxy Hà Nội bằng tag địa chỉ (không polygon)

Searchable union proxy: {hn_proxy['searchable_union']:,} — thấp hơn pilot vì nhiều POI không ghi chữ “Hà Nội” trong tag.

## 5. Kết luận

- Cả nước trong PBF ≈ **{report['vietnam_all_objects']['total']:,}** object bản đồ.
- Cùng kiểu lọc search → searchable raw ≈ **{searchable:,}** (trước dedup).
- Hà Nội ~55k/46k/45k là kết quả **cắt biên + lọc + dedup/audit**, đúng với thiết kế.
"""
    out_md.write_text(md, encoding="utf-8")
    print(json.dumps(t, ensure_ascii=False, indent=2), flush=True)
    print("Wrote", out_json, flush=True)
    print("Wrote", out_md, flush=True)


if __name__ == "__main__":
    main()
