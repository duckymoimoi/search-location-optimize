"""Conservative bare-brand routing from accepted catalog aliases only."""
from pathlib import Path
import sqlite3

from textnorm import fold, letter_compact


def within_one_edit(left, right):
    if abs(len(left) - len(right)) > 1:
        return False
    if len(left) > len(right):
        left, right = right, left
    i = j = changes = 0
    while i < len(left) and j < len(right):
        if left[i] == right[j]:
            i += 1
            j += 1
        else:
            changes += 1
            if changes > 1:
                return False
            if len(left) == len(right):
                i += 1
            j += 1
    return changes + (len(right)-j) <= 1


class BrandRouter:
    def __init__(self, path):
        path = Path(path).resolve()
        connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
        try:
            rows = connection.execute("SELECT lookup_fold, brand_family_id FROM brand_match_index WHERE match_status = 'accepted'").fetchall()
            has_members = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='brand_members'").fetchone()
            members = connection.execute("SELECT brand_family_id, COALESCE(NULLIF(mapped_poi_id, ''), poi_id) FROM brand_members WHERE membership_status='accepted' AND destination_searchable=1").fetchall() if has_members else []
        finally:
            connection.close()
        families = {}
        for key, family in rows:
            families.setdefault(fold(key), set()).add(family)
        self.lookup = {key: next(iter(values)) for key, values in families.items() if len(values) == 1}
        self.fuzzy_keys = [(letter_compact(key), family) for key, family in self.lookup.items()
                           if not any(ch.isdigit() for ch in key) and len(letter_compact(key)) >= 7]
        self.member_ids = {}
        for family, poi_id in members:
            self.member_ids.setdefault(family, set()).add(poi_id)
        self.all_member_ids = set().union(*self.member_ids.values()) if self.member_ids else set()

    def members(self, family):
        return self.member_ids.get(family, set())

    def family(self, query, *, fuzzy=False):
        # Full-key match only: a branch/address suffix must not be erased.
        exact = self.lookup.get(fold(query))
        if exact or not fuzzy or any(ch.isdigit() for ch in query):
            return exact
        compact = letter_compact(query)
        if len(compact) < 6:
            return None
        matches = {family for key, family in self.fuzzy_keys if within_one_edit(compact, key)}
        return next(iter(matches)) if len(matches) == 1 else None
