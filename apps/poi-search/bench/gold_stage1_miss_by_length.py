#!/usr/bin/env python3
"""List mE5 miss cases with top hits; relate miss rate to query length."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
GOLD = ROOT / "data/vietnam/gold_stage1_v1"
RUNS = ROOT / "training/kaggle/output_gold_stage1_w1/gold_stage1_w1"
OUT = ROOT / "docs/deliveries/w1_evidence"
CORPUS = ROOT / "data/vietnam/poi_corpus_v1/pois_core.parquet"

DEPTH = 1000
MISS = DEPTH + 1


def load_run(path: Path):
    ranks: dict[str, int] = {}
    tops: dict[str, list[str]] = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            vid = str(row.get("variant_id") or "")
            br = row.get("best_rank")
            if br is None:
                br = MISS
            else:
                br = int(br)
                if br <= 0 or br > DEPTH:
                    br = MISS
            ranks[vid] = br
            tops[vid] = [str(x) for x in (row.get("top_ids") or [])[:10]]
    return ranks, tops


def hit_series(s: pd.Series, k: int) -> pd.Series:
    return (s >= 1) & (s <= k)


def fmt_top(ids: list[str], intended: str, name_map: dict) -> str:
    out = []
    for i, pid in enumerate(ids, 1):
        p = name_map.get(pid)
        mark = " <<TARGET" if pid == intended else ""
        if p is None:
            out.append(f"  {i}. {pid}{mark}")
            continue
        brand = ""
        if getattr(p, "brand", None) and str(p.brand) not in ("", "None", "nan"):
            brand = f" | {p.brand}"
        addr = (str(getattr(p, "address_text", "") or ""))[:70]
        out.append(f"  {i}. {p.name}{brand} — {addr} [{pid}]{mark}")
    return "\n".join(out)


def main() -> None:
    queries = pd.read_csv(GOLD / "query_variants_v1.csv")
    meta = {str(r.variant_id): r for r in queries.itertuples(index=False)}

    pois = pd.read_parquet(CORPUS, columns=["poi_id", "name", "brand", "address_text", "province"])
    name_map = {str(r.poi_id): r for r in pois.itertuples(index=False)}

    dense_r, dense_top = load_run(RUNS / "run_dense_me5_exact.jsonl")
    lex_r, lex_top = load_run(RUNS / "run_lexical_bm25.jsonl")

    rows = []
    for vid, m in meta.items():
        if vid not in dense_r or vid not in lex_r:
            continue
        q = str(m.query_text)
        rows.append(
            {
                "variant_id": vid,
                "case_id": str(m.case_id),
                "query_text": q,
                "char_len": len(q),
                "token_n": len(q.split()),
                "family": str(m.query_variant_family),
                "stratum": str(m.primary_sampling_stratum),
                "operator": str(m.variant_operator),
                "intended": str(m.intended_poi_id),
                "dense": dense_r[vid],
                "lex": lex_r[vid],
                "dense_top": dense_top.get(vid, []),
                "lex_top": lex_top.get(vid, []),
            }
        )
    df = pd.DataFrame(rows)
    bins = [0, 15, 20, 25, 30, 35, 40, 60]
    df["len_bucket"] = pd.cut(df["char_len"], bins=bins, right=True)

    print("char_len describe:")
    print(df["char_len"].describe().to_string())
    print("\nSpearman char_len vs rank (negative => longer => better rank):")
    print("  me5 ", f"{df['char_len'].corr(df['dense'], method='spearman'):.3f}")
    print("  bm25", f"{df['char_len'].corr(df['lex'], method='spearman'):.3f}")

    for k in (10, 100, 1000):
        print(f"\nR@{k} by len_bucket:")
        g = df.groupby("len_bucket", observed=True).agg(
            n=("variant_id", "size"),
            me5=("dense", lambda s: float(hit_series(s, k).mean())),
            bm25=("lex", lambda s: float(hit_series(s, k).mean())),
        )
        print(g.to_string(float_format=lambda x: f"{x:.3f}"))

    miss100 = df[~hit_series(df["dense"], 100)].sort_values(["char_len", "dense", "variant_id"])
    miss10 = df[~hit_series(df["dense"], 10)].sort_values(["char_len", "dense", "variant_id"])

    lines: list[str] = []
    lines.append("# mE5 miss cases — độ dài query và top hits")
    lines.append("")
    lines.append(
        "Giả thuyết: query càng dài càng dễ. Dưới đây là R theo bucket độ dài + "
        "toàn bộ miss@100 của mE5 kèm top-10 dense/BM25 để đọc tay."
    )
    lines.append("")
    lines.append("## 1. Phân bố độ dài (toàn gold)")
    lines.append("")
    lines.append(
        f"n={len(df)} · min={df.char_len.min()} · p50={df.char_len.median():.0f} · "
        f"mean={df.char_len.mean():.1f} · max={df.char_len.max()}"
    )
    lines.append("")
    lines.append(
        f"Spearman(char_len, mE5_rank) = **{df['char_len'].corr(df['dense'], method='spearman'):.3f}** "
        f"(âm = dài hơn → rank tốt hơn)"
    )
    lines.append(
        f"Spearman(char_len, BM25_rank) = **{df['char_len'].corr(df['lex'], method='spearman'):.3f}**"
    )
    lines.append("")
    lines.append("## 2. Recall mE5 theo bucket độ dài (ký tự)")
    lines.append("")
    lines.append("| char_len | n | R@10 | R@100 | R@1000 |")
    lines.append("|---|---:|---:|---:|---:|")
    for bucket, g in df.groupby("len_bucket", observed=True):
        lines.append(
            f"| {bucket} | {len(g)} | {hit_series(g['dense'], 10).mean():.3f} | "
            f"{hit_series(g['dense'], 100).mean():.3f} | {hit_series(g['dense'], 1000).mean():.3f} |"
        )
    lines.append("")
    lines.append("## 3. Miss rate: ngắn vs dài")
    lines.append("")
    for thr in (20, 25, 30):
        short = df[df.char_len <= thr]
        long = df[df.char_len > thr]
        lines.append(
            f"- **len≤{thr}**: n={len(short)} · miss@10={int((~hit_series(short['dense'], 10)).sum())} "
            f"({(~hit_series(short['dense'], 10)).mean():.1%}) · "
            f"miss@100={int((~hit_series(short['dense'], 100)).sum())} "
            f"({(~hit_series(short['dense'], 100)).mean():.1%})"
        )
        lines.append(
            f"- **len>{thr}**: n={len(long)} · miss@10={int((~hit_series(long['dense'], 10)).sum())} "
            f"({(~hit_series(long['dense'], 10)).mean():.1%}) · "
            f"miss@100={int((~hit_series(long['dense'], 100)).sum())} "
            f"({(~hit_series(long['dense'], 100)).mean():.1%})"
        )
    lines.append("")
    hit100 = df[hit_series(df["dense"], 100)]
    lines.append(
        f"Mean len — miss@100: **{miss100.char_len.mean():.1f}** · "
        f"hit@100: **{hit100.char_len.mean():.1f}** · overall: **{df.char_len.mean():.1f}**"
    )
    lines.append(
        f"Mean tokens — miss@100: **{miss100.token_n.mean():.1f}** · "
        f"hit@100: **{hit100.token_n.mean():.1f}**"
    )
    lines.append("")
    lines.append(
        f"## 4. Toàn bộ mE5 miss@100 ({len(miss100)} queries) — sort theo độ dài tăng dần"
    )
    lines.append("")
    lines.append(
        f"(Miss@10 = {len(miss10)} queries — xem JSON examples nếu cần; "
        f"dưới đây đủ sâu để đọc pattern.)"
    )
    lines.append("")

    for _, r in miss100.iterrows():
        tgt = name_map.get(r.intended)
        tgt_name = tgt.name if tgt is not None else r.intended
        lines.append(
            f"### `{r.variant_id}` · len={r.char_len} · tokens={r.token_n} · "
            f"dense_rank={r.dense} · lex_rank={r.lex}"
        )
        lines.append(f"- **query:** `{r.query_text}`")
        lines.append(f"- family=`{r.family}` · operator=`{r.operator}` · stratum=`{r.stratum}`")
        lines.append(f"- **target:** {tgt_name} [{r.intended}]")
        lines.append("- **mE5 top-10:**")
        lines.append(fmt_top(list(r.dense_top), r.intended, name_map))
        lines.append("- **BM25 top-10:**")
        lines.append(fmt_top(list(r.lex_top), r.intended, name_map))
        lines.append("")

    OUT.mkdir(parents=True, exist_ok=True)
    out_path = OUT / "09_ME5_MISS_CASES_BY_LENGTH.md"
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # compact machine summary
    summary = {
        "n": len(df),
        "spearman_len_me5_rank": float(df["char_len"].corr(df["dense"], method="spearman")),
        "spearman_len_bm25_rank": float(df["char_len"].corr(df["lex"], method="spearman")),
        "miss_at_10": int(len(miss10)),
        "miss_at_100": int(len(miss100)),
        "mean_len_miss_at_100": float(miss100.char_len.mean()) if len(miss100) else None,
        "mean_len_hit_at_100": float(hit100.char_len.mean()) if len(hit100) else None,
        "by_len_bucket_r100": {
            str(b): {
                "n": int(len(g)),
                "r10": float(hit_series(g["dense"], 10).mean()),
                "r100": float(hit_series(g["dense"], 100).mean()),
                "r1000": float(hit_series(g["dense"], 1000).mean()),
            }
            for b, g in df.groupby("len_bucket", observed=True)
        },
    }
    bench_out = ROOT / "apps/poi-search/bench/results/gold_stage1_lexical_rescue"
    bench_out.mkdir(parents=True, exist_ok=True)
    (bench_out / "length_vs_recall_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("wrote", out_path)
    print("miss@10", len(miss10), "miss@100", len(miss100))


if __name__ == "__main__":
    main()
