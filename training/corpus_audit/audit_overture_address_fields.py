"""Inspect Overture Places address struct coverage for Hanoi sample bbox."""
import duckdb

RELEASE = "2026-08-19.0"
W, S, E, N = 105.75, 20.95, 105.90, 21.08
SRC = f"s3://overturemaps-us-west-2/release/{RELEASE}/theme=places/type=place/*"

con = duckdb.connect()
con.execute("INSTALL httpfs; LOAD httpfs;")
con.execute("SET s3_region='us-west-2';")
con.execute("SET s3_access_key_id='';")
con.execute("SET s3_secret_access_key='';")

print("Address struct schema:")
print(
    con.execute(
        f"""
        SELECT addresses[1]
        FROM read_parquet('{SRC}', hive_partitioning=1)
        WHERE bbox.xmin BETWEEN {W} AND {E}
          AND names.primary IS NOT NULL
          AND len(addresses) > 0
        LIMIT 1
        """
    ).fetchone()
)

sql = f"""
SELECT
  count(*) AS n,
  count(*) FILTER (WHERE len(addresses) > 0) AS has_addresses_arr,
  count(*) FILTER (WHERE addresses[1].freeform IS NOT NULL AND length(trim(addresses[1].freeform))>0) AS has_freeform,
  count(*) FILTER (WHERE addresses[1].locality IS NOT NULL) AS has_locality,
  count(*) FILTER (WHERE addresses[1].region IS NOT NULL) AS has_region,
  count(*) FILTER (WHERE addresses[1].postcode IS NOT NULL) AS has_postcode,
  count(*) FILTER (WHERE addresses[1].country IS NOT NULL) AS has_country
FROM read_parquet('{SRC}', hive_partitioning=1)
WHERE bbox.xmin BETWEEN {W} AND {E}
  AND bbox.xmax BETWEEN {W} AND {E}
  AND bbox.ymin BETWEEN {S} AND {N}
  AND bbox.ymax BETWEEN {S} AND {N}
  AND names.primary IS NOT NULL
"""
print("\nCoverage:")
print(con.execute(sql).fetchdf().to_string(index=False))

print("\nSamples:")
for name, addr in con.execute(
    f"""
    SELECT names.primary AS name, addresses[1] AS addr
    FROM read_parquet('{SRC}', hive_partitioning=1)
    WHERE bbox.xmin BETWEEN {W} AND {E}
      AND bbox.xmax BETWEEN {W} AND {E}
      AND bbox.ymin BETWEEN {S} AND {N}
      AND bbox.ymax BETWEEN {S} AND {N}
      AND names.primary IS NOT NULL
      AND addresses[1].freeform IS NOT NULL
    LIMIT 8
    """
).fetchall():
    print(repr(name)[:70])
    print(" ", addr)
