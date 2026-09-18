# SEARCH 2.0 — Query Variant & Noise Generation Rules v5

> **Status:** Design draft (English, full operator detail)  
> **Authoring standard (use this to expand gold):** [`SEARCH_2.0_STAGE1_QUERY_VARIANT_STANDARD.md`](./SEARCH_2.0_STAGE1_QUERY_VARIANT_STANDARD.md)  
> **Scope:** Stage 1 text retrieval only  
> **Goal:** Generate realistic Vietnamese POI-search query variants for zero-shot evaluation support and later contrastive training, without mixing textual errors with geo/personalization signals.

---

## 1. Design principles

1. **Stage 1 is text-only.**  
   Origin, distance, time, popularity, and user history are not used to generate or label Stage 1 query variants.

2. **Not every variant is an error.**  
   Separate:
   - valid orthographic / IME variants,
   - mechanical typing errors,
   - phonological spelling errors,
   - incomplete prefixes,
   - aliases / abbreviations,
   - address-format variants,
   - structural word-order variants.

3. **Evaluation and training have different requirements.**
   - **Evaluation:** curated, human-authored or human-reviewed, primarily single controlled transformations.
   - **Training:** may use larger synthetic expansion, including compound noise after single-error behavior is validated.

4. **Synthetic generation must preserve intent.**  
   A generated query must still reasonably refer to the intended POI. If an edit can change the destination to a different real POI/address, reject the sample.

5. **Applicability is operator-specific.**  
   Do not apply every operator to every POI.

6. **Keep the original clean query.**  
   Every synthetic row must be traceable to one canonical human-reviewed query.

---

## 2. Schema

Recommended fields:

```text
case_id
variant_id

query_text
canonical_query

query_variant_family
variant_operator
variant_subtype
severity

query_types
language_type

intended_poi_id
acceptable_poi_ids_full

source
generator_version
review_status
split

display_grapheme_count
whitespace_token_count
```

Optional diagnostic fields:

```text
edit_position
edit_token
edit_distance
operator_params
parent_variant_id
generation_seed
```

### 2.1 `query_variant_family`

Allowed values:

```text
CLEAN
ORTHOGRAPHIC_IME
MECHANICAL_TYPO
PHONOLOGICAL
TOKEN_EDIT
PREFIX
ALIAS
ADDRESS_VARIANT
STRUCTURAL
```

### 2.2 `severity`

```text
CLEAN
SINGLE
COMPOUND
```

Policy:

- Pilot / gold evaluation: primarily `CLEAN` and `SINGLE`.
- Training expansion: may include `COMPOUND`.
- A `COMPOUND` query should normally contain at most 2 transformations in the first training version.

---

## 3. Operator taxonomy

## 3.1 CLEAN

### `canonical`

Human-authored or human-reviewed query that contains enough information to identify the intended POI under Stage-1 text-only semantics.

Example:

```text
Bệnh viện Bạch Mai
Highlands Trần Duy Hưng
16/2 Lê Văn Khương
B3 Thành Công
```

Rules:

- No synthetic corruption.
- No chat-style templates such as `cho tôi đến ...`.
- Do not inject origin/current-location text unless it is naturally part of the query.
- For multi-branch brands, canonical query should contain textual disambiguation when needed.

---

## 3.2 ORTHOGRAPHIC_IME

These are Vietnamese input/orthographic variants. They are not necessarily user mistakes.

### `strip_diacritics`

Remove Vietnamese diacritics while preserving letters and token boundaries.

```text
Bệnh viện Bạch Mai
→ Benh vien Bach Mai
```

Constraints:

- Do not modify digits, `/`, `-`, building codes, or Latin brand names unnecessarily.
- Result must remain readable.

---

### `partial_diacritics`

Remove accents from only part of the query.

```text
Bệnh viện Bạch Mai
→ Bệnh vien Bach Mai
```

Purpose:

- Model mixed converted/unconverted Vietnamese input.

Constraints:

- Modify at least one but not all eligible Vietnamese tokens.
- Avoid generating a duplicate of `strip_diacritics`.

---

### `tone_confuse`

Replace a Vietnamese tone mark with another plausible tone.

```text
Phở Bò Nam Định
→ Phợ Bò Nam Định
```

Constraints:

- Change tone only; avoid simultaneously changing base consonants/vowels.
- One controlled error for evaluation.

---

### `telex_leftover`

Generate incomplete/unconverted Telex artifacts.

Examples:

```text
cửa hàng
→ cuwar hang

mỹ phẩm
→ myx phaamr

đường
→ dduwowng
```

Recommended subtypes:

```text
telex_vowel_marker
telex_dd
telex_tone_marker
partial_telex
mixed_converted_telex
```

Constraints:

- Keep subtype internally even if top-level operator remains `telex_leftover`.
- Do not generate impossible random Telex sequences.
- Prefer patterns observed in Vietnamese input behavior.

---

## 3.3 MECHANICAL_TYPO

Mechanical keyboard/touch typing errors.

### `char_delete`

Delete one character from an alphabetic token.

```text
bach mai
→ bac mai
```

Constraints:

- Do not delete the only character of a token.
- Do not delete digits from house numbers/codes by default.
- Reject if the result becomes a different known POI/code with high ambiguity.

---

### `char_insert`

Insert one plausible character.

```text
bach mai
→ bacch mai
```

Preferred sources:

- neighboring keyboard key,
- repeated nearby character,
- common accidental insertion.

Avoid uniformly random alphabet insertion for evaluation.

---

### `char_substitute`

Replace one character with another.

```text
bach mai
→ baxh mai
```

Constraints:

- Prefer keyboard-neighbor or empirically plausible substitutions.
- Keep separate from phonological substitutions.

---

### `char_transpose`

Swap two adjacent characters.

```text
bach
→ bcah
```

Constraints:

- Adjacent characters only.
- Do not use this label for swapping entire syllables/tokens.

---

### `adjacent_key`

Replace one character with a QWERTY-adjacent key.

```text
tan phong
→ tan phpng
```

Constraints:

- Use an explicit keyboard adjacency map.
- Do not modify Vietnamese combining marks independently.
- Prefer applying to normalized alphabetic characters.

---

### `double_letter`

Repeat a character due to double-tap.

```text
cà phê
→ càà phê

bach
→ bachh
```

Constraints:

- Must be a true duplicated character.
- Telex markers such as `aa`, `ee`, `dd` belong to `telex_leftover` when they represent unfinished IME input.

---

## 3.4 PHONOLOGICAL

### `phonological_confusion`

Replace a Vietnamese syllable component with a plausible pronunciation-related alternative.

Candidate confusion families may include:

```text
s ↔ x
tr ↔ ch
d ↔ gi ↔ r
l ↔ n
final consonant confusions when plausible
```

Example:

```text
trường
→ chường
```

Constraints:

- Use a curated Vietnamese confusion table.
- Do not apply every regional confusion uniformly.
- Treat literature-based confusion sets as coverage guidance, not production frequency.
- Reject transformations that create a different valid POI/name with changed intent.

---

## 3.5 TOKEN_EDIT

### `syllable_delete`

Delete one non-critical syllable/token.

```text
Bệnh viện Đại học Y Dược
→ Bệnh viện Đại học Y
```

or a realistic omission:

```text
Tiệm của Hòa 214A Bùi Văn Ba
→ Hòa 214A Bùi Ba
```

Constraints:

- Never delete the only discriminative token if doing so changes the query into a generic ambiguous intent.
- For evaluation, remove at most one syllable/token.
- Do not delete house-number components by this operator.

---

### `space_merge`

Merge an existing token boundary.

```text
Bách Hóa Xanh
→ BáchHóa Xanh
```

Constraints:

- Merge exactly one boundary for `SINGLE`.
- Result must remain a plausible fast-typing artifact.

---

### `space_split`

Insert a space inside a token.

```text
Highlands
→ High lands
```

Constraints:

- Avoid splitting building codes or house numbers unless there is evidence for that format.
- Prefer longer alphabetic tokens.

---

## 3.6 PREFIX

Prefix variants are incomplete queries, not errors.

### `char_prefix`

Generate character/grapheme prefixes from the canonical query.

Example:

```text
b
bệ
bện
bệnh
bệnh 
bệnh v
...
bệnh viện bạch mai
```

Rules:

- Use **Unicode grapheme clusters**, not bytes.
- Prefixes used for FHC/SHC/PrefixAUC should be generated deterministically at benchmark time.
- Do not store every prefix permanently in the gold dataset unless needed for reproducibility.

---

### `token_prefix`

Generate whitespace-token prefixes.

```text
bệnh
bệnh viện
bệnh viện bạch
bệnh viện bạch mai
```

Purpose:

- Coarser diagnostic benchmark.
- Keep separate from character-prefix metrics.

---

### `mid_token_incomplete`

Cut inside the final token.

```text
bệnh viện bạ
```

This is useful as a stored human-readable variant, but full character-prefix benchmarking should still be deterministic.

---

## 3.7 ALIAS

Aliases are valid alternative ways to refer to the same POI. They are not noise.

### `abbreviation`

```text
Bệnh viện Đa khoa
→ BVĐK

Đại học Quốc gia
→ ĐHQG
```

Constraints:

- Use only known/common abbreviations or manually approved abbreviations.
- Do not invent arbitrary initials.

---

### `short_name`

Drop generic name components while preserving identity.

```text
Quán Cơm Tấm Ba Ghiền
→ Cơm Tấm Ba Ghiền
→ Ba Ghiền
```

Constraints:

- Must remain semantically valid for the intended POI.
- If the result becomes ambiguous across many POIs, `acceptable_poi_ids_full` must reflect that.

---

### `code_short`

Use a validated building/transit/unit code.

```text
Nhà B3 Tập thể Thành Công
→ B3
```

Constraints:

- Apply only if the POI has a verified code/ref.
- Do not invent codes.
- If the code is non-unique in the corpus, use set-valued qrels or exclude from unique-target evaluation.

---

### `name_area`

Alternative name + textual area.

```text
Highlands Coffee Trần Duy Hưng
→ Highlands Trần Duy Hưng
→ Highlands Cầu Giấy
```

Constraints:

- Area must be factual for the POI.
- If area-level query matches multiple branches, qrels must contain all Stage-1-acceptable POIs.

---

### `english_or_bilingual_alias`

Examples:

```text
Đại học Quốc gia Hà Nội
→ Vietnam National University Hanoi
```

Constraints:

- Use only verified alternate names.
- Do not machine-translate POI proper names blindly.

---

## 3.8 ADDRESS_VARIANT

### `slash_normalize`

Normalize alley/house-number separators.

```text
16/2 Lê Văn Khương
→ 16 2 Lê Văn Khương
→ 16-2 Lê Văn Khương
```

Constraints:

- Apply only when `/` is present in the verified address.
- Do not delete a numeric component.
- Reject if normalized form maps naturally to a different address.

---

### `housenumber_format`

Controlled formatting variants:

```text
72B
→ 72 B

A58
→ A 58
```

Constraints:

- Preserve all semantic number/letter components.
- No digit deletion.

---

### `address_component_omission`

Drop one address component only when the remaining query still reasonably identifies the intended address/POI.

Example:

```text
121 Lê Lợi, Phường Bến Thành, Quận 1
→ 121 Lê Lợi, Quận 1
```

Constraints:

- Not for gold unique-target cases if omission makes the query ambiguous.
- Prefer training augmentation or set-valued qrels.

---

## 3.9 STRUCTURAL

### `token_order_variant`

Reorder tokens/syllables without modeling a mechanical typo.

Examples:

```text
Highlands Coffee
→ Coffee Highlands

Bệnh viện Bạch Mai
→ Bạch Mai Bệnh viện
```

Constraints:

- Treat as a structural robustness test, not a typing error.
- Use conservative permutations only.
- Avoid random full shuffling.

---

## 4. Applicability rules

Each operator must define:

```text
eligible(query, poi) -> bool
apply(query, poi, seed) -> candidate
validate(candidate, query, poi, corpus) -> pass/fail
```

Minimum applicability constraints:

| Operator | Apply when | Reject when |
|---|---|---|
| `strip_diacritics` | Vietnamese diacritics exist | output identical |
| `telex_leftover` | Vietnamese syllable supports Telex transform | invalid/random Telex artifact |
| `char_delete` | alphabetic token length >= 3 | deletes critical code/digit |
| `char_insert` | alphabetic token exists | implausible random artifact |
| `char_substitute` | alphabetic token exists | changes intended entity |
| `char_transpose` | token length >= 2 | crosses token boundary |
| `adjacent_key` | QWERTY-mappable char exists | modifies digit/address semantics |
| `double_letter` | alphabetic char exists | actually represents Telex marker |
| `phonological_confusion` | curated confusion applies | changes intent/entity |
| `syllable_delete` | >= 2 meaningful tokens | query becomes generic/non-identifying |
| `space_merge` | >= 2 tokens | output duplicate of another variant |
| `space_split` | long alphabetic token exists | breaks building/address code |
| `code_short` | verified code exists | code is fabricated |
| `slash_normalize` | verified address contains `/` | loses numeric component |
| `token_order_variant` | >= 2 reorderable lexical tokens | random/unrealistic permutation |

---

## 5. Single vs compound generation

## 5.1 Evaluation

Default:

```text
canonical
+
one controlled transformation
```

Reason:

- preserves interpretability,
- enables per-operator failure analysis,
- avoids attributing one failure to several simultaneous corruptions.

Recommended gold evaluation mix:

```text
CLEAN
ORTHOGRAPHIC_IME / SINGLE
MECHANICAL_TYPO / SINGLE
PHONOLOGICAL / SINGLE
TOKEN_EDIT / SINGLE
ALIAS
ADDRESS_VARIANT
STRUCTURAL
```

Prefix sequences are generated separately.

---

## 5.2 Training

Training may use:

```text
SINGLE
COMPOUND(max_ops=2)
```

Recommended compound examples:

```text
strip_diacritics + char_delete
strip_diacritics + adjacent_key
partial_diacritics + space_merge
telex_leftover + char_delete
abbreviation + strip_diacritics
```

Avoid:

```text
3+ random operators
multiple destructive deletions
code_short + destructive typo
address-number deletion
```

A compound sample should remain recognizable to a human reviewer.

---

## 6. Sampling policy

Do **not** copy operator frequencies directly from external papers/datasets.

Literature should answer:

```text
Which error/variant families exist?
```

Production logs should eventually answer:

```text
How frequent is each family in our app?
```

Before real logs exist, maintain two distributions:

### 6.1 Diagnostic evaluation distribution

Purpose: guarantee minimum coverage for each failure type.

Example target:

```text
>= 30 independent cases for each major family
>= 15 independent cases for each low-frequency specialist operator
```

Do not count multiple variants from the same `case_id` as independent cases.

### 6.2 Training distribution

Use broad but conservative augmentation.

Suggested initial constraints:

```text
clean_or_alias          35–45%
orthographic_ime        20–30%
mechanical_typo         15–25%
token_edit               5–10%
phonological             3–8%
address/structural       domain-dependent
compound                 <= 20% of generated samples
```

These are engineering starting points, **not empirical production frequencies**. Reweight when real query logs become available.

---

## 7. Qrels policy

Variant generation must respect Stage-1 semantics.

### 7.1 Unique intent

```text
query -> one clearly intended POI
```

Use:

```text
acceptable_poi_ids_full = [target]
```

### 7.2 Ambiguous text-only intent

Examples:

```text
KFC Lạng Sơn
Pepper Lunch Hà Nội
quán ăn
Highlands Cầu Giấy
```

If multiple POIs are equally defensible without origin/context:

```text
acceptable_poi_ids_full = [
  poi_a,
  poi_b,
  ...
]
```

Do not force Stage 1 to choose the branch that would only become preferable after Stage-2 geo/personalization signals.

---

## 8. Validation rules

Every generated variant must pass all applicable checks.

### 8.1 General

1. Non-empty query.
2. Different from canonical after configured normalization.
3. Different from other variants in the same `case_id`.
4. Intended semantics preserved.
5. No invented venue/name/address/code.
6. No origin-derived terms injected automatically.
7. Exactly one `query_variant_family`.
8. `variant_operator` belongs to that family.
9. `severity` matches the number/type of transformations.

### 8.2 Text normalization duplicate check

At minimum compare after:

```text
Unicode normalization
case fold
trim
collapse whitespace
```

For duplicate detection only, optionally compare a diacritic-folded form.

### 8.3 Corpus-aware validation

Reject a generated query when:

- it exactly names another POI,
- an address edit changes to another known house number,
- a building code becomes another valid code,
- deletion creates an unacceptably broad category query while qrels remain single-target.

---

## 9. Recommended evaluation slices

Always report aggregate and slices by:

```text
query_variant_family
variant_operator
primary_sampling_stratum
query_types
language_type
```

Core Stage-1 metrics:

```text
Recall@50
Recall@100
Recall@500
Recall@1000

MRR@10
SR@1
SR@5
SR@10

FHC-char@1/5/10
SHC-char@1/5/10
PrefixAUC@5/10

FHC-token@5
SHC-token@5
```

For model comparison, bootstrap/statistical resampling should use `case_id` / `pair_id` as the independent unit, not individual generated variants.

---

## 10. Migration from `noise_taxonomy_v4`

Recommended mapping:

| v4 | v5 |
|---|---|
| `strip_diacritics` | `ORTHOGRAPHIC_IME / strip_diacritics` |
| `telex_leftover` | `ORTHOGRAPHIC_IME / telex_leftover` |
| `double_letter` | `MECHANICAL_TYPO / double_letter` |
| `space_merge_split` | split into `TOKEN_EDIT / space_merge` and `space_split` |
| `syllable_delete` | `TOKEN_EDIT / syllable_delete` |
| `syllable_substitute` | split into `PHONOLOGICAL / phonological_confusion`, `ALIAS / abbreviation`, or orthographic variant |
| `tone_confuse` | `ORTHOGRAPHIC_IME / tone_confuse` |
| `adjacent_key` | `MECHANICAL_TYPO / adjacent_key` |
| `transpose_syllable` | usually `STRUCTURAL / token_order_variant`; mechanical typo becomes `char_transpose` |
| `prefix_incomplete` | `PREFIX / char_prefix`, `token_prefix`, or `mid_token_incomplete` |
| `slash_normalize` | `ADDRESS_VARIANT / slash_normalize` |
| `code_short` | `ALIAS / code_short` |

New v5 operators:

```text
partial_diacritics
char_delete
char_insert
char_substitute
char_transpose
phonological_confusion
space_merge
space_split
char_prefix
token_prefix
mid_token_incomplete
short_name
name_area
english_or_bilingual_alias
housenumber_format
address_component_omission
token_order_variant
```

---

## 11. Recommended implementation order

### Phase A — before expanding evaluation

1. Migrate v4 labels to v5 families/operators.
2. Fix set-valued qrels for ambiguous Stage-1 queries.
3. Add deterministic grapheme-prefix benchmark.
4. Add the four core mechanical edit operators:
   - `char_delete`
   - `char_insert`
   - `char_substitute`
   - `char_transpose`
5. Review `syllable_substitute` cases and remap them.

### Phase B — expand diagnostic gold set

Increase independent intents, not merely number of variants.

Prioritize:

```text
very_short
brand_multi_branch
ambiguous_category
address/alley/house_number
long_tail
VI/EN mixed
abbreviation
hard lexical distractors
rare mechanical typo
phonological confusion
```

### Phase C — training expansion

Generate larger synthetic data with:

```text
single controlled variants
+
limited compound variants
+
hard-negative mining
```

Keep generation and negative mining separately traceable.

---

## 12. Literature basis

This taxonomy is motivated by the following lines of work:

- **VSEC / Vietnamese spelling correction:** real Vietnamese spelling-error distributions and synthetic corruption for training; supports separating real evaluation data from synthetic augmentation.
- **Vietnamese synthetic spelling-correction datasets:** character insertion/deletion/substitution/transposition, QWERTY adjacency, Telex, accent and phonological variations.
- **MGeo / GeoTES:** POI search with geographic expressions, colloquial/incomplete queries, and query–POI retrieval/reranking formulation.
- **Baidu POI auto-completion:** incomplete-prefix search as a first-class problem; typing effort and early target appearance matter independently from full-query ranking.
- **POI retrieval literature:** Stage-1 candidate retrieval and Stage-2 contextual reranking should be evaluated separately when Stage 1 is intentionally text-only.

External literature defines plausible failure/variant families. It must **not** be treated as evidence for the production frequency of each operator in this project.

---

## 13. Final rule

> **Generate broad training data, but keep evaluation controlled.**
>
> A Stage-1 synthetic query is valid only when:
>
> 1. it represents a plausible way a user could type/refer to the POI,
> 2. it preserves the intended text-level search semantics,
> 3. its transformation is explicitly labeled,
> 4. it can be traced to a clean human-reviewed query,
> 5. it does not require origin/time/history to determine correctness.

