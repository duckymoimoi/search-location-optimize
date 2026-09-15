"""Download a small Overture Places sample over central Hanoi via anonymous S3."""
from pathlib import Path

import duckdb

OUT_CSV = Path(__file__).resolve().parent / "overture_hanoi_sample.csv"
OUT_PARQUET = Path(__file__).resolve().parent / "overture_hanoi_sample.parquet"
RELEASE = "2026-08-19.0"
# Central Hanoi sample bbox (west, south, east, north)
W, S, E, N = 105.75, 20.95, 105.90, 21.08
SRC = (
    f"s3://overturemaps-us-west-2/release/{RELEASE}/"
    "theme=places/type=place/*"
)


def main() -> None:
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute("INSTALL spatial; LOAD spatial;")
    con.execute("SET s3_region='us-west-2';")
    con.execute("SET s3_access_key_id='';")
    con.execute("SET s3_secret_access_key='';")

    sql = f"""
    COPY (
      SELECT
        id,
        names.primary AS name,
        categories.primary AS category,
        confidence,
        ST_Y(geometry) AS lat,
        ST_X(geometry) AS lon,
        addresses[1].freeform AS address_freeform,
        sources[1].dataset AS source_dataset,
        sources[1].license AS source_license
      FROM read_parquet('{SRC}', hive_partitioning=1)
      WHERE bbox.xmin BETWEEN {W} AND {E}
        AND bbox.xmax BETWEEN {W} AND {E}
        AND bbox.ymin BETWEEN {S} AND {N}
        AND bbox.ymax BETWEEN {S} AND {N}
        AND names.primary IS NOT NULL
    ) TO '{OUT_PARQUET.as_posix()}' (FORMAT PARQUET);
    """
    print(f"Querying {RELEASE} places in bbox {W},{S},{E},{N} ...")
    con.execute(sql)
    con.execute(
        f"""
        COPY (
          SELECT * FROM read_parquet('{OUT_PARQUET.as_posix()}')
          ORDER BY name
        ) TO '{OUT_CSV.as_posix()}' (HEADER, DELIMITER ',');
        """
    )
    n = con.execute(
        f"SELECT count(*) FROM read_parquet('{OUT_PARQUET.as_posix()}')"
    ).fetchone()[0]
    sample = con.execute(
        f"""
        SELECT name, category, lat, lon
        FROM read_parquet('{OUT_PARQUET.as_posix()}')
        ORDER BY name LIMIT 8
        """
    ).fetchall()
    print(f"Wrote {OUT_CSV}")
    print(f"Wrote {OUT_PARQUET}")
    print(f"rows={n}")
    print("sample:")
    for row in sample:
        print(" ", row)


if __name__ == "__main__":
    main()
