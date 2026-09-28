from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).parents[1] / 'api'))
from brand_router import BrandRouter


def test_accepted_unambiguous_full_query_only(tmp_path):
    path = tmp_path / 'brands.sqlite'
    connection = sqlite3.connect(path)
    connection.execute('CREATE TABLE brand_match_index(lookup_fold TEXT, brand_family_id TEXT, match_status TEXT)')
    connection.executemany('INSERT INTO brand_match_index VALUES (?,?,?)', [
        ('cong ca phe', 'brand:cong', 'accepted'),
        ('highlands', 'candidate:highlands', 'needs_review'),
        ('acme', 'brand:a', 'accepted'), ('acme', 'brand:b', 'accepted')])
    connection.commit()
    connection.close()
    router = BrandRouter(path)
    assert router.family('Cộng Cà Phê') == 'brand:cong'
    assert router.family('Cộng Cà Phê Nguyễn Chí Thanh') is None
    assert router.family('highlands') is None
    assert router.family('acme') is None
    assert router.family('CongCaPh', fuzzy=True) == 'brand:cong'
    assert router.family('CongCaPh 259', fuzzy=True) is None
    assert router.family('CongCaPh Nguyen Trai', fuzzy=True) is None
