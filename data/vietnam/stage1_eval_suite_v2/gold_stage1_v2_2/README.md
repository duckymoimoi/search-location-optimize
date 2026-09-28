# Gold POI v2.2 — reproducible reissue

200 POI, 800 query sessions, 820 positive qrels, 200 prefix records. Payloads are byte-identical to the locked data payloads of v2.1; filenames carry v2.2, logical suite IDs stay gold_stage1_v2.

This is a previously exposed regression set, not a new holdout. Historical labels are inherited; structural validity, corpus membership, qrel consistency and train-target overlap were rechecked. No new independent human label review is claimed.

v2.1 full historical provenance remains incomplete. This reissue pins present source files and the builder, without claiming to recover the missing authoring packet. See lineage.json, source_files.json and validation_report.json.

Verify: `python tools/reissue_gold_stage1_v22.py verify`. Reproduce in a new folder: `python tools/reissue_gold_stage1_v22.py build --out artifacts/results/gold_v22_rebuild`. Do not edit this signed directory.
