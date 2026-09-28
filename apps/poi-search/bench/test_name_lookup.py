from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).parents[1]/'api'))
from name_lookup import strong_full_name_match, lookup_name_candidates


def test_strong_catalog_match_keeps_numbers_and_full_address():
    doc={'search_label':'Bệnh viện Đại Đồng','search_aliases':[],'address':'12 Nguyễn Trãi'}
    assert strong_full_name_match('benh vien dai dong',doc)=='full_name_exact'
    assert strong_full_name_match('Bệnh viện Đại Đồng 12 Nguyễn Trãi',doc)=='full_name_address_exact'
    assert strong_full_name_match('Bệnh viện Đại Đồng 13 Nguyễn Trãi',doc) is None
    assert strong_full_name_match('Bệnh viện Đồng',doc) is None
    assert strong_full_name_match('Bệnh viện Đại Đnog',doc)=='full_name_letter_transpose'


def test_multiple_strong_matches_are_not_promoted():
    class Client:
        def request(self,*args):
            return {'hits':{'hits':[{'_id':str(i),'_score':5,'_source':{'search_label':'Bệnh viện Đại Đồng'}} for i in (1,2)]}}
    assert lookup_name_candidates(Client(),'Bệnh viện Đại Đồng')[0]==[]
