"""Re-export Overture sample CSV for Excel: UTF-8 BOM + strip control chars."""
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "overture_hanoi_sample.parquet"
OUT = ROOT / "overture_hanoi_sample_excel.csv"

con = duckdb.connect()
tmp = ROOT / "_tmp_overture_excel.csv"
con.execute(
    f"""
    COPY (
      SELECT
        id,
        regexp_replace(coalesce(name, ''), '[\\x00-\\x1F]', '', 'g') AS name,
        category,
        confidence,
        lat,
        lon,
        regexp_replace(coalesce(address_freeform, ''), '[\\x00-\\x1F]', '', 'g') AS address_freeform,
        source_dataset,
        source_license
      FROM read_parquet('{SRC.as_posix()}')
      ORDER BY name
    ) TO '{tmp.as_posix()}' (HEADER, DELIMITER ',');
    """
)
OUT.write_bytes(b"\xef\xbb\xbf" + tmp.read_bytes())
tmp.unlink(missing_ok=True)
print(f"Wrote {OUT} ({OUT.stat().st_size / 1e6:.2f} MB)")
