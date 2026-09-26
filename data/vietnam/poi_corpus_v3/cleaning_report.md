# vn-poi-core-v3-semantic-address-dedup50

Source: `D:\vsf\data\vietnam\poi_corpus_v2` (184,135 POI).
Output: **179,209 POI** (4,433 duplicates merged, 493 junk/foreign dropped).

| Decision | Rows |
|---|---:|
| keep | 179,209 |
| merge_duplicate | 4,433 |
| drop_junk_or_foreign | 493 |

### Deduplication breakdown by address rule:

| Rule | Merged Count |
|---|---:|
| `both_no_address` | 3,533 |
| `one_street_compatible` | 635 |
| `one_house_street_compatible` | 64 |
| `same_house_and_street` | 72 |
| `same_street_no_housenumber` | 129 |

### Dropped Junk & Foreign POIs breakdown (Option A):

| Reason | Dropped Count |
|---|---:|
| `pure_non_latin_Cyrillic` | 91 |
| `outside_admin_vn` | 323 |
| `osm_fixme_todo` | 2 |
| `generic_no_name` | 4 |
| `pure_non_latin_Korean` | 32 |
| `pure_non_latin_Lao` | 1 |
| `pure_non_latin_Thai` | 2 |
| `pure_non_latin_Chinese_CJK` | 20 |
| `obstacle_osm_note` | 4 |
| `pure_non_latin_Chinese_CJK_Japanese` | 9 |
| `pure_non_latin_Japanese` | 1 |
| `border_checkpoint` | 2 |
| `pure_non_latin_Khmer` | 1 |
| `pure_non_latin_Chinese_CJK_Korean` | 1 |

### Target Protection Summary:
- Gold Targets (400 IDs): **100% preserved (0 merged, 0 dropped)**.
- Train v6 Checkpoint (500 IDs): **100% preserved (0 merged, 0 dropped)**.
- Train 20k Pool (19939 IDs): **Filtered to remove 38 internal duplicates and 11 foreign/junk POIs**.

All removed IDs and retained representatives are recorded in `poi_id_migration.parquet`.
The v2 corpus and live index were not modified. A new embedding matrix and index are required before activation.
