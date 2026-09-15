"""Audit Overture sample for encoding artifacts and address coverage."""
from collections import Counter
from pathlib import Path

import duckdb

P = Path(__file__).resolve().parent / "overture_hanoi_sample.parquet"


def main() -> None:
    con = duckdb.connect()
    n = con.execute(f"SELECT count(*) FROM read_parquet('{P.as_posix()}')").fetchone()[0]

    # Control / weird chars in name
    bad = con.execute(
        f"""
        SELECT
          count(*) FILTER (WHERE name IS NOT NULL AND regexp_matches(name, '[\\x00-\\x08\\x0B\\x0C\\x0E-\\x1F]')) AS ctrl_in_name,
          count(*) FILTER (WHERE name IS NOT NULL AND starts_with(name, chr(8))) AS starts_with_bs,
          count(*) FILTER (WHERE address_freeform IS NOT NULL AND regexp_matches(address_freeform, '[\\x00-\\x08\\x0B\\x0C\\x0E-\\x1F]')) AS ctrl_in_addr,
          count(*) FILTER (WHERE address_freeform IS NOT NULL AND length(trim(address_freeform)) > 0) AS has_addr,
          count(*) FILTER (WHERE address_freeform IS NULL OR length(trim(address_freeform)) = 0) AS no_addr,
          count(*) FILTER (WHERE category IS NULL) AS no_cat
        FROM read_parquet('{P.as_posix()}')
        """
    ).fetchone()

    # Peek raw bytes of first weird names
    samples = con.execute(
        f"""
        SELECT name, address_freeform, category, lat, lon
        FROM read_parquet('{P.as_posix()}')
        WHERE name IS NOT NULL AND regexp_matches(name, '[\\x00-\\x08\\x0B\\x0C\\x0E-\\x1F]')
        LIMIT 5
        """
    ).fetchall()

    print(f"rows={n}")
    print(
        "ctrl_in_name=",
        bad[0],
        "starts_with_bs=",
        bad[1],
        "ctrl_in_addr=",
        bad[2],
        "has_addr=",
        bad[3],
        "no_addr=",
        bad[4],
        "no_cat=",
        bad[5],
    )
    print("addr_coverage_pct=", round(100.0 * bad[3] / n, 2))
    print("weird_name_samples:")
    for name, addr, cat, lat, lon in samples:
        print("  repr=", repr(name[:80]))
        print("  utf8=", name.encode('utf-8', errors='replace')[:40])
        print("  addr=", repr(addr)[:120] if addr else None, "cat=", cat)

    # Address length distribution among those with address
    lens = con.execute(
        f"""
        SELECT
          approx_quantile(length(address_freeform), 0.5),
          approx_quantile(length(address_freeform), 0.9),
          max(length(address_freeform)),
          count(*) FILTER (WHERE address_freeform ILIKE '%,%') AS has_comma,
          count(*) FILTER (WHERE address_freeform ~ '(?i)(hà nội|ha noi|hanoi)') AS mentions_hanoi
        FROM read_parquet('{P.as_posix()}')
        WHERE address_freeform IS NOT NULL AND length(trim(address_freeform)) > 0
        """
    ).fetchone()
    print("addr_len_p50/p90/max=", lens[0], lens[1], lens[2])
    print("addr_has_comma=", lens[3], "mentions_hanoi=", lens[4])

    # Check if CSV was written with BOM
    csv = Path(__file__).resolve().parent / "overture_hanoi_sample.csv"
    head = csv.read_bytes()[:8]
    print("csv_head_bytes=", head)
    print("csv_has_utf8_bom=", head.startswith(b"\xef\xbb\xbf"))


if __name__ == "__main__":
    main()
