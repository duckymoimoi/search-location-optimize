"""Query/document text helpers shared by lexical DSL and ranking."""
from __future__ import annotations

import re
import unicodedata
from types import SimpleNamespace

from settings import POLICY, ENCODER_NORMALIZER


def encoder_input(query: str, normalizer: str | None = None) -> str:
    """Versioned query input; lexical keys are independent of this choice."""
    mode = normalizer or ENCODER_NORMALIZER
    if mode == "raw":
        return query
    if mode == "glue_code_spans":
        return glue_code_spans(query)
    raise ValueError(f"Unknown encoder normalizer: {mode}")

def fold(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").replace("đ", "d").replace("Đ", "D")
    return " ".join("".join(ch for ch in unicodedata.normalize("NFD", text) if not unicodedata.combining(ch)).casefold().split())


def alnum_compact(text: str) -> str:
    """Fold + strip non-alphanumerics so S2.02 / s2-02 / s202 share one key."""
    return "".join(ch for ch in fold(text) if ch.isalnum())


def letter_compact(text: str) -> str:
    """Fold + letters only. 'van hanh mall' / 'vanhanh mall' / 'Vạn Hạnh Mall' share one key."""
    return "".join(ch for ch in fold(text) if ch.isalpha())


def names_compact_values(*parts: object) -> list[str]:
    """Exact space-insensitive keys for a name and its aliases. No pairs, no prefixes."""
    out: set[str] = set()
    for part in parts:
        if part is None:
            continue
        if isinstance(part, (list, tuple)):
            values = [str(item) for item in part if item is not None and str(item).strip()]
        else:
            text = str(part).strip()
            if not text or text in {"None", "nan"}:
                continue
            values = [text]
        for value in values:
            key = letter_compact(value)
            if len(key) >= 6:
                out.add(key)
    return sorted(out)


def query_name_compacts(query: str) -> list[str]:
    """Emit a name-compact key only when the query looks space-glued.

    A spaced name already matches label_folded / BM25. Address queries whose
    longest letter token is a normal Vietnamese syllable (nguyen=6) stay off
    this path so a street name cannot outrank a house+street hit.
    """
    tokens = [token for token in text_tokens(query) if _token_kind(token) == "letter"]
    key = letter_compact(query)
    if len(key) < 6:
        return []
    longest = max((len(letter_compact(token)) for token in tokens), default=0)
    # 7+ = two folded syllables glued (vanhanh). Solo 8+ = whole name glued (vanhanhmall).
    if longest >= 7 or (len(tokens) == 1 and len(key) >= 8):
        return [key]
    return []


def query_fuzzy_terms(query: str) -> list[str]:
    """Letter tokens long enough to typo. Never numbers, codes, or 1–3 letter syllables."""
    return [
        token
        for token in text_tokens(query)
        if _token_kind(token) == "letter" and len(token) >= 4
    ]


def glue_code_spans(query: str) -> str:
    """Collapse dotted or hyphenated codes into one token for the standard analyzer.

    The index analyzer splits on '.'. Without this, s10.2 is tokens s10 + 2 and
    matches every S10.* label, while s1.02 also matches S2.02 via the shared 02.
    No building-code pattern: any alphanumeric span with an internal . or -.
    Slash stays a separator so 16/2 does not become 162.
    """
    span = re.compile(r"[^\W_]+(?:[.\-][^\W_]+)+", re.UNICODE)
    return span.sub(lambda match: alnum_compact(match.group(0)), query or "")


def _token_kind(token: str) -> str:
    """letter = letters only, number = digits only, code = both."""
    has_letter = any(ch.isalpha() for ch in token)
    has_digit = any(ch.isdigit() for ch in token)
    if has_letter and has_digit:
        return "code"
    if has_letter:
        return "letter"
    if has_digit:
        return "number"
    return "other"


def is_code_key(compact: str) -> bool:
    """A code key has both a letter and a digit. A pure number is not a code."""
    return (
        len(compact) >= 2
        and any(ch.isalpha() for ch in compact)
        and any(ch.isdigit() for ch in compact)
    )


def query_code_compacts(query: str) -> list[str]:
    """One compact key per token that contains both a letter and a digit.

    Tokens are not joined. A house number plus the following words must not
    become a single code, and a pure number must not hit codes_compact.
    """
    out: list[str] = []
    seen: set[str] = set()
    for raw in fold(glue_code_spans(query)).split():
        compact = alnum_compact(raw)
        if not is_code_key(compact) or compact in seen:
            continue
        seen.add(compact)
        out.append(compact)
    return out


def letter_runs(tokens: list[str]) -> list[list[str]]:
    """Maximal runs of letter-only tokens, in query order."""
    runs: list[list[str]] = []
    current: list[str] = []
    for token in tokens:
        if _token_kind(token) == "letter":
            current.append(token)
        elif current:
            runs.append(current)
            current = []
    if current:
        runs.append(current)
    return runs


def compact_length(value: str) -> int:
    """Character length used to skip dense on short queries.

    Dots and hyphens inside codes do not count, so s10.2 and s102 take the same route.
    """
    text = unicodedata.normalize("NFKC", value or "")
    text = "".join(ch for ch in text if ch not in ".-")
    return len("".join(text.split()))


def normalized_text(value: str) -> str:
    """Normalize spacing/case while preserving Vietnamese accents."""
    return " ".join(unicodedata.normalize("NFKC", value or "").casefold().split())


def expand_query(query: str) -> str:
    """One optional lexical alternative; never replace the encoder input."""
    value = unicodedata.normalize("NFKC", query)
    for rewrite in POLICY.get("query_rewrites", []):
        value = re.sub(rewrite["pattern"], rewrite["replacement"], value, flags=re.IGNORECASE)
    return " ".join(value.split())


def text_tokens(value: str) -> list[str]:
    # Keep slash/hyphen inside address numbers and building identifiers.
    return re.findall(r"[^\W_]+(?:[/-][^\W_]+)*", fold(value))


def _accented_tokens(value: str) -> list[str]:
    return re.findall(r"[^\W_]+(?:[/-][^\W_]+)*", normalized_text(value))


def query_has_accents(query: str) -> bool:
    """True when stripping diacritics changes the query (user typed accents)."""
    return bool(normalized_text(query)) and normalized_text(query) != fold(query)


def split_path_token(token: str) -> list[str]:
    """Split a slash/hyphen chain; '259/15' → ['259', '15']. Dots are not split here."""
    if not token:
        return []
    if re.search(r"[/-]", token) and any(ch.isdigit() for ch in token):
        return [part for part in re.split(r"[/-]+", token) if part]
    return [token]


def path_atoms(query: str) -> list[str]:
    """Folded tokens with house/alley chains expanded. No street-type lexicon."""
    atoms: list[str] = []
    for token in text_tokens(query):
        atoms.extend(split_path_token(token))
    return atoms


def is_house_atom(token: str) -> bool:
    """True for a house/unit atom: pure digits, or a digit-leading code (15A).

    Letter-leading codes (B12, s10) stay on codes_compact, not house paths.
    """
    kind = _token_kind(token)
    if kind == "number":
        return True
    if kind != "code":
        return False
    first = next((ch for ch in token if ch.isalnum()), "")
    return first.isdigit()


def _is_medial_house(atoms: list[str], index: int) -> bool:
    """Number with name-letters on both sides: '3' in 'duong 3 thang 2'.

    A letter that sits after another house atom is glue ('ngo' in '259 ngo 15
    nguyen...'), so the following number is still in the house path.
    """
    if not (0 <= index < len(atoms)) or not is_house_atom(atoms[index]):
        return False
    prev_letter = index > 0 and _token_kind(atoms[index - 1]) == "letter"
    next_letter = index + 1 < len(atoms) and _token_kind(atoms[index + 1]) == "letter"
    if not (prev_letter and next_letter):
        return False
    if index >= 2 and is_house_atom(atoms[index - 2]):
        return False
    return True


def housenumber_path_key(value: str) -> str:
    """Catalog key for a housenumber field: '259/15' and '259-15' → '259 15'."""
    parts = [atom for atom in path_atoms(value) if any(ch.isdigit() for ch in atom)]
    return " ".join(parts)


def _grow_house_path(atoms: list[str], start: int) -> tuple[tuple[str, ...], int]:
    """Consume a house/alley chain. One letter token between two house atoms is glue."""
    if start >= len(atoms) or not is_house_atom(atoms[start]) or _is_medial_house(atoms, start):
        return (), start
    path = [atoms[start]]
    index = start + 1
    while index < len(atoms):
        if is_house_atom(atoms[index]) and not _is_medial_house(atoms, index):
            path.append(atoms[index])
            index += 1
            continue
        if (
            _token_kind(atoms[index]) == "letter"
            and index + 1 < len(atoms)
            and is_house_atom(atoms[index + 1])
            and not _is_medial_house(atoms, index + 1)
        ):
            path.append(atoms[index + 1])
            index += 2
            continue
        break
    return tuple(path), index


def _letter_run_from(atoms: list[str], start: int) -> list[str]:
    run: list[str] = []
    for token in atoms[start:]:
        if _token_kind(token) == "letter":
            run.append(token)
        elif run:
            break
    return run


def parse_query_structure(query: str) -> SimpleNamespace:
    """Topology-only parse: house/alley path vs named span vs number-in-name.

    Glue between house atoms is any single letter token ('ngo', '/', '-').
    A number with letters on both sides is part of a named span, not a house path.
    """
    atoms = path_atoms(query)
    medial = any(_is_medial_house(atoms, index) for index in range(len(atoms)))
    leading_path, after_leading = _grow_house_path(atoms, 0)
    named_letters = tuple(
        token for token in atoms[after_leading:] if _token_kind(token) == "letter"
    )
    inner: list[tuple[str, ...]] = []
    index = after_leading if leading_path else 0
    while index < len(atoms):
        path, end = _grow_house_path(atoms, index)
        if path and len(_letter_run_from(atoms, end)) >= 2:
            inner.append(path)
            index = end
            continue
        index += 1
    keys: list[str] = []
    seen: set[str] = set()
    for path in (leading_path, *inner):
        if not path:
            continue
        key = " ".join(path)
        if key not in seen:
            seen.add(key)
            keys.append(key)
    has_house_street = bool(leading_path) and len(named_letters) >= 2
    return SimpleNamespace(
        atoms=tuple(atoms),
        leading_path=leading_path,
        inner_paths=tuple(inner),
        named_letters=named_letters,
        path_keys=tuple(keys),
        has_house_street=has_house_street,
        has_medial_number=medial,
    )
