# Stratified sample 200 queries for quality review

Seed: 20260913. Quotas: {'retrieval_core': 90, 'autocomplete': 30, 'ambiguity_stress': 30, 'ime_keystream': 25, 'structured_code': 25}

- retrieval_core: 90 ({'abbreviation': 5, 'address_exact': 5, 'address_first': 4, 'address_namespace': 4, 'adjacent_transpose': 4, 'character_deletion': 4, 'clean_name': 4, 'editorial_paraphrase': 4, 'grounded_search_phrase': 4, 'keyboard_neighbor': 4, 'mixed_two_errors': 4, 'name_address': 4, 'name_street': 4, 'no_diacritics': 4, 'partial_diacritics': 4, 'repeated_character': 4, 'search_phrase': 4, 'slash_alley_address': 4, 'source_alias_or_abbreviation': 4, 'space_edit': 4, 'unit_with_namespace': 4, 'wrong_tone': 4})
- autocomplete: 30 ({'prefix_4': 6, 'prefix_5': 6, 'prefix_6': 6, 'prefix_7': 6, 'prefix_8': 6})
- ambiguity_stress: 30 ({'address_exact': 1, 'adjacent_transpose': 2, 'character_deletion': 2, 'clean_name': 2, 'editorial_paraphrase': 2, 'grounded_search_phrase': 2, 'keyboard_neighbor': 2, 'mixed_two_errors': 2, 'no_diacritics': 1, 'partial_diacritics': 1, 'prefix_1': 1, 'prefix_2': 1, 'prefix_3': 1, 'prefix_4': 1, 'prefix_5': 1, 'prefix_6': 1, 'prefix_7': 1, 'prefix_8': 1, 'repeated_character': 1, 'search_phrase': 1, 'source_alias_or_abbreviation': 1, 'space_edit': 1, 'wrong_tone': 1})
- ime_keystream: 25 ({'ime_raw_keys': 9, 'telex_raw_keys': 8, 'vni_raw_keys': 8})
- structured_code: 25 ({'address_first': 2, 'address_namespace': 1, 'adjacent_transpose': 2, 'clean_name': 2, 'name_address': 2, 'name_street': 1, 'no_diacritics': 2, 'partial_diacritics': 2, 'prefix_1': 2, 'prefix_2': 2, 'prefix_3': 2, 'search_phrase': 2, 'slash_alley_address': 1, 'structured_code': 1, 'wrong_tone': 1})

## 1. [retrieval_core/abbreviation] `hnq10k-v3-07079`
- **query**: `bv đa khoa đan phượng`
- **clean_query**: `Bệnh viện Đa khoa Đan Phượng`
- **POI**: Bệnh viện Đa khoa Đan Phượng | Phùng | amenity=hospital
- **split**: test_synthetic | surface=committed_text | gen=grounded_composition
- **compat**: 1 | train_elig=False | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False
- **flags**: main_excl=[] train_excl=['not_train_split'] review=[]

## 2. [retrieval_core/address_exact] `hnq10k-v3-01706`
- **query**: `73 ngô 71 việt hưng`
- **clean_query**: `73 Ngô 71 Việt Hưng`
- **POI**: 73 Ngô 71 Việt Hưng | 73 Ngô 71 Việt Hưng | address=
- **split**: train | surface=committed_text | gen=grounded_composition
- **compat**: 1 | train_elig=True | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False

## 3. [retrieval_core/address_first] `hnq10k-v3-03625`
- **query**: `30 ngõ kiến thiết trường mầm non nắng hồng`
- **clean_query**: `Trường Mầm non Nắng Hồng 30 Ngõ Kiến Thiết`
- **POI**: Trường Mầm non Nắng Hồng | 30 Ngõ Kiến Thiết | amenity=kindergarten
- **split**: train | surface=committed_text | gen=grounded_composition
- **compat**: 1 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['missing_sibling_address'] train_excl=['missing_sibling_address'] review=['missing_sibling_address']

## 4. [retrieval_core/address_namespace] `hnq20k-v4-add-01778`
- **query**: `trường trung học cơ sở gia lâm (trường chính) 25 phố nguyễn khiêm ích`
- **clean_query**: `trường trung học cơ sở gia lâm (trường chính) 25 phố nguyễn khiêm ích`
- **POI**: Trường Trung học cơ sở Gia Lâm (Trường chính) | 25 Phố Nguyễn Khiêm Ích | amenity=school
- **split**: dev_synthetic | surface=committed_text | gen=grounded_field_composition
- **compat**: 1 | train_elig=False | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False
- **flags**: main_excl=[] train_excl=['not_train_split'] review=[]

## 5. [retrieval_core/adjacent_transpose] `hnq20k-v4-add-05299`
- **query**: `ha dang amrt`
- **clean_query**: `ha dang mart`
- **POI**: Hà Đăng Mart | Phố Thành Thái Dịch Vọng | shop=supermarket
- **split**: dev_synthetic | surface=committed_text | gen=controlled_typing_variant
- **compat**: 2 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **mutation**: ha dang mart → ha dang amrt ops=['accent_folding', 'adjacent_transpose'] ime=None
- **flags**: main_excl=['multiple_known_compatible'] train_excl=['multiple_known_compatible', 'not_train_split'] review=['multiple_known_compatible']

## 6. [retrieval_core/character_deletion] `hnq20k-v4-add-04557`
- **query**: `484 duong ang`
- **clean_query**: `484 duong lang`
- **POI**: 484 Đường Láng | 484 Đường Láng | address=
- **split**: train | surface=committed_text | gen=controlled_typing_variant
- **compat**: 1 | train_elig=True | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False
- **mutation**: None → None ops=['accent_folding', 'character_deletion'] ime=None

## 7. [retrieval_core/clean_name] `hnq10k-v3-06251`
- **query**: `quán trà đá`
- **clean_query**: `Quán trà đá`
- **POI**: Quán trà đá |  | amenity=drinking_water
- **split**: train | surface=committed_text | gen=grounded_composition
- **compat**: 2 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois'] train_excl=['multiple_compatible_pois'] review=['multiple_compatible_pois']

## 8. [retrieval_core/editorial_paraphrase] `hnq10k-v3-00066`
- **query**: `aeon maxvalu vũ tông phan`
- **clean_query**: `aeon maxvalu vũ tông phan`
- **POI**: AEON MaxValu | 349 Phố Vũ Tông Phan Khương Đình | shop=supermarket
- **split**: test_synthetic | surface=committed_text | gen=codex_authored_per_poi
- **compat**: 9 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois', 'cross_split_compatible'] train_excl=['not_train_split', 'multiple_compatible_pois', 'cross_split_compatible', 'editorial_paraphrase'] review=['multiple_compatible_pois', 'editorial_paraphrase', 'cross_split_compatible']

## 9. [retrieval_core/grounded_search_phrase] `hnq20k-v4-add-02974`
- **query**: `cho mình đến đội thanh tra giao thông vận tải huyện mê linh`
- **clean_query**: `cho mình đến đội thanh tra giao thông vận tải huyện mê linh`
- **POI**: Đội Thanh tra Giao thông vận tải huyện Mê Linh |  | office=government
- **split**: architecture_holdout | surface=committed_text | gen=codex_authored_pattern_instantiation
- **compat**: 1 | train_elig=False | main_metric=True
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=[] train_excl=['synthetic_language_rule', 'not_train_split'] review=['synthetic_language_rule']

## 10. [retrieval_core/keyboard_neighbor] `hnq20k-v4-add-06060`
- **query**: `tiy nhien`
- **clean_query**: `tuy nhien`
- **POI**: Túy nhiên | Đường Tỉnh 419 | shop=convenience
- **split**: train | surface=committed_text | gen=controlled_typing_variant
- **compat**: 1 | train_elig=True | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False
- **mutation**: None → None ops=['accent_folding', 'keyboard_neighbor'] ime=None

## 11. [retrieval_core/mixed_two_errors] `hnq20k-v4-add-07373`
- **query**: `qan via`
- **clean_query**: `quan bia`
- **POI**: Quán bia | Phố Nguyễn Đình Tứ Cổ Nhuế | amenity=restaurant
- **split**: architecture_holdout | surface=committed_text | gen=controlled_typing_variant
- **compat**: 32 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **mutation**: None → None ops=['accent_folding', 'character_deletion', 'keyboard_neighbor'] ime=None
- **flags**: main_excl=['multiple_known_compatible', 'cross_split_compatible'] train_excl=['multiple_known_compatible', 'cross_split_compatible', 'not_train_split'] review=['multiple_known_compatible']

## 12. [retrieval_core/name_address] `hnq10k-v3-06023`
- **query**: `almaz hà nội hoa lan`
- **clean_query**: `Almaz Hà Nội Hoa Lan`
- **POI**: Almaz Hà Nội | Hoa Lan Vinhomes Riverside | amenity=conference_centre
- **split**: train | surface=committed_text | gen=grounded_composition
- **compat**: 1 | train_elig=True | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False

## 13. [retrieval_core/name_street] `hnq10k-v3-03975`
- **query**: `63 ngõ 61 ngõ 61`
- **clean_query**: `63 Ngõ 61`
- **POI**: 63 Ngõ 61 | 63 Ngõ 61 | address=
- **split**: train | surface=committed_text | gen=grounded_composition
- **compat**: 1 | train_elig=True | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False

## 14. [retrieval_core/no_diacritics] `hnq20k-v4-add-03437`
- **query**: `31 ngo 335 an duong vuong`
- **clean_query**: `31 ngõ 335 an dương vương`
- **POI**: 31 Ngõ 335 An Dương Vương | 31 Ngõ 335 An Dương Vương | address=
- **split**: architecture_holdout | surface=committed_text | gen=controlled_typing_variant
- **compat**: 1 | train_elig=False | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False
- **mutation**: None → None ops=['accent_folding'] ime=None
- **flags**: main_excl=[] train_excl=['not_train_split'] review=[]

## 15. [retrieval_core/partial_diacritics] `hnq20k-v4-add-03729`
- **query**: `tây hô jsc`
- **clean_query**: `tây hồ jsc`
- **POI**: Tây Hồ JSC | 487 Đường Hoàng Quốc Việt Phường Cổ Nhuế 1 | office=company
- **split**: train | surface=committed_text | gen=controlled_typing_variant
- **compat**: 1 | train_elig=True | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False
- **mutation**: None → None ops=['single_tone_removed'] ime=None

## 16. [retrieval_core/repeated_character] `hnq20k-v4-add-05673`
- **query**: `72 ngo 328 le ttrong tan`
- **clean_query**: `72 ngo 328 le trong tan`
- **POI**: 72 Ngõ 328 Lê Trọng Tấn | 72 Ngõ 328 Lê Trọng Tấn | address=
- **split**: train | surface=committed_text | gen=controlled_typing_variant
- **compat**: 1 | train_elig=True | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False
- **mutation**: None → None ops=['accent_folding', 'repeated_character'] ime=None

## 17. [retrieval_core/search_phrase] `hnq10k-v3-09375`
- **query**: `tìm công an xã nam hồng`
- **clean_query**: `Công an xã Nam Hồng`
- **POI**: Công an xã Nam Hồng |  | amenity=police
- **split**: train | surface=committed_text | gen=grounded_composition
- **compat**: 1 | train_elig=True | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False

## 18. [retrieval_core/slash_alley_address] `hnq20k-v4-add-00721`
- **query**: `113 ngõ 192 lê trọng tấn`
- **clean_query**: `113 ngõ 192 lê trọng tấn`
- **POI**: 113 Ngõ 192 Lê Trọng Tấn | 113 Ngõ 192 Lê Trọng Tấn | address=
- **split**: train | surface=committed_text | gen=grounded_field_composition
- **compat**: 1 | train_elig=True | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False

## 19. [retrieval_core/source_alias_or_abbreviation] `hnq20k-v4-add-01250`
- **query**: `long bien station phố gầm cầu`
- **clean_query**: `long bien station phố gầm cầu`
- **POI**: Ga Long Biên | 1 Phố Gầm Cầu | building=train_station
- **split**: train | surface=committed_text | gen=source_alias
- **compat**: 1 | train_elig=False | main_metric=True
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=[] train_excl=['synthetic_language_rule'] review=['synthetic_language_rule']

## 20. [retrieval_core/space_edit] `hnq20k-v4-add-06602`
- **query**: `bun cha - phoga ta`
- **clean_query**: `bun cha - pho ga ta`
- **POI**: Bún chả - Phở Gà Ta |  | amenity=restaurant
- **split**: train | surface=committed_text | gen=controlled_typing_variant
- **compat**: 1 | train_elig=True | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False
- **mutation**: None → None ops=['accent_folding', 'space_edit'] ime=None

## 21. [retrieval_core/unit_with_namespace] `hnq10k-v3-03289`
- **query**: `g 191 phố minh khai`
- **clean_query**: `G 191 Phố Minh Khai`
- **POI**: 191 Phố Minh Khai | 191 Phố Minh Khai | address=
- **split**: train | surface=committed_text | gen=grounded_composition
- **compat**: 1 | train_elig=True | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False

## 22. [retrieval_core/wrong_tone] `hnq20k-v4-add-04348`
- **query**: `trám biến áp triệu việt vương 1`
- **clean_query**: `trạm biến áp triệu việt vương 1`
- **POI**: Trạm biến áp Triệu Việt Vương 1 |  | building=yes
- **split**: dev_synthetic | surface=committed_text | gen=controlled_typing_variant
- **compat**: 1 | train_elig=False | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False
- **mutation**: None → None ops=['single_tone_replaced'] ime=None
- **flags**: main_excl=[] train_excl=['not_train_split'] review=[]

## 23. [retrieval_core/abbreviation] `hnq10k-v3-04279`
- **query**: `bv nhi`
- **clean_query**: `Bệnh Viện Nhi`
- **POI**: Bệnh Viện Nhi |  | aeroway=helipad
- **split**: train | surface=committed_text | gen=grounded_composition
- **compat**: 4 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois'] train_excl=['multiple_compatible_pois'] review=['multiple_compatible_pois']

## 24. [retrieval_core/address_exact] `hnq10k-v3-01656`
- **query**: `26 ánh dương 10`
- **clean_query**: `26 Ánh Dương 10`
- **POI**: 26 Ánh Dương 10 | 26 Ánh Dương 10 Phân khu Cát Tường | address=
- **split**: train | surface=committed_text | gen=grounded_composition
- **compat**: 1 | train_elig=True | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False

## 25. [retrieval_core/address_first] `hnq10k-v3-00950`
- **query**: `12b7 phố phạm ngọc thạch hanosimex`
- **clean_query**: `Hanosimex 12B7 Phố Phạm Ngọc Thạch`
- **POI**: Hanosimex | 12B7 Phố Phạm Ngọc Thạch Kim Liên | shop=clothes
- **split**: test_synthetic | surface=committed_text | gen=grounded_composition
- **compat**: 1 | train_elig=False | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False
- **flags**: main_excl=[] train_excl=['not_train_split'] review=[]

## 26. [retrieval_core/address_namespace] `hnq20k-v4-add-01755`
- **query**: `khách sạn novotel suites 5 phố duy tân`
- **clean_query**: `khách sạn novotel suites 5 phố duy tân`
- **POI**: Khách Sạn Novotel Suites | 5 Phố Duy Tân Dịch Vọng Hậu | tourism=hotel
- **split**: dev_synthetic | surface=committed_text | gen=grounded_field_composition
- **compat**: 1 | train_elig=False | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False
- **flags**: main_excl=[] train_excl=['not_train_split'] review=[]

## 27. [retrieval_core/adjacent_transpose] `hnq10k-v3-08680`
- **query**: `nha tho giao xu ke gnhe`
- **clean_query**: `Nhà thờ Giáo xứ Kẻ Nghệ`
- **POI**: Nhà thờ Giáo xứ Kẻ Nghệ |  | amenity=place_of_worship
- **split**: train | surface=committed_text | gen=controlled_typing_rule
- **compat**: 1 | train_elig=True | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False
- **mutation**: nha tho giao xu ke nghe → nha tho giao xu ke gnhe ops=None ime=None

## 28. [retrieval_core/character_deletion] `hnq20k-v4-add-04857`
- **query**: `15 dung 72`
- **clean_query**: `15 duong 72`
- **POI**: 15 Đường 72 | 15 Đường 72 | address=
- **split**: architecture_holdout | surface=committed_text | gen=controlled_typing_variant
- **compat**: 2 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **mutation**: None → None ops=['accent_folding', 'character_deletion'] ime=None
- **flags**: main_excl=['multiple_known_compatible'] train_excl=['multiple_known_compatible', 'not_train_split'] review=['multiple_known_compatible']

## 29. [retrieval_core/clean_name] `hnq10k-v3-07846`
- **query**: `cn vision`
- **clean_query**: `CN Vision`
- **POI**: CN Vision | Phố Thọ Tháp | amenity=language_school
- **split**: dev_synthetic | surface=committed_text | gen=grounded_composition
- **compat**: 1 | train_elig=False | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False
- **flags**: main_excl=[] train_excl=['not_train_split'] review=[]

## 30. [retrieval_core/editorial_paraphrase] `hnq10k-v3-00186`
- **query**: `thcs sài đồng phân hiệu 1`
- **clean_query**: `thcs sài đồng phân hiệu 1`
- **POI**: Trường Trung học cơ sở Sài Đồng (Phân hiệu 1) | 11 Ngõ 557 đường Nguyễn Văn Linh | amenity=school
- **split**: train | surface=committed_text | gen=codex_authored_per_poi
- **compat**: 1 | train_elig=False | main_metric=True
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=[] train_excl=['editorial_paraphrase'] review=['editorial_paraphrase']

## 31. [retrieval_core/grounded_search_phrase] `hnq20k-v4-add-02811`
- **query**: `đến trạm y tế xã yên viên`
- **clean_query**: `đến trạm y tế xã yên viên`
- **POI**: Trạm Y tế xã Yên Viên |  | amenity=clinic
- **split**: dev_synthetic | surface=committed_text | gen=codex_authored_pattern_instantiation
- **compat**: 1 | train_elig=False | main_metric=True
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=[] train_excl=['synthetic_language_rule', 'not_train_split'] review=['synthetic_language_rule']

## 32. [retrieval_core/keyboard_neighbor] `hnq20k-v4-add-06176`
- **query**: `trien lam tranh dan fian viet nam`
- **clean_query**: `trien lam tranh dan gian viet nam`
- **POI**: Triển lãm Tranh dân gian Việt Nam |  | tourism=gallery
- **split**: train | surface=committed_text | gen=controlled_typing_variant
- **compat**: 1 | train_elig=True | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False
- **mutation**: None → None ops=['accent_folding', 'keyboard_neighbor'] ime=None

## 33. [retrieval_core/mixed_two_errors] `hnq20k-v4-add-07459`
- **query**: `6 po tau tra`
- **clean_query**: `6 pho tay tra`
- **POI**: 6 Phố Tây Trà | 6 Phố Tây Trà | address=
- **split**: architecture_holdout | surface=committed_text | gen=controlled_typing_variant
- **compat**: 1 | train_elig=False | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False
- **mutation**: None → None ops=['accent_folding', 'character_deletion', 'keyboard_neighbor'] ime=None
- **flags**: main_excl=[] train_excl=['not_train_split'] review=[]

## 34. [retrieval_core/name_address] `hnq10k-v3-03664`
- **query**: `chung cư an lạc - phùng khoang ngõ 67 phùng khoang`
- **clean_query**: `Chung cư An Lạc - Phùng Khoang Ngõ 67 Phùng Khoang`
- **POI**: Chung cư An Lạc - Phùng Khoang | Ngõ 67 Phùng Khoang | building=apartments
- **split**: train | surface=committed_text | gen=grounded_composition
- **compat**: 1 | train_elig=True | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False

## 35. [retrieval_core/name_street] `hnq10k-v3-04025`
- **query**: `9 ngõ 423 an dương vương ngõ 423 an dương vương`
- **clean_query**: `9 Ngõ 423 An Dương Vương`
- **POI**: 9 Ngõ 423 An Dương Vương | 9 Ngõ 423 An Dương Vương | address=
- **split**: train | surface=committed_text | gen=grounded_composition
- **compat**: 2 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois'] train_excl=['multiple_compatible_pois'] review=['multiple_compatible_pois']

## 36. [retrieval_core/no_diacritics] `hnq20k-v4-add-03320`
- **query**: `nha hang san ho do`
- **clean_query**: `nhà hàng san hô đỏ`
- **POI**: Nhà hàng San Hô Đỏ | 135 Phố Lương Định Của Kim Liên | amenity=restaurant
- **split**: dev_synthetic | surface=committed_text | gen=controlled_typing_variant
- **compat**: 1 | train_elig=False | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False
- **mutation**: None → None ops=['accent_folding'] ime=None
- **flags**: main_excl=[] train_excl=['not_train_split'] review=[]

## 37. [retrieval_core/partial_diacritics] `hnq20k-v4-add-03573`
- **query**: `đại sư quán nigeria`
- **clean_query**: `đại sứ quán nigeria`
- **POI**: Đại sứ quán Nigeria | Phố Vạn Bảo | office=diplomatic
- **split**: train | surface=committed_text | gen=controlled_typing_variant
- **compat**: 1 | train_elig=True | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False
- **mutation**: None → None ops=['single_tone_removed'] ime=None

## 38. [retrieval_core/repeated_character] `hnq20k-v4-add-05938`
- **query**: `dai su quan ausstralia`
- **clean_query**: `dai su quan australia`
- **POI**: Đại sứ quán Australia | 8 Phố Đào Tấn Cống Vị | office=diplomatic
- **split**: architecture_holdout | surface=committed_text | gen=controlled_typing_variant
- **compat**: 1 | train_elig=False | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False
- **mutation**: None → None ops=['accent_folding', 'repeated_character'] ime=None
- **flags**: main_excl=[] train_excl=['not_train_split'] review=[]

## 39. [retrieval_core/search_phrase] `hnq10k-v3-01195`
- **query**: `địa chỉ eab`
- **clean_query**: `Eab`
- **POI**: Eab |  | amenity=atm
- **split**: dev_synthetic | surface=committed_text | gen=grounded_composition
- **compat**: 24 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois'] train_excl=['not_train_split', 'multiple_compatible_pois'] review=['multiple_compatible_pois']

## 40. [retrieval_core/slash_alley_address] `hnq20k-v4-add-00523`
- **query**: `sn 14, tổ 13 hẻm 640/20/12 nguyễn văn cừ`
- **clean_query**: `sn 14, tổ 13 hẻm 640/20/12 nguyễn văn cừ`
- **POI**: sn 14, tổ 13 Hẻm 640/20/12 Nguyễn Văn Cừ | sn 14, tổ 13 Hẻm 640/20/12 Nguyễn Văn Cừ Gia Thụy | address=
- **split**: train | surface=committed_text | gen=grounded_field_composition
- **compat**: 1 | train_elig=True | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False

## 41. [retrieval_core/source_alias_or_abbreviation] `hnq20k-v4-add-01101`
- **query**: `trường thcs ba trại`
- **clean_query**: `trường thcs ba trại`
- **POI**: Trường Trung học cơ sở Ba Trại |  | building=school
- **split**: train | surface=committed_text | gen=auditable_abbreviation_rule
- **compat**: 2 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_known_compatible'] train_excl=['multiple_known_compatible', 'synthetic_language_rule'] review=['multiple_known_compatible', 'synthetic_language_rule']

## 42. [retrieval_core/space_edit] `hnq20k-v4-add-06678`
- **query**: `theqk`
- **clean_query**: `the qk`
- **POI**: The QK |  | amenity=bar
- **split**: train | surface=committed_text | gen=controlled_typing_variant
- **compat**: 1 | train_elig=True | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False
- **mutation**: None → None ops=['accent_folding', 'space_edit'] ime=None

## 43. [retrieval_core/unit_with_namespace] `hnq10k-v3-03429`
- **query**: `a 7 phố hàm long`
- **clean_query**: `A 7 Phố Hàm Long`
- **POI**: 7 Phố Hàm Long | 7 Phố Hàm Long | address=
- **split**: train | surface=committed_text | gen=grounded_composition
- **compat**: 1 | train_elig=True | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False

## 44. [retrieval_core/wrong_tone] `hnq10k-v3-09413`
- **query**: `công an xá nội bài`
- **clean_query**: `Công an xã Nội Bài`
- **POI**: Công an xã Nội Bài |  | amenity=police
- **split**: train | surface=committed_text | gen=controlled_typing_rule
- **compat**: 4 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois'] train_excl=['multiple_compatible_pois'] review=['multiple_compatible_pois']

## 45. [retrieval_core/abbreviation] `hnq10k-v3-00048`
- **query**: `bv phụ sản trung ương cơ sở 2 đại lộ thăng long`
- **clean_query**: `Bệnh viện Phụ sản Trung ương cơ sở 2 Đại lộ Thăng Long`
- **POI**: Bệnh viện Phụ sản Trung ương cơ sở 2 | Đại lộ Thăng Long Kiều Phú | amenity=hospital
- **split**: train | surface=committed_text | gen=grounded_composition
- **compat**: 1 | train_elig=True | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False

## 46. [retrieval_core/address_exact] `hnq10k-v3-03986`
- **query**: `25 ngách 321/28`
- **clean_query**: `25 Ngách 321/28`
- **POI**: 25 Ngách 321/28 | 25 Ngách 321/28 | address=
- **split**: test_synthetic | surface=committed_text | gen=grounded_composition
- **compat**: 1 | train_elig=False | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False
- **flags**: main_excl=[] train_excl=['not_train_split'] review=[]

## 47. [retrieval_core/address_first] `hnq10k-v3-06650`
- **query**: `36 đường nguyễn phong sắc đội chữa cháy và cứu nạn cứu hộ khu vực số 11`
- **clean_query**: `Đội Chữa cháy và Cứu nạn cứu hộ khu vực số 11 36 Đường Nguyễn Phong Sắc`
- **POI**: Đội Chữa cháy và Cứu nạn cứu hộ khu vực số 11 | 36 Đường Nguyễn Phong Sắc Nghĩa Tân | amenity=fire_station
- **split**: test_synthetic | surface=committed_text | gen=grounded_composition
- **compat**: 1 | train_elig=False | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False
- **flags**: main_excl=[] train_excl=['not_train_split'] review=[]

## 48. [retrieval_core/address_namespace] `hnq20k-v4-add-01828`
- **query**: `cà phê 74 74 đường hoàng hoa thám`
- **clean_query**: `cà phê 74 74 đường hoàng hoa thám`
- **POI**: Cà Phê 74 | 74 Đường Hoàng Hoa Thám | amenity=cafe
- **split**: dev_synthetic | surface=committed_text | gen=grounded_field_composition
- **compat**: 1 | train_elig=False | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False
- **flags**: main_excl=[] train_excl=['not_train_split'] review=[]

## 49. [retrieval_core/adjacent_transpose] `hnq20k-v4-add-05282`
- **query**: `dien alnh ha noi`
- **clean_query**: `dien lanh ha noi`
- **POI**: Điện lạnh Hà Nội |  | shop=electronics
- **split**: dev_synthetic | surface=committed_text | gen=controlled_typing_variant
- **compat**: 4 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **mutation**: dien lanh ha noi → dien alnh ha noi ops=['accent_folding', 'adjacent_transpose'] ime=None
- **flags**: main_excl=['multiple_known_compatible', 'cross_split_compatible'] train_excl=['multiple_known_compatible', 'cross_split_compatible', 'not_train_split'] review=['multiple_known_compatible']

## 50. [retrieval_core/character_deletion] `hnq20k-v4-add-04771`
- **query**: `hidde gem`
- **clean_query**: `hidden gem`
- **POI**: Hidden Gem | Phố Hàng Tre | amenity=cafe
- **split**: dev_synthetic | surface=committed_text | gen=controlled_typing_variant
- **compat**: 2 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **mutation**: None → None ops=['accent_folding', 'character_deletion'] ime=None
- **flags**: main_excl=['multiple_known_compatible', 'cross_split_compatible'] train_excl=['multiple_known_compatible', 'cross_split_compatible', 'not_train_split'] review=['multiple_known_compatible']

## 51. [retrieval_core/clean_name] `hnq10k-v3-06426`
- **query**: `bánh khúc hoàng thường`
- **clean_query**: `Bánh Khúc Hoàng Thường`
- **POI**: Bánh Khúc Hoàng Thường | 123 Ngõ 262 Đường Đa Tôn Bát Tràng | amenity=fast_food
- **split**: train | surface=committed_text | gen=grounded_composition
- **compat**: 1 | train_elig=True | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False

## 52. [retrieval_core/editorial_paraphrase] `hnq10k-v3-00206`
- **query**: `tttm chợ mơ`
- **clean_query**: `tttm chợ mơ`
- **POI**: Trung tâm thương mại Chợ Mơ | 459C Bạch Mai Trương Định | shop=mall
- **split**: train | surface=committed_text | gen=codex_authored_per_poi
- **compat**: 1 | train_elig=False | main_metric=True
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=[] train_excl=['editorial_paraphrase'] review=['editorial_paraphrase']

## 53. [retrieval_core/grounded_search_phrase] `hnq20k-v4-add-02904`
- **query**: `cho tôi tới võ đường hanoi kendo`
- **clean_query**: `cho tôi tới võ đường hanoi kendo`
- **POI**: Võ Đường Hanoi Kendo |  | club=sport
- **split**: architecture_holdout | surface=committed_text | gen=codex_authored_pattern_instantiation
- **compat**: 1 | train_elig=False | main_metric=True
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=[] train_excl=['synthetic_language_rule', 'not_train_split'] review=['synthetic_language_rule']

## 54. [retrieval_core/keyboard_neighbor] `hnq20k-v4-add-06133`
- **query**: `elipaport`
- **clean_query**: `elipsport`
- **POI**: Elipsport |  | shop=sports
- **split**: train | surface=committed_text | gen=controlled_typing_variant
- **compat**: 1 | train_elig=True | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False
- **mutation**: None → None ops=['accent_folding', 'keyboard_neighbor'] ime=None

## 55. [retrieval_core/mixed_two_errors] `hnq20k-v4-add-07165`
- **query**: `nhs hang cosins`
- **clean_query**: `nha hang cousins`
- **POI**: Nhà Hàng Cousins |  | amenity=restaurant
- **split**: train | surface=committed_text | gen=controlled_typing_variant
- **compat**: 1 | train_elig=True | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False
- **mutation**: None → None ops=['accent_folding', 'character_deletion', 'keyboard_neighbor'] ime=None

## 56. [retrieval_core/name_address] `hnq10k-v3-04979`
- **query**: `cà phê first phạm văn đồng`
- **clean_query**: `Cà Phê First Phạm Văn Đồng`
- **POI**: Cà Phê First | Phạm Văn Đồng Cổ Nhuế 2 | amenity=cafe
- **split**: train | surface=committed_text | gen=grounded_composition
- **compat**: 1 | train_elig=True | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False

## 57. [retrieval_core/name_street] `hnq10k-v3-04175`
- **query**: `khu ươm tơ đường tỉnh 422b đường tỉnh 422b`
- **clean_query**: `Khu Ươm Tơ Đường tỉnh 422B`
- **POI**: Khu Ươm Tơ Đường tỉnh 422B | Khu Ươm Tơ Đường tỉnh 422B Sơn Đồng | address=
- **split**: train | surface=committed_text | gen=grounded_composition
- **compat**: 1 | train_elig=True | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False

## 58. [retrieval_core/no_diacritics] `hnq10k-v3-03424`
- **query**: `2 ngo 18 ngo quyen`
- **clean_query**: `2 Ngõ 18 Ngô Quyền`
- **POI**: 2 Ngõ 18 Ngô Quyền | 2 Ngõ 18 Ngô Quyền | address=
- **split**: train | surface=committed_text | gen=controlled_typing_rule
- **compat**: 9 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois'] train_excl=['multiple_compatible_pois'] review=['multiple_compatible_pois']

## 59. [retrieval_core/partial_diacritics] `hnq20k-v4-add-03833`
- **query**: `hai đăng 8 - bbq07`
- **clean_query**: `hải đăng 8 - bbq07`
- **POI**: Hải Đăng 8 - BBQ07 |  | amenity=bbq
- **split**: dev_synthetic | surface=committed_text | gen=controlled_typing_variant
- **compat**: 1 | train_elig=False | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False
- **mutation**: None → None ops=['single_tone_removed'] ime=None
- **flags**: main_excl=[] train_excl=['not_train_split'] review=[]

## 60. [retrieval_core/repeated_character] `hnq20k-v4-add-05724`
- **query**: `cing hu tanng`
- **clean_query**: `cing hu tang`
- **POI**: Cing Hu Tang | Phố Phạm Ngọc Thạch | amenity=cafe
- **split**: train | surface=committed_text | gen=controlled_typing_variant
- **compat**: 1 | train_elig=True | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False
- **mutation**: None → None ops=['accent_folding', 'repeated_character'] ime=None

## 61. [retrieval_core/search_phrase] `hnq10k-v3-09620`
- **query**: `địa chỉ vietnam post`
- **clean_query**: `Vietnam Post`
- **POI**: Vietnam Post |  | amenity=post_office
- **split**: train | surface=committed_text | gen=grounded_composition
- **compat**: 9 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois'] train_excl=['multiple_compatible_pois'] review=['multiple_compatible_pois']

## 62. [retrieval_core/slash_alley_address] `hnq20k-v4-add-00796`
- **query**: `nhóm trẻ nụ cười bé thơ 6 ngõ 55 dịch vọng`
- **clean_query**: `nhóm trẻ nụ cười bé thơ 6 ngõ 55 dịch vọng`
- **POI**: Nhóm trẻ Nụ Cười Bé Thơ | 6 Ngõ 55 Dịch Vọng | amenity=kindergarten
- **split**: dev_synthetic | surface=committed_text | gen=grounded_field_composition
- **compat**: 1 | train_elig=False | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False
- **flags**: main_excl=[] train_excl=['not_train_split'] review=[]

## 63. [retrieval_core/source_alias_or_abbreviation] `hnq20k-v4-add-01100`
- **query**: `trường tiểu học times school khai sơn`
- **clean_query**: `trường tiểu học times school khai sơn`
- **POI**: Times School Khai Son Elementary School |  | building=school
- **split**: train | surface=committed_text | gen=source_alias
- **compat**: 1 | train_elig=False | main_metric=True
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=[] train_excl=['synthetic_language_rule'] review=['synthetic_language_rule']

## 64. [retrieval_core/space_edit] `hnq20k-v4-add-06755`
- **query**: `truong tieu hocngoc ha (phan hieu 2)`
- **clean_query**: `truong tieu hoc ngoc ha (phan hieu 2)`
- **POI**: Trường Tiểu học Ngọc Hà (phân hiệu 2) | Ngõ 194 Đội Cấn | amenity=school
- **split**: dev_synthetic | surface=committed_text | gen=controlled_typing_variant
- **compat**: 1 | train_elig=False | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False
- **mutation**: None → None ops=['accent_folding', 'space_edit'] ime=None
- **flags**: main_excl=[] train_excl=['not_train_split'] review=[]

## 65. [retrieval_core/unit_with_namespace] `hnq10k-v3-03394`
- **query**: `13 đầm bầu mom baby b14 phố phạm ngọc thạch`
- **clean_query**: `13 Đầm bầu Mom Baby B14 Phố Phạm Ngọc Thạch`
- **POI**: Đầm bầu Mom Baby | Phố Phạm Ngọc Thạch | shop=clothes
- **split**: train | surface=committed_text | gen=grounded_composition
- **compat**: 1 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['missing_sibling_address'] train_excl=['missing_sibling_address'] review=['missing_sibling_address']

## 66. [retrieval_core/wrong_tone] `hnq20k-v4-add-04382`
- **query**: `58 phộ đại linh`
- **clean_query**: `58 phố đại linh`
- **POI**: 58 Phố Đại Linh | 58 Phố Đại Linh | address=
- **split**: architecture_holdout | surface=committed_text | gen=controlled_typing_variant
- **compat**: 1 | train_elig=False | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False
- **mutation**: None → None ops=['single_tone_replaced'] ime=None
- **flags**: main_excl=[] train_excl=['not_train_split'] review=[]

## 67. [retrieval_core/abbreviation] `hnq10k-v3-07119`
- **query**: `bv bắc thăng long`
- **clean_query**: `Bệnh viện Bắc Thăng Long`
- **POI**: Bệnh viện Bắc Thăng Long |  | amenity=hospital
- **split**: train | surface=committed_text | gen=grounded_composition
- **compat**: 1 | train_elig=True | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False

## 68. [retrieval_core/address_exact] `hnq10k-v3-02881`
- **query**: `19 ngõ 180 tây mỗ`
- **clean_query**: `19 Ngõ 180 Tây Mỗ`
- **POI**: 19 Ngõ 180 Tây Mỗ | 19 Ngõ 180 Tây Mỗ | address=
- **split**: train | surface=committed_text | gen=grounded_composition
- **compat**: 1 | train_elig=True | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False

## 69. [retrieval_core/address_first] `hnq10k-v3-00575`
- **query**: `643 đường phạm văn đồng bmw`
- **clean_query**: `BMW 643 Đường Phạm Văn Đồng`
- **POI**: BMW | 643 Đường Phạm Văn Đồng Phường Cổ Nhuế 1 | shop=car
- **split**: train | surface=committed_text | gen=grounded_composition
- **compat**: 1 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['missing_sibling_address'] train_excl=['missing_sibling_address'] review=['missing_sibling_address']

## 70. [retrieval_core/address_namespace] `hnq20k-v4-add-01722`
- **query**: `78 đường thiên nga`
- **clean_query**: `78 đường thiên nga`
- **POI**: 78 Đường Thiên Nga | 78 Đường Thiên Nga Phân khu Tinh Hoa, Global Gate | address=
- **split**: train | surface=committed_text | gen=grounded_field_composition
- **compat**: 1 | train_elig=True | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False

## 71. [retrieval_core/adjacent_transpose] `hnq10k-v3-02249`
- **query**: `18 cua vong`
- **clean_query**: `18 Cầu Vồng`
- **POI**: 18 Cầu Vồng | 18 Cầu Vồng | shop=copyshop
- **split**: train | surface=committed_text | gen=controlled_typing_rule
- **compat**: 1 | train_elig=True | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False
- **mutation**: 18 cau vong → 18 cua vong ops=None ime=None

## 72. [retrieval_core/character_deletion] `hnq20k-v4-add-04833`
- **query**: `15 ch ca`
- **clean_query**: `15 cha ca`
- **POI**: 15 Chả Cá | 15 Chả Cá | shop=bakery
- **split**: dev_synthetic | surface=committed_text | gen=controlled_typing_variant
- **compat**: 1 | train_elig=False | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False
- **mutation**: None → None ops=['accent_folding', 'character_deletion'] ime=None
- **flags**: main_excl=[] train_excl=['not_train_split'] review=[]

## 73. [retrieval_core/clean_name] `hnq10k-v3-04276`
- **query**: `bệnh viện nhi`
- **clean_query**: `Bệnh Viện Nhi`
- **POI**: Bệnh Viện Nhi |  | aeroway=helipad
- **split**: train | surface=committed_text | gen=grounded_composition
- **compat**: 4 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois'] train_excl=['multiple_compatible_pois'] review=['multiple_compatible_pois']

## 74. [retrieval_core/editorial_paraphrase] `hnq10k-v3-00111`
- **query**: `tràng tiền plaza`
- **clean_query**: `tràng tiền plaza`
- **POI**: Tràng Tiền Plaza | 24 Phố Hai Bà Trưng Tràng Tiền | shop=mall
- **split**: train | surface=committed_text | gen=codex_authored_per_poi
- **compat**: 2 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois'] train_excl=['multiple_compatible_pois', 'editorial_paraphrase'] review=['multiple_compatible_pois', 'editorial_paraphrase']

## 75. [retrieval_core/grounded_search_phrase] `hnq20k-v4-add-02805`
- **query**: `địa chỉ trạm sạc fast+`
- **clean_query**: `địa chỉ trạm sạc fast+`
- **POI**: Trạm sạc Fast+ |  | amenity=charging_station
- **split**: dev_synthetic | surface=committed_text | gen=codex_authored_pattern_instantiation
- **compat**: 1 | train_elig=False | main_metric=True
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=[] train_excl=['synthetic_language_rule', 'not_train_split'] review=['synthetic_language_rule']

## 76. [retrieval_core/keyboard_neighbor] `hnq20k-v4-add-06447`
- **query**: `ic lan beo hai phong`
- **clean_query**: `oc lan beo hai phong`
- **POI**: Ốc Lan Béo Hải Phòng | 2B Phố Đặng Văn Ngữ Phương Liên – Trung Tự | amenity=restaurant
- **split**: architecture_holdout | surface=committed_text | gen=controlled_typing_variant
- **compat**: 1 | train_elig=False | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False
- **mutation**: None → None ops=['accent_folding', 'keyboard_neighbor'] ime=None
- **flags**: main_excl=[] train_excl=['not_train_split'] review=[]

## 77. [retrieval_core/mixed_two_errors] `hnq20k-v4-add-07233`
- **query**: `kt atlaric`
- **clean_query**: `kt atlantic`
- **POI**: KT Atlantic | 171 Phố Xã Đàn Nam Đồng | shop=clothes
- **split**: train | surface=committed_text | gen=controlled_typing_variant
- **compat**: 1 | train_elig=True | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False
- **mutation**: None → None ops=['accent_folding', 'character_deletion', 'keyboard_neighbor'] ime=None

## 78. [retrieval_core/name_address] `hnq10k-v3-09604`
- **query**: `bưu cục đông anh 9 đường cao lỗ`
- **clean_query**: `Bưu cục Đông Anh 9 Đường Cao Lỗ`
- **POI**: Bưu cục Đông Anh | 9 Đường Cao Lỗ | amenity=post_office
- **split**: train | surface=committed_text | gen=grounded_composition
- **compat**: 1 | train_elig=True | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False

## 79. [retrieval_core/name_street] `hnq10k-v3-02750`
- **query**: `97 phố nhật chiêu phố nhật chiêu`
- **clean_query**: `97 Phố Nhật Chiêu`
- **POI**: 97 Phố Nhật Chiêu | 97 Phố Nhật Chiêu | address=
- **split**: train | surface=committed_text | gen=grounded_composition
- **compat**: 1 | train_elig=True | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False

## 80. [retrieval_core/no_diacritics] `hnq20k-v4-add-03471`
- **query**: `50 ngo 643 pham van dong`
- **clean_query**: `50 ngõ 643 phạm văn đồng`
- **POI**: 50 Ngõ 643 Phạm Văn Đồng | 50 Ngõ 643 Phạm Văn Đồng Phường Cổ Nhuế 1 | address=
- **split**: architecture_holdout | surface=committed_text | gen=controlled_typing_variant
- **compat**: 1 | train_elig=False | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False
- **mutation**: None → None ops=['accent_folding'] ime=None
- **flags**: main_excl=[] train_excl=['not_train_split'] review=[]

## 81. [retrieval_core/partial_diacritics] `hnq20k-v4-add-03741`
- **query**: `2 ngõ 133 nguyên phong sắc`
- **clean_query**: `2 ngõ 133 nguyễn phong sắc`
- **POI**: 2 Ngõ 133 Nguyễn Phong Sắc | 2 Ngõ 133 Nguyễn Phong Sắc Phường Nghĩa Tân | address=
- **split**: train | surface=committed_text | gen=controlled_typing_variant
- **compat**: 1 | train_elig=True | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False
- **mutation**: None → None ops=['single_tone_removed'] ime=None

## 82. [retrieval_core/repeated_character] `hnq20k-v4-add-05767`
- **query**: `truong tieu hoc va trung hoc co so myy duc`
- **clean_query**: `truong tieu hoc va trung hoc co so my duc`
- **POI**: Trường Tiểu học và Trung học cơ sở Mỹ Đức |  | amenity=school
- **split**: dev_synthetic | surface=committed_text | gen=controlled_typing_variant
- **compat**: 1 | train_elig=False | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False
- **mutation**: None → None ops=['accent_folding', 'repeated_character'] ime=None
- **flags**: main_excl=[] train_excl=['not_train_split'] review=[]

## 83. [retrieval_core/search_phrase] `hnq10k-v3-08320`
- **query**: `địa chỉ raptor karaoke`
- **clean_query**: `Raptor Karaoke`
- **POI**: Raptor Karaoke |  | amenity=nightclub
- **split**: train | surface=committed_text | gen=grounded_composition
- **compat**: 1 | train_elig=True | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False

## 84. [retrieval_core/slash_alley_address] `hnq20k-v4-add-00763`
- **query**: `đảng uỷ - hđnd - ubnd phường định công 1 ngõ 282 đường kim giang`
- **clean_query**: `đảng uỷ - hđnd - ubnd phường định công 1 ngõ 282 đường kim giang`
- **POI**: Đảng uỷ - HĐND - UBND phường Định Công | 1 Ngõ 282 Đường Kim Giang | amenity=townhall
- **split**: dev_synthetic | surface=committed_text | gen=grounded_field_composition
- **compat**: 1 | train_elig=False | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False
- **flags**: main_excl=[] train_excl=['not_train_split'] review=[]

## 85. [retrieval_core/source_alias_or_abbreviation] `hnq20k-v4-add-01311`
- **query**: `vaec phố hoa lư`
- **clean_query**: `vaec phố hoa lư`
- **POI**: Cục Văn hóa các dân tộc Việt Nam | 1 Phố Hoa Lư | office=government
- **split**: dev_synthetic | surface=committed_text | gen=source_alias
- **compat**: 1 | train_elig=False | main_metric=True
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=[] train_excl=['synthetic_language_rule', 'not_train_split'] review=['synthetic_language_rule']

## 86. [retrieval_core/space_edit] `hnq20k-v4-add-06915`
- **query**: `69 duongthanh`
- **clean_query**: `69 duong thanh`
- **POI**: 69 Đường Thành | 69 Đường Thành | address=
- **split**: architecture_holdout | surface=committed_text | gen=controlled_typing_variant
- **compat**: 2 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **mutation**: None → None ops=['accent_folding', 'space_edit'] ime=None
- **flags**: main_excl=['multiple_known_compatible', 'cross_split_compatible'] train_excl=['multiple_known_compatible', 'cross_split_compatible', 'not_train_split'] review=['multiple_known_compatible']

## 87. [retrieval_core/unit_with_namespace] `hnq10k-v3-03334`
- **query**: `a 32 ngách 27/9 tây mỗ`
- **clean_query**: `A 32 Ngách 27/9 Tây Mỗ`
- **POI**: 32 Ngách 27/9 Tây Mỗ | 32 Ngách 27/9 Tây Mỗ | address=
- **split**: dev_synthetic | surface=committed_text | gen=grounded_composition
- **compat**: 1 | train_elig=False | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False
- **flags**: main_excl=[] train_excl=['not_train_split'] review=[]

## 88. [retrieval_core/wrong_tone] `hnq20k-v4-add-04125`
- **query**: `học viển quốc phòng`
- **clean_query**: `học viện quốc phòng`
- **POI**: Học viện Quốc phòng | 93 Đường Hoàng Quốc Việt Phường Nghĩa Đô | amenity=college
- **split**: train | surface=committed_text | gen=controlled_typing_variant
- **compat**: 7 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **mutation**: None → None ops=['single_tone_replaced'] ime=None
- **flags**: main_excl=['multiple_known_compatible', 'cross_split_compatible'] train_excl=['multiple_known_compatible', 'cross_split_compatible'] review=['multiple_known_compatible']

## 89. [retrieval_core/abbreviation] `hnq10k-v3-00219`
- **query**: `bv k - cơ sở tân triều 30 đường cầu bươu`
- **clean_query**: `Bệnh viện K - Cơ sở Tân Triều 30 Đường Cầu Bươu`
- **POI**: Bệnh viện K - Cơ sở Tân Triều | 30 Đường Cầu Bươu Tân Triều | amenity=hospital
- **split**: train | surface=committed_text | gen=grounded_composition
- **compat**: 1 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['missing_sibling_address'] train_excl=['missing_sibling_address'] review=['missing_sibling_address']

## 90. [retrieval_core/address_exact] `hnq10k-v3-02131`
- **query**: `65 thời đại 7`
- **clean_query**: `65 Thời Đại 7`
- **POI**: 65 Thời Đại 7 | 65 Thời Đại 7 Phân khu Thịnh Vượng, Global Gate | address=
- **split**: train | surface=committed_text | gen=grounded_composition
- **compat**: 1 | train_elig=True | main_metric=True
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False

## 91. [autocomplete/prefix_4] `hnq10k-v3-00067`
- **query**: `aeon`
- **clean_query**: `AEON `
- **POI**: AEON MaxValu | 349 Phố Vũ Tông Phan Khương Đình | shop=supermarket
- **split**: test_synthetic | surface=committed_text | gen=controlled_typing_rule
- **compat**: 18 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois', 'track:autocomplete', 'cross_split_compatible'] train_excl=['not_train_split', 'multiple_compatible_pois', 'track:autocomplete', 'cross_split_compatible', 'unfinished_prefix'] review=['multiple_compatible_pois', 'unfinished_prefix', 'cross_split_compatible']

## 92. [autocomplete/prefix_5] `hnq10k-v3-03242`
- **query**: `1 thờ`
- **clean_query**: `1 Thờ`
- **POI**: 1 Thời Đại 1 | 1 Thời Đại 1 Phân khu Thịnh Vượng, Global Gate | address=
- **split**: train | surface=committed_text | gen=controlled_typing_rule
- **compat**: 8 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois', 'track:autocomplete'] train_excl=['multiple_compatible_pois', 'track:autocomplete', 'unfinished_prefix'] review=['multiple_compatible_pois', 'unfinished_prefix']

## 93. [autocomplete/prefix_6] `hnq10k-v3-06497`
- **query**: `popeye`
- **clean_query**: `Popeye`
- **POI**: Popeyes |  | amenity=fast_food
- **split**: train | surface=committed_text | gen=controlled_typing_rule
- **compat**: 4 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois', 'track:autocomplete'] train_excl=['multiple_compatible_pois', 'track:autocomplete', 'unfinished_prefix'] review=['multiple_compatible_pois', 'unfinished_prefix']

## 94. [autocomplete/prefix_7] `hnq10k-v3-02222`
- **query**: `68 nhật`
- **clean_query**: `68 Nhật `
- **POI**: 68 Nhật Nguyệt 5 | 68 Nhật Nguyệt 5 Phân khu Cát Tường | address=
- **split**: train | surface=committed_text | gen=controlled_typing_rule
- **compat**: 4 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois', 'track:autocomplete'] train_excl=['multiple_compatible_pois', 'track:autocomplete', 'unfinished_prefix'] review=['multiple_compatible_pois', 'unfinished_prefix']

## 95. [autocomplete/prefix_8] `hnq20k-v4-add-09921`
- **query**: `điểm trạ`
- **clean_query**: `điểm trạm y tế phương liệt`
- **POI**: Điểm Trạm Y tế Phương Liệt | 5 Phố Phương Liệt | amenity=clinic
- **split**: architecture_holdout | surface=committed_text | gen=controlled_prefix
- **compat**: 10 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **mutation**: None → None ops=['prefix_truncation'] ime=None
- **flags**: main_excl=['track_autocomplete', 'multiple_known_compatible', 'cross_split_compatible'] train_excl=['track_autocomplete', 'multiple_known_compatible', 'cross_split_compatible', 'ambiguous_or_partial_input', 'not_train_split'] review=['multiple_known_compatible', 'ambiguous_or_partial_input']

## 96. [autocomplete/prefix_4] `hnq10k-v3-03917`
- **query**: `zody`
- **clean_query**: `Zody `
- **POI**: Zody House | 1/53 Ton That Thiep | tourism=apartment
- **split**: train | surface=committed_text | gen=controlled_typing_rule
- **compat**: 1 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['track:autocomplete'] train_excl=['track:autocomplete', 'unfinished_prefix'] review=['unfinished_prefix']

## 97. [autocomplete/prefix_5] `hnq20k-v4-add-09051`
- **query**: `40 ng`
- **clean_query**: `40 ngõ 67 cầu cốc`
- **POI**: 40 Ngõ 67 Cầu Cốc | 40 Ngõ 67 Cầu Cốc | address=
- **split**: train | surface=committed_text | gen=controlled_prefix
- **compat**: 24 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **mutation**: None → None ops=['prefix_truncation'] ime=None
- **flags**: main_excl=['track_autocomplete', 'multiple_known_compatible', 'cross_split_compatible'] train_excl=['track_autocomplete', 'multiple_known_compatible', 'cross_split_compatible', 'ambiguous_or_partial_input'] review=['multiple_known_compatible', 'ambiguous_or_partial_input']

## 98. [autocomplete/prefix_6] `hnq10k-v3-00997`
- **query**: `popeye`
- **clean_query**: `Popeye`
- **POI**: Popeyes | 104 Phố Lê Thanh Nghị Bách Khoa | amenity=fast_food
- **split**: train | surface=committed_text | gen=controlled_typing_rule
- **compat**: 4 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois', 'track:autocomplete'] train_excl=['multiple_compatible_pois', 'track:autocomplete', 'unfinished_prefix'] review=['multiple_compatible_pois', 'unfinished_prefix']

## 99. [autocomplete/prefix_7] `hnq10k-v3-04272`
- **query**: `sân bay`
- **clean_query**: `Sân bay `
- **POI**: Sân bay Quốc tế Nội Bài | Phú Minh | aeroway=aerodrome
- **split**: train | surface=committed_text | gen=controlled_typing_rule
- **compat**: 5 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois', 'track:autocomplete'] train_excl=['multiple_compatible_pois', 'track:autocomplete', 'unfinished_prefix'] review=['multiple_compatible_pois', 'unfinished_prefix']

## 100. [autocomplete/prefix_8] `hnq20k-v4-add-09728`
- **query**: `đền thiê`
- **clean_query**: `đền thiên hoa`
- **POI**: Đền Thiên Hoa |  | amenity=place_of_worship
- **split**: train | surface=committed_text | gen=controlled_prefix
- **compat**: 3 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **mutation**: None → None ops=['prefix_truncation'] ime=None
- **flags**: main_excl=['track_autocomplete', 'multiple_known_compatible', 'cross_split_compatible'] train_excl=['track_autocomplete', 'multiple_known_compatible', 'cross_split_compatible', 'ambiguous_or_partial_input'] review=['multiple_known_compatible', 'ambiguous_or_partial_input']

## 101. [autocomplete/prefix_4] `hnq10k-v3-01347`
- **query**: `itim`
- **clean_query**: `ITIM`
- **POI**: ITIMS |  | building=university
- **split**: train | surface=committed_text | gen=controlled_typing_rule
- **compat**: 1 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['track:autocomplete'] train_excl=['track:autocomplete', 'unfinished_prefix'] review=['unfinished_prefix']

## 102. [autocomplete/prefix_5] `hnq20k-v4-add-09407`
- **query**: `sh03-`
- **clean_query**: `sh03-29 san hô 3`
- **POI**: SH03-29 San Hô 3 | SH03-29 San Hô 3 Đa Tốn | address=
- **split**: architecture_holdout | surface=committed_text | gen=controlled_prefix
- **compat**: 14 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **mutation**: None → None ops=['prefix_truncation'] ime=None
- **flags**: main_excl=['track_autocomplete', 'multiple_known_compatible'] train_excl=['track_autocomplete', 'multiple_known_compatible', 'ambiguous_or_partial_input', 'not_train_split'] review=['multiple_known_compatible', 'ambiguous_or_partial_input']

## 103. [autocomplete/prefix_6] `hnq10k-v3-04522`
- **query**: `seaban`
- **clean_query**: `SeABan`
- **POI**: SeABank |  | amenity=bank
- **split**: train | surface=committed_text | gen=controlled_typing_rule
- **compat**: 23 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois', 'track:autocomplete'] train_excl=['multiple_compatible_pois', 'track:autocomplete', 'unfinished_prefix'] review=['multiple_compatible_pois', 'unfinished_prefix']

## 104. [autocomplete/prefix_7] `hnq10k-v3-03597`
- **query**: `baber p`
- **clean_query**: `baber p`
- **POI**: baber pi | Ngách 27 Ngõ 176 Đức Thắng | shop=hairdresser
- **split**: train | surface=committed_text | gen=controlled_typing_rule
- **compat**: 2 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois', 'track:autocomplete'] train_excl=['multiple_compatible_pois', 'track:autocomplete', 'unfinished_prefix'] review=['multiple_compatible_pois', 'unfinished_prefix']

## 105. [autocomplete/prefix_8] `hnq10k-v3-04147`
- **query**: `8 phố lê`
- **clean_query**: `8 Phố Lê`
- **POI**: 8 Phố Lê Đại Hành | 8 Phố Lê Đại Hành | address=
- **split**: train | surface=committed_text | gen=controlled_typing_rule
- **compat**: 3 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois', 'track:autocomplete', 'cross_split_compatible'] train_excl=['multiple_compatible_pois', 'track:autocomplete', 'cross_split_compatible', 'unfinished_prefix'] review=['multiple_compatible_pois', 'unfinished_prefix', 'cross_split_compatible']

## 106. [autocomplete/prefix_4] `hnq10k-v3-07242`
- **query**: `l..a`
- **clean_query**: `L..A `
- **POI**: L..A Karaoke | 175 Trần Đăng Ninh Dịch Vọng | amenity=karaoke_box
- **split**: train | surface=committed_text | gen=controlled_typing_rule
- **compat**: 8 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois', 'track:autocomplete', 'cross_split_compatible'] train_excl=['multiple_compatible_pois', 'track:autocomplete', 'cross_split_compatible', 'unfinished_prefix'] review=['multiple_compatible_pois', 'unfinished_prefix', 'cross_split_compatible']

## 107. [autocomplete/prefix_5] `hnq10k-v3-02067`
- **query**: `459 n`
- **clean_query**: `459 N`
- **POI**: 459 Ngõ 192 Lê Trọng Tấn | 459 Ngõ 192 Lê Trọng Tấn | address=
- **split**: train | surface=committed_text | gen=controlled_typing_rule
- **compat**: 1 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['track:autocomplete'] train_excl=['track:autocomplete', 'unfinished_prefix'] review=['unfinished_prefix']

## 108. [autocomplete/prefix_6] `hnq10k-v3-08022`
- **query**: `chợ vồ`
- **clean_query**: `Chợ Vồ`
- **POI**: Chợ Vồi |  | amenity=marketplace
- **split**: train | surface=committed_text | gen=controlled_typing_rule
- **compat**: 1 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['track:autocomplete'] train_excl=['track:autocomplete', 'unfinished_prefix'] review=['unfinished_prefix']

## 109. [autocomplete/prefix_7] `hnq10k-v3-07947`
- **query**: `nhà bát`
- **clean_query**: `Nhà Bát `
- **POI**: Nhà Bát Giác |  | amenity=library
- **split**: dev_synthetic | surface=committed_text | gen=controlled_typing_rule
- **compat**: 1 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['track:autocomplete'] train_excl=['not_train_split', 'track:autocomplete', 'unfinished_prefix'] review=['unfinished_prefix']

## 110. [autocomplete/prefix_8] `hnq20k-v4-add-09562`
- **query**: `ký túc x`
- **clean_query**: `ký túc xá`
- **POI**: Ký túc xá |  | building=dormitory
- **split**: train | surface=committed_text | gen=controlled_prefix
- **compat**: 39 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **mutation**: None → None ops=['prefix_truncation'] ime=None
- **flags**: main_excl=['track_autocomplete', 'multiple_known_compatible', 'cross_split_compatible'] train_excl=['track_autocomplete', 'multiple_known_compatible', 'cross_split_compatible', 'ambiguous_or_partial_input'] review=['multiple_known_compatible', 'ambiguous_or_partial_input']

## 111. [autocomplete/prefix_4] `hnq10k-v3-09567`
- **query**: `giao`
- **clean_query**: `Giao `
- **POI**: Giao hàng Tiết kiệm |  | amenity=post_office
- **split**: train | surface=committed_text | gen=controlled_typing_rule
- **compat**: 9 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois', 'track:autocomplete', 'cross_split_compatible'] train_excl=['multiple_compatible_pois', 'track:autocomplete', 'cross_split_compatible', 'unfinished_prefix'] review=['multiple_compatible_pois', 'unfinished_prefix', 'cross_split_compatible']

## 112. [autocomplete/prefix_5] `hnq20k-v4-add-09237`
- **query**: `kingd`
- **clean_query**: `kingdom hotel`
- **POI**: Kingdom Hotel | 4 | tourism=hotel
- **split**: train | surface=committed_text | gen=controlled_prefix
- **compat**: 1 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **mutation**: None → None ops=['prefix_truncation'] ime=None
- **flags**: main_excl=['track_autocomplete'] train_excl=['track_autocomplete', 'ambiguous_or_partial_input'] review=['ambiguous_or_partial_input']

## 113. [autocomplete/prefix_6] `hnq10k-v3-08197`
- **query**: `chợ cầ`
- **clean_query**: `chợ Cầ`
- **POI**: chợ Cầu | xã Liên Minh (Thọ An cũ) | amenity=marketplace
- **split**: train | surface=committed_text | gen=controlled_typing_rule
- **compat**: 11 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois', 'track:autocomplete', 'cross_split_compatible'] train_excl=['multiple_compatible_pois', 'track:autocomplete', 'cross_split_compatible', 'unfinished_prefix'] review=['multiple_compatible_pois', 'unfinished_prefix', 'cross_split_compatible']

## 114. [autocomplete/prefix_7] `hnq10k-v3-03072`
- **query**: `6 đường`
- **clean_query**: `6 Đường `
- **POI**: 6 Đường Thành Phố 4.4 | 6 Đường Thành Phố 4.4 Phân khu Cát Tường | address=
- **split**: test_synthetic | surface=committed_text | gen=controlled_typing_rule
- **compat**: 29 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois', 'track:autocomplete', 'cross_split_compatible'] train_excl=['not_train_split', 'multiple_compatible_pois', 'track:autocomplete', 'cross_split_compatible', 'unfinished_prefix'] review=['multiple_compatible_pois', 'unfinished_prefix', 'cross_split_compatible']

## 115. [autocomplete/prefix_8] `hnq20k-v4-add-09652`
- **query**: `quà tặng`
- **clean_query**: `quà tặng tháng năm`
- **POI**: Quà tặng Tháng Năm |  | shop=gift
- **split**: train | surface=committed_text | gen=controlled_prefix
- **compat**: 3 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **mutation**: None → None ops=['prefix_truncation'] ime=None
- **flags**: main_excl=['track_autocomplete', 'multiple_known_compatible'] train_excl=['track_autocomplete', 'multiple_known_compatible', 'ambiguous_or_partial_input'] review=['multiple_known_compatible', 'ambiguous_or_partial_input']

## 116. [autocomplete/prefix_4] `hnq10k-v3-00117`
- **query**: `giáp`
- **clean_query**: `Giáp `
- **POI**: Giáp Bát |  | public_transport=station
- **split**: train | surface=committed_text | gen=controlled_typing_rule
- **compat**: 3 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois', 'track:autocomplete'] train_excl=['multiple_compatible_pois', 'track:autocomplete', 'unfinished_prefix'] review=['multiple_compatible_pois', 'unfinished_prefix']

## 117. [autocomplete/prefix_5] `hnq20k-v4-add-09145`
- **query**: `de sy`
- **clean_query**: `de syloia`
- **POI**: De Syloia | 17A Phố Trần Hưng Đạo | tourism=hotel
- **split**: train | surface=committed_text | gen=controlled_prefix
- **compat**: 1 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **mutation**: None → None ops=['prefix_truncation'] ime=None
- **flags**: main_excl=['track_autocomplete'] train_excl=['track_autocomplete', 'ambiguous_or_partial_input'] review=['ambiguous_or_partial_input']

## 118. [autocomplete/prefix_6] `hnq10k-v3-09672`
- **query**: `sơn bi`
- **clean_query**: `Sơn Bi`
- **POI**: Sơn Bia | 45 Phố Trần Thái Tông | amenity=pub
- **split**: dev_synthetic | surface=committed_text | gen=controlled_typing_rule
- **compat**: 1 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['track:autocomplete'] train_excl=['not_train_split', 'track:autocomplete', 'unfinished_prefix'] review=['unfinished_prefix']

## 119. [autocomplete/prefix_7] `hnq10k-v3-02797`
- **query**: `331 phố`
- **clean_query**: `331 Phố `
- **POI**: 331 Phố Ngọc Lâm | 331 Phố Ngọc Lâm | address=
- **split**: train | surface=committed_text | gen=controlled_typing_rule
- **compat**: 2 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois', 'track:autocomplete'] train_excl=['multiple_compatible_pois', 'track:autocomplete', 'unfinished_prefix'] review=['multiple_compatible_pois', 'unfinished_prefix']

## 120. [autocomplete/prefix_8] `hnq20k-v4-add-09901`
- **query**: `53 phố t`
- **clean_query**: `53 phố tứ liên`
- **POI**: 53 Phố Tứ Liên | 53 Phố Tứ Liên | address=
- **split**: architecture_holdout | surface=committed_text | gen=controlled_prefix
- **compat**: 9 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **mutation**: None → None ops=['prefix_truncation'] ime=None
- **flags**: main_excl=['track_autocomplete', 'multiple_known_compatible', 'cross_split_compatible'] train_excl=['track_autocomplete', 'multiple_known_compatible', 'cross_split_compatible', 'ambiguous_or_partial_input', 'not_train_split'] review=['multiple_known_compatible', 'ambiguous_or_partial_input']

## 121. [ambiguity_stress/address_exact] `hnq10k-v3-03241`
- **query**: `1 thời đại 1`
- **clean_query**: `1 Thời Đại 1`
- **POI**: 1 Thời Đại 1 | 1 Thời Đại 1 Phân khu Thịnh Vượng, Global Gate | address=
- **split**: train | surface=committed_text | gen=grounded_composition
- **compat**: 53 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois', 'track:ambiguity_stress'] train_excl=['multiple_compatible_pois', 'track:ambiguity_stress'] review=['multiple_compatible_pois']

## 122. [ambiguity_stress/adjacent_transpose] `hnq10k-v3-04463`
- **query**: `tpbank lviebank 24/7`
- **clean_query**: `TPBank LiveBank 24/7`
- **POI**: TPBank LiveBank 24/7 |  | amenity=atm
- **split**: train | surface=committed_text | gen=controlled_typing_rule
- **compat**: 124 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **mutation**: tpbank livebank 24/7 → tpbank lviebank 24/7 ops=None ime=None
- **flags**: main_excl=['multiple_compatible_pois', 'track:ambiguity_stress'] train_excl=['multiple_compatible_pois', 'track:ambiguity_stress'] review=['multiple_compatible_pois']

## 123. [ambiguity_stress/character_deletion] `hnq20k-v4-add-04600`
- **query**: `van puc`
- **clean_query**: `van phuc`
- **POI**: Vạn Phúc |  | amenity=bank
- **split**: train | surface=committed_text | gen=controlled_typing_variant
- **compat**: 79 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **mutation**: None → None ops=['accent_folding', 'character_deletion'] ime=None
- **flags**: main_excl=['track_ambiguity_stress', 'multiple_known_compatible', 'cross_split_compatible'] train_excl=['track_ambiguity_stress', 'multiple_known_compatible', 'cross_split_compatible', 'ambiguous_or_partial_input'] review=['multiple_known_compatible', 'ambiguous_or_partial_input']

## 124. [ambiguity_stress/clean_name] `hnq10k-v3-00226`
- **query**: `kfc`
- **clean_query**: `KFC`
- **POI**: KFC |  | amenity=fast_food
- **split**: train | surface=committed_text | gen=grounded_composition
- **compat**: 25 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois', 'track:ambiguity_stress'] train_excl=['multiple_compatible_pois', 'track:ambiguity_stress'] review=['multiple_compatible_pois']

## 125. [ambiguity_stress/editorial_paraphrase] `hnq10k-v3-00176`
- **query**: `winmart lê duẩn`
- **clean_query**: `winmart lê duẩn`
- **POI**: WinMart+ | 49 Đường Lê Duẩn Cửa Nam | shop=convenience
- **split**: train | surface=committed_text | gen=codex_authored_per_poi
- **compat**: 826 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois', 'track:ambiguity_stress'] train_excl=['multiple_compatible_pois', 'track:ambiguity_stress', 'editorial_paraphrase'] review=['multiple_compatible_pois', 'editorial_paraphrase']

## 126. [ambiguity_stress/grounded_search_phrase] `hnq20k-v4-add-02892`
- **query**: `đi tới market`
- **clean_query**: `đi tới market`
- **POI**: Market |  | building=yes
- **split**: architecture_holdout | surface=committed_text | gen=codex_authored_pattern_instantiation
- **compat**: 60 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['track_ambiguity_stress', 'multiple_known_compatible', 'cross_split_compatible'] train_excl=['track_ambiguity_stress', 'multiple_known_compatible', 'cross_split_compatible', 'ambiguous_or_partial_input', 'synthetic_language_rule', 'not_train_split'] review=['multiple_known_compatible', 'ambiguous_or_partial_input', 'synthetic_language_rule']

## 127. [ambiguity_stress/keyboard_neighbor] `hnq20k-v4-add-06018`
- **query**: `dong amh`
- **clean_query**: `dong anh`
- **POI**: Đông Anh |  | public_transport=station
- **split**: train | surface=committed_text | gen=controlled_typing_variant
- **compat**: 63 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **mutation**: None → None ops=['accent_folding', 'keyboard_neighbor'] ime=None
- **flags**: main_excl=['track_ambiguity_stress', 'multiple_known_compatible', 'cross_split_compatible'] train_excl=['track_ambiguity_stress', 'multiple_known_compatible', 'cross_split_compatible', 'ambiguous_or_partial_input'] review=['multiple_known_compatible', 'ambiguous_or_partial_input']

## 128. [ambiguity_stress/mixed_two_errors] `hnq20k-v4-add-07222`
- **query**: `do p`
- **clean_query**: `do do`
- **POI**: Đô Đô | 17B10 Phố Phạm Ngọc Thạch Kim Liên | amenity=cafe
- **split**: train | surface=committed_text | gen=controlled_typing_variant
- **compat**: 527 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **mutation**: None → None ops=['accent_folding', 'character_deletion', 'keyboard_neighbor'] ime=None
- **flags**: main_excl=['track_ambiguity_stress', 'multiple_known_compatible', 'cross_split_compatible'] train_excl=['track_ambiguity_stress', 'multiple_known_compatible', 'cross_split_compatible', 'ambiguous_or_partial_input'] review=['multiple_known_compatible', 'ambiguous_or_partial_input']

## 129. [ambiguity_stress/no_diacritics] `hnq10k-v3-00718`
- **query**: `van`
- **clean_query**: `Vân`
- **POI**: Vân |  | shop=clothes
- **split**: train | surface=committed_text | gen=controlled_typing_rule
- **compat**: 1841 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois', 'track:ambiguity_stress', 'cross_split_compatible'] train_excl=['multiple_compatible_pois', 'track:ambiguity_stress', 'cross_split_compatible'] review=['multiple_compatible_pois', 'cross_split_compatible']

## 130. [ambiguity_stress/partial_diacritics] `hnq20k-v4-add-03614`
- **query**: `nha dân`
- **clean_query**: `nhà dân`
- **POI**: Nhà dân |  | building=house
- **split**: train | surface=committed_text | gen=controlled_typing_variant
- **compat**: 119 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **mutation**: None → None ops=['single_tone_removed'] ime=None
- **flags**: main_excl=['track_ambiguity_stress', 'multiple_known_compatible', 'cross_split_compatible'] train_excl=['track_ambiguity_stress', 'multiple_known_compatible', 'cross_split_compatible', 'ambiguous_or_partial_input'] review=['multiple_known_compatible', 'ambiguous_or_partial_input']

## 131. [ambiguity_stress/prefix_1] `hnq20k-v4-add-07904`
- **query**: `t`
- **clean_query**: `trường tiểu học thuỵ an`
- **POI**: Trường Tiểu học Thuỵ An |  | amenity=school
- **split**: architecture_holdout | surface=committed_text | gen=controlled_prefix
- **compat**: 6123 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **mutation**: None → None ops=['prefix_truncation'] ime=None
- **flags**: main_excl=['track_ambiguity_stress', 'multiple_known_compatible', 'cross_split_compatible', 'normalized_query_cross_split'] train_excl=['track_ambiguity_stress', 'multiple_known_compatible', 'cross_split_compatible', 'normalized_query_cross_split', 'ambiguous_or_partial_input', 'not_train_split'] review=['multiple_known_compatible', 'ambiguous_or_partial_input']

## 132. [ambiguity_stress/prefix_2] `hnq10k-v3-02107`
- **query**: `10`
- **clean_query**: `10`
- **POI**: 108 Hẻm 25 Ngách 49 Ngõ 165 Phố Dương Quảng Hàm | 108 Hẻm 25 Ngách 49 Ngõ 165 Phố Dương Quảng Hàm | address=
- **split**: test_synthetic | surface=committed_text | gen=controlled_typing_rule
- **compat**: 755 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois', 'track:ambiguity_stress', 'cross_split_compatible'] train_excl=['not_train_split', 'multiple_compatible_pois', 'track:ambiguity_stress', 'cross_split_compatible', 'unfinished_prefix'] review=['multiple_compatible_pois', 'unfinished_prefix', 'cross_split_compatible']

## 133. [ambiguity_stress/prefix_3] `hnq10k-v3-04662`
- **query**: `nhà`
- **clean_query**: `Nhà`
- **POI**: Nhà Đạt Đồng Đò |  | amenity=bar
- **split**: train | surface=committed_text | gen=controlled_typing_rule
- **compat**: 1626 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois', 'track:ambiguity_stress', 'cross_split_compatible'] train_excl=['multiple_compatible_pois', 'track:ambiguity_stress', 'cross_split_compatible', 'unfinished_prefix'] review=['multiple_compatible_pois', 'unfinished_prefix', 'cross_split_compatible']

## 134. [ambiguity_stress/prefix_4] `hnq10k-v3-08942`
- **query**: `chùa`
- **clean_query**: `Chùa `
- **POI**: Chùa Kiến Bái |  | amenity=place_of_worship
- **split**: train | surface=committed_text | gen=controlled_typing_rule
- **compat**: 333 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois', 'track:ambiguity_stress', 'cross_split_compatible'] train_excl=['multiple_compatible_pois', 'track:ambiguity_stress', 'cross_split_compatible', 'unfinished_prefix'] review=['multiple_compatible_pois', 'unfinished_prefix', 'cross_split_compatible']

## 135. [ambiguity_stress/prefix_5] `hnq10k-v3-09467`
- **query**: `trung`
- **clean_query**: `Trung`
- **POI**: Trung tâm Vận hành EMS |  | amenity=post_depot
- **split**: train | surface=committed_text | gen=controlled_typing_rule
- **compat**: 456 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois', 'track:ambiguity_stress', 'cross_split_compatible'] train_excl=['multiple_compatible_pois', 'track:ambiguity_stress', 'cross_split_compatible', 'unfinished_prefix'] review=['multiple_compatible_pois', 'unfinished_prefix', 'cross_split_compatible']

## 136. [ambiguity_stress/prefix_6] `hnq10k-v3-00522`
- **query**: `vinfas`
- **clean_query**: `VinFas`
- **POI**: VinFast |  | amenity=charging_station
- **split**: train | surface=committed_text | gen=controlled_typing_rule
- **compat**: 408 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois', 'track:ambiguity_stress'] train_excl=['multiple_compatible_pois', 'track:ambiguity_stress', 'unfinished_prefix'] review=['multiple_compatible_pois', 'unfinished_prefix']

## 137. [ambiguity_stress/prefix_7] `hnq10k-v3-03697`
- **query**: `nhà văn`
- **clean_query**: `Nhà văn `
- **POI**: Nhà văn hóa Tổ dân phố Đào Nguyên | 8 Ngõ 215 đường Trâu Quỳ | amenity=community_centre
- **split**: train | surface=committed_text | gen=controlled_typing_rule
- **compat**: 265 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois', 'track:ambiguity_stress', 'cross_split_compatible'] train_excl=['multiple_compatible_pois', 'track:ambiguity_stress', 'cross_split_compatible', 'unfinished_prefix'] review=['multiple_compatible_pois', 'unfinished_prefix', 'cross_split_compatible']

## 138. [ambiguity_stress/prefix_8] `hnq10k-v3-04472`
- **query**: `vpbank c`
- **clean_query**: `VPBank C`
- **POI**: VPBank CDM |  | amenity=atm
- **split**: train | surface=committed_text | gen=controlled_typing_rule
- **compat**: 52 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois', 'track:ambiguity_stress'] train_excl=['multiple_compatible_pois', 'track:ambiguity_stress', 'unfinished_prefix'] review=['multiple_compatible_pois', 'unfinished_prefix']

## 139. [ambiguity_stress/repeated_character] `hnq20k-v4-add-05762`
- **query**: `san hho`
- **clean_query**: `san ho`
- **POI**: San Ho |  | amenity=restaurant
- **split**: dev_synthetic | surface=committed_text | gen=controlled_typing_variant
- **compat**: 271 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **mutation**: None → None ops=['accent_folding', 'repeated_character'] ime=None
- **flags**: main_excl=['track_ambiguity_stress', 'multiple_known_compatible', 'cross_split_compatible'] train_excl=['track_ambiguity_stress', 'multiple_known_compatible', 'cross_split_compatible', 'ambiguous_or_partial_input', 'not_train_split'] review=['multiple_known_compatible', 'ambiguous_or_partial_input']

## 140. [ambiguity_stress/search_phrase] `hnq10k-v3-00845`
- **query**: `địa chỉ vietcombank`
- **clean_query**: `Vietcombank`
- **POI**: Vietcombank |  | amenity=bank
- **split**: train | surface=committed_text | gen=grounded_composition
- **compat**: 235 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois', 'track:ambiguity_stress'] train_excl=['multiple_compatible_pois', 'track:ambiguity_stress'] review=['multiple_compatible_pois']

## 141. [ambiguity_stress/source_alias_or_abbreviation] `hnq20k-v4-add-01118`
- **query**: `yên lãng`
- **clean_query**: `yên lãng`
- **POI**: Kẻ Láng |  | historic=yes
- **split**: train | surface=committed_text | gen=source_alias
- **compat**: 57 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['track_ambiguity_stress', 'multiple_known_compatible', 'cross_split_compatible'] train_excl=['track_ambiguity_stress', 'multiple_known_compatible', 'cross_split_compatible', 'ambiguous_or_partial_input', 'synthetic_language_rule'] review=['multiple_known_compatible', 'ambiguous_or_partial_input', 'synthetic_language_rule']

## 142. [ambiguity_stress/space_edit] `hnq20k-v4-add-06721`
- **query**: `thanhha`
- **clean_query**: `thanh ha`
- **POI**: Thanh hà | 41 Phố Lý Quốc Sư | shop=convenience
- **split**: train | surface=committed_text | gen=controlled_typing_variant
- **compat**: 149 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **mutation**: None → None ops=['accent_folding', 'space_edit'] ime=None
- **flags**: main_excl=['track_ambiguity_stress', 'multiple_known_compatible', 'cross_split_compatible'] train_excl=['track_ambiguity_stress', 'multiple_known_compatible', 'cross_split_compatible', 'ambiguous_or_partial_input'] review=['multiple_known_compatible', 'ambiguous_or_partial_input']

## 143. [ambiguity_stress/wrong_tone] `hnq10k-v3-04563`
- **query**: `ngân háng nông nghiệp`
- **clean_query**: `Ngân hàng Nông nghiệp`
- **POI**: Ngân hàng Nông nghiệp |  | amenity=bank
- **split**: train | surface=committed_text | gen=controlled_typing_rule
- **compat**: 84 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois', 'track:ambiguity_stress', 'cross_split_compatible'] train_excl=['multiple_compatible_pois', 'track:ambiguity_stress', 'cross_split_compatible'] review=['multiple_compatible_pois', 'cross_split_compatible']

## 144. [ambiguity_stress/adjacent_transpose] `hnq10k-v3-06005`
- **query**: `dinh dunog`
- **clean_query**: `Đình Đương`
- **POI**: Đình Đương |  | amenity=community_centre
- **split**: dev_synthetic | surface=committed_text | gen=controlled_typing_rule
- **compat**: 247 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **mutation**: dinh duong → dinh dunog ops=None ime=None
- **flags**: main_excl=['multiple_compatible_pois', 'track:ambiguity_stress', 'cross_split_compatible'] train_excl=['not_train_split', 'multiple_compatible_pois', 'track:ambiguity_stress', 'cross_split_compatible'] review=['multiple_compatible_pois', 'cross_split_compatible']

## 145. [ambiguity_stress/character_deletion] `hnq20k-v4-add-04947`
- **query**: `khac san`
- **clean_query**: `khach san`
- **POI**: Khach San | 23-25 | tourism=hotel
- **split**: architecture_holdout | surface=committed_text | gen=controlled_typing_variant
- **compat**: 315 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **mutation**: None → None ops=['accent_folding', 'character_deletion'] ime=None
- **flags**: main_excl=['track_ambiguity_stress', 'multiple_known_compatible', 'cross_split_compatible'] train_excl=['track_ambiguity_stress', 'multiple_known_compatible', 'cross_split_compatible', 'ambiguous_or_partial_input', 'not_train_split'] review=['multiple_known_compatible', 'ambiguous_or_partial_input']

## 146. [ambiguity_stress/clean_name] `hnq10k-v3-00506`
- **query**: `vib`
- **clean_query**: `VIB`
- **POI**: VIB | D2 Giảng Võ | amenity=atm
- **split**: train | surface=committed_text | gen=grounded_composition
- **compat**: 31 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois', 'track:ambiguity_stress', 'cross_split_compatible'] train_excl=['multiple_compatible_pois', 'track:ambiguity_stress', 'cross_split_compatible'] review=['multiple_compatible_pois', 'cross_split_compatible']

## 147. [ambiguity_stress/editorial_paraphrase] `hnq10k-v3-00141`
- **query**: `gia lâm ngọc lâm`
- **clean_query**: `gia lâm ngọc lâm`
- **POI**: Gia Lâm | Ngõ 481 Ngọc Lâm Ngọc Lâm | public_transport=station
- **split**: train | surface=committed_text | gen=codex_authored_per_poi
- **compat**: 66 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois', 'track:ambiguity_stress', 'cross_split_compatible'] train_excl=['multiple_compatible_pois', 'track:ambiguity_stress', 'cross_split_compatible', 'editorial_paraphrase'] review=['multiple_compatible_pois', 'editorial_paraphrase', 'cross_split_compatible']

## 148. [ambiguity_stress/grounded_search_phrase] `hnq20k-v4-add-02900`
- **query**: `đến điếm canh đê`
- **clean_query**: `đến điếm canh đê`
- **POI**: Điếm canh đê |  | building=yes
- **split**: architecture_holdout | surface=committed_text | gen=codex_authored_pattern_instantiation
- **compat**: 66 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['track_ambiguity_stress', 'multiple_known_compatible', 'cross_split_compatible'] train_excl=['track_ambiguity_stress', 'multiple_known_compatible', 'cross_split_compatible', 'ambiguous_or_partial_input', 'synthetic_language_rule', 'not_train_split'] review=['multiple_known_compatible', 'ambiguous_or_partial_input', 'synthetic_language_rule']

## 149. [ambiguity_stress/keyboard_neighbor] `hnq20k-v4-add-06023`
- **query**: `minh jhai`
- **clean_query**: `minh khai`
- **POI**: Minh Khai |  | public_transport=stop_area
- **split**: train | surface=committed_text | gen=controlled_typing_variant
- **compat**: 108 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **mutation**: None → None ops=['accent_folding', 'keyboard_neighbor'] ime=None
- **flags**: main_excl=['track_ambiguity_stress', 'multiple_known_compatible', 'cross_split_compatible'] train_excl=['track_ambiguity_stress', 'multiple_known_compatible', 'cross_split_compatible', 'ambiguous_or_partial_input'] review=['multiple_known_compatible', 'ambiguous_or_partial_input']

## 150. [ambiguity_stress/mixed_two_errors] `hnq20k-v4-add-07190`
- **query**: `phi hun`
- **clean_query**: `pho hung`
- **POI**: Pho Hùng |  | amenity=restaurant
- **split**: train | surface=committed_text | gen=controlled_typing_variant
- **compat**: 68 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **mutation**: None → None ops=['accent_folding', 'character_deletion', 'keyboard_neighbor'] ime=None
- **flags**: main_excl=['track_ambiguity_stress', 'multiple_known_compatible', 'cross_split_compatible'] train_excl=['track_ambiguity_stress', 'multiple_known_compatible', 'cross_split_compatible', 'ambiguous_or_partial_input'] review=['multiple_known_compatible', 'ambiguous_or_partial_input']

## 151. [ime_keystream/ime_raw_keys] `hnq20k-v4-add-02106`
- **query**: `ky1 tuc1 xa1`
- **clean_query**: `ký túc xá`
- **POI**: Ký túc xá |  | building=yes
- **split**: train | surface=raw_keys | gen=rule_generated_ime
- **compat**: 48 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **mutation**: None → None ops=['vni_raw_encoding'] ime=vni
- **flags**: main_excl=['track_ime_keystream', 'multiple_known_compatible', 'cross_split_compatible'] train_excl=['track_ime_keystream', 'multiple_known_compatible', 'cross_split_compatible', 'ime_engine_unverified'] review=['multiple_known_compatible', 'ime_engine_unverified']

## 152. [ime_keystream/telex_raw_keys] `hnq10k-v3-06703`
- **query**: `thuwcj phaamr chay aau lacj`
- **clean_query**: `Thực Phẩm Chay Âu Lạc`
- **POI**: Thực Phẩm Chay Âu Lạc |  | amenity=food_court
- **split**: train | surface=raw_keys | gen=controlled_ime_key_rule
- **compat**: 1 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['track:ime_keystream'] train_excl=['track:ime_keystream', 'unverified_ime_keystream'] review=['unverified_ime_keystream']

## 153. [ime_keystream/vni_raw_keys] `hnq10k-v3-06833`
- **query**: `cu7a3 hang2 xa8ng da6u2 so61 14 d9u7o7ng2 thuy5 khue6`
- **clean_query**: `Cửa hàng xăng dầu số 14 Đường Thụy Khuê`
- **POI**: Cửa hàng xăng dầu số 14 | Đường Thụy Khuê | amenity=fuel
- **split**: train | surface=raw_keys | gen=controlled_ime_key_rule
- **compat**: 1 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['missing_sibling_address', 'track:ime_keystream'] train_excl=['missing_sibling_address', 'track:ime_keystream', 'unverified_ime_keystream'] review=['missing_sibling_address', 'unverified_ime_keystream']

## 154. [ime_keystream/ime_raw_keys] `hnq20k-v4-add-02017`
- **query**: `phee la - yeen phuj`
- **clean_query**: `phê la - yên phụ`
- **POI**: Phê La - Yên Phụ |  | amenity=cafe
- **split**: train | surface=raw_keys | gen=rule_generated_ime
- **compat**: 1 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **mutation**: None → None ops=['telex_raw_encoding'] ime=telex
- **flags**: main_excl=['track_ime_keystream'] train_excl=['track_ime_keystream', 'ime_engine_unverified'] review=['ime_engine_unverified']

## 155. [ime_keystream/telex_raw_keys] `hnq10k-v3-03453`
- **query**: `159 phoos quan nhaan`
- **clean_query**: `159 Phố Quan Nhân`
- **POI**: 159 Phố Quan Nhân | 159 Phố Quan Nhân | address=
- **split**: test_synthetic | surface=raw_keys | gen=controlled_ime_key_rule
- **compat**: 2 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois', 'track:ime_keystream'] train_excl=['not_train_split', 'multiple_compatible_pois', 'track:ime_keystream', 'unverified_ime_keystream'] review=['multiple_compatible_pois', 'unverified_ime_keystream']

## 156. [ime_keystream/vni_raw_keys] `hnq10k-v3-02833`
- **query**: `6 pho61 nha6n hoa2`
- **clean_query**: `6 Phố Nhân Hòa`
- **POI**: 6 Phố Nhân Hòa | 6 Phố Nhân Hòa | address=
- **split**: train | surface=raw_keys | gen=controlled_ime_key_rule
- **compat**: 2 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois', 'track:ime_keystream'] train_excl=['multiple_compatible_pois', 'track:ime_keystream', 'unverified_ime_keystream'] review=['multiple_compatible_pois', 'unverified_ime_keystream']

## 157. [ime_keystream/ime_raw_keys] `hnq20k-v4-add-02351`
- **query**: `truowcs 50m caauf hoaf khee`
- **clean_query**: `trước 50m cầu hòa khê`
- **POI**: Trước 50m cầu Hòa Khê |  | public_transport=platform
- **split**: architecture_holdout | surface=raw_keys | gen=rule_generated_ime
- **compat**: 1 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **mutation**: None → None ops=['telex_raw_encoding'] ime=telex
- **flags**: main_excl=['track_ime_keystream'] train_excl=['track_ime_keystream', 'ime_engine_unverified', 'not_train_split'] review=['ime_engine_unverified']

## 158. [ime_keystream/telex_raw_keys] `hnq10k-v3-06053`
- **query**: `toaf ans nhaan daan huyeenj thuowngf tins`
- **clean_query**: `Toà án nhân dân huyện Thường Tín`
- **POI**: Toà án nhân dân huyện Thường Tín |  | amenity=courthouse
- **split**: train | surface=raw_keys | gen=controlled_ime_key_rule
- **compat**: 1 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['track:ime_keystream'] train_excl=['track:ime_keystream', 'unverified_ime_keystream'] review=['unverified_ime_keystream']

## 159. [ime_keystream/vni_raw_keys] `hnq10k-v3-09083`
- **query**: `chua2 d9u7c1 hoa2 - pha6t5 giao1 nguye6n thuy3`
- **clean_query**: `Chùa Đức Hòa - Phật Giáo Nguyên Thủy`
- **POI**: Chùa Đức Hòa - Phật Giáo Nguyên Thủy | Thôn Bến Đức Hòa | amenity=place_of_worship
- **split**: train | surface=raw_keys | gen=controlled_ime_key_rule
- **compat**: 1 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['track:ime_keystream'] train_excl=['track:ime_keystream', 'unverified_ime_keystream'] review=['unverified_ime_keystream']

## 160. [ime_keystream/ime_raw_keys] `hnq20k-v4-add-02104`
- **query**: `chung cu7 an lac5 - nam la khe6`
- **clean_query**: `chung cư an lạc - nam la khê`
- **POI**: Chung cư An Lạc - Nam La Khê |  | building=apartments
- **split**: train | surface=raw_keys | gen=rule_generated_ime
- **compat**: 1 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **mutation**: None → None ops=['vni_raw_encoding'] ime=vni
- **flags**: main_excl=['track_ime_keystream'] train_excl=['track_ime_keystream', 'ime_engine_unverified'] review=['ime_engine_unverified']

## 161. [ime_keystream/telex_raw_keys] `hnq10k-v3-08503`
- **query**: `nhaf thuoocs truowngf huowng phoos thanhf thais`
- **clean_query**: `Nhà thuốc Trường Hương Phố Thành Thái`
- **POI**: Nhà thuốc Trường Hương | Phố Thành Thái Dịch Vọng | amenity=pharmacy
- **split**: train | surface=raw_keys | gen=controlled_ime_key_rule
- **compat**: 1 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['track:ime_keystream'] train_excl=['track:ime_keystream', 'unverified_ime_keystream'] review=['unverified_ime_keystream']

## 162. [ime_keystream/vni_raw_keys] `hnq10k-v3-08208`
- **query**: `cho75 mia1`
- **clean_query**: `Chợ Mía`
- **POI**: Chợ Mía |  | amenity=marketplace
- **split**: test_synthetic | surface=raw_keys | gen=controlled_ime_key_rule
- **compat**: 1 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['track:ime_keystream'] train_excl=['not_train_split', 'track:ime_keystream', 'unverified_ime_keystream'] review=['unverified_ime_keystream']

## 163. [ime_keystream/ime_raw_keys] `hnq20k-v4-add-02139`
- **query**: `hoor ddoong duowng`
- **clean_query**: `hổ đông dương`
- **POI**: Hổ Đông Dương |  | tourism=attraction
- **split**: train | surface=raw_keys | gen=rule_generated_ime
- **compat**: 1 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **mutation**: None → None ops=['telex_raw_encoding'] ime=telex
- **flags**: main_excl=['track_ime_keystream'] train_excl=['track_ime_keystream', 'ime_engine_unverified'] review=['ime_engine_unverified']

## 164. [ime_keystream/telex_raw_keys] `hnq10k-v3-05903`
- **query**: `nhaf vawn hoas thoon vuwcj dduowngf ddan khee`
- **clean_query**: `Nhà văn hóa thôn Vực Đường Đan Khê`
- **POI**: Nhà văn hóa thôn Vực | Đường Đan Khê | amenity=community_centre
- **split**: train | surface=raw_keys | gen=controlled_ime_key_rule
- **compat**: 1 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['track:ime_keystream'] train_excl=['track:ime_keystream', 'unverified_ime_keystream'] review=['unverified_ime_keystream']

## 165. [ime_keystream/vni_raw_keys] `hnq10k-v3-06008`
- **query**: `nha2 va8n hoa1 tho6n 4`
- **clean_query**: `Nhà văn hóa thôn 4`
- **POI**: Nhà văn hóa thôn 4 |  | amenity=community_centre
- **split**: train | surface=raw_keys | gen=controlled_ime_key_rule
- **compat**: 3 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois', 'track:ime_keystream'] train_excl=['multiple_compatible_pois', 'track:ime_keystream', 'unverified_ime_keystream'] review=['multiple_compatible_pois', 'unverified_ime_keystream']

## 166. [ime_keystream/ime_raw_keys] `hnq20k-v4-add-02189`
- **query**: `13 phoos toong ddanr`
- **clean_query**: `13 phố tông đản`
- **POI**: 13 Phố Tông Đản | 13 Phố Tông Đản | address=
- **split**: train | surface=raw_keys | gen=rule_generated_ime
- **compat**: 1 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **mutation**: None → None ops=['telex_raw_encoding'] ime=telex
- **flags**: main_excl=['track_ime_keystream'] train_excl=['track_ime_keystream', 'ime_engine_unverified'] review=['ime_engine_unverified']

## 167. [ime_keystream/telex_raw_keys] `hnq10k-v3-02678`
- **query**: `158 dduowngf thieen nga 6`
- **clean_query**: `158 Đường Thiên Nga 6`
- **POI**: 158 Đường Thiên Nga 6 | 158 Đường Thiên Nga 6 Phân khu Tinh Hoa, Global Gate | address=
- **split**: train | surface=raw_keys | gen=controlled_ime_key_rule
- **compat**: 1 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['track:ime_keystream'] train_excl=['track:ime_keystream', 'unverified_ime_keystream'] review=['unverified_ime_keystream']

## 168. [ime_keystream/vni_raw_keys] `hnq10k-v3-02933`
- **query**: `30 ngo4 140 ngoc5 thuy5`
- **clean_query**: `30 Ngõ 140 Ngọc Thụy`
- **POI**: 30 Ngõ 140 Ngọc Thụy | 30 Ngõ 140 Ngọc Thụy | address=
- **split**: train | surface=raw_keys | gen=controlled_ime_key_rule
- **compat**: 1 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['track:ime_keystream'] train_excl=['track:ime_keystream', 'unverified_ime_keystream'] review=['unverified_ime_keystream']

## 169. [ime_keystream/ime_raw_keys] `hnq20k-v4-add-02114`
- **query**: `khach1 san5 classic 2`
- **clean_query**: `khách sạn classic 2`
- **POI**: Khách Sạn Classic 2 | 49 Lương Ngọc Quyến | tourism=hotel
- **split**: train | surface=raw_keys | gen=rule_generated_ime
- **compat**: 1 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **mutation**: None → None ops=['vni_raw_encoding'] ime=vni
- **flags**: main_excl=['track_ime_keystream'] train_excl=['track_ime_keystream', 'ime_engine_unverified'] review=['ime_engine_unverified']

## 170. [ime_keystream/telex_raw_keys] `hnq10k-v3-05453`
- **query**: `ddieemr y tees phucs lowij`
- **clean_query**: `Điểm y tế Phúc Lợi`
- **POI**: Điểm y tế Phúc Lợi |  | amenity=clinic
- **split**: train | surface=raw_keys | gen=controlled_ime_key_rule
- **compat**: 1 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['track:ime_keystream'] train_excl=['track:ime_keystream', 'unverified_ime_keystream'] review=['unverified_ime_keystream']

## 171. [ime_keystream/vni_raw_keys] `hnq10k-v3-01433`
- **query**: `vpbank 61 pho61 xa4 d9an2`
- **clean_query**: `VPBank 61 Phố Xã Đàn`
- **POI**: VPBank | 61 Phố Xã Đàn | amenity=bank
- **split**: train | surface=raw_keys | gen=controlled_ime_key_rule
- **compat**: 1 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['missing_sibling_address', 'track:ime_keystream'] train_excl=['missing_sibling_address', 'track:ime_keystream', 'unverified_ime_keystream'] review=['missing_sibling_address', 'unverified_ime_keystream']

## 172. [ime_keystream/ime_raw_keys] `hnq20k-v4-add-02368`
- **query**: `lai5 tao3 motor`
- **clean_query**: `lại tảo motor`
- **POI**: Lại Tảo Motor |  | shop=motorcycle_repair
- **split**: architecture_holdout | surface=raw_keys | gen=rule_generated_ime
- **compat**: 1 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **mutation**: None → None ops=['vni_raw_encoding'] ime=vni
- **flags**: main_excl=['track_ime_keystream'] train_excl=['track_ime_keystream', 'ime_engine_unverified', 'not_train_split'] review=['ime_engine_unverified']

## 173. [ime_keystream/telex_raw_keys] `hnq10k-v3-08853`
- **query**: `ddieenj huy vawn`
- **clean_query**: `Điện Huy Văn`
- **POI**: Điện Huy Văn |  | amenity=place_of_worship
- **split**: train | surface=raw_keys | gen=controlled_ime_key_rule
- **compat**: 1 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['track:ime_keystream'] train_excl=['track:ime_keystream', 'unverified_ime_keystream'] review=['unverified_ime_keystream']

## 174. [ime_keystream/vni_raw_keys] `hnq10k-v3-09508`
- **query**: `bu7u d9ie6n5 du7o7ng no6i5`
- **clean_query**: `Bưu Điện Dương Nội`
- **POI**: Bưu Điện Dương Nội |  | amenity=post_office
- **split**: train | surface=raw_keys | gen=controlled_ime_key_rule
- **compat**: 1 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['track:ime_keystream'] train_excl=['track:ime_keystream', 'unverified_ime_keystream'] review=['unverified_ime_keystream']

## 175. [ime_keystream/ime_raw_keys] `hnq20k-v4-add-02231`
- **query**: `35 dduowngf hoof meex trif`
- **clean_query**: `35 đường hồ mễ trì`
- **POI**: 35 Đường Hồ Mễ Trì | 35 Đường Hồ Mễ Trì | address=
- **split**: train | surface=raw_keys | gen=rule_generated_ime
- **compat**: 1 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **mutation**: None → None ops=['telex_raw_encoding'] ime=telex
- **flags**: main_excl=['track_ime_keystream'] train_excl=['track_ime_keystream', 'ime_engine_unverified'] review=['ime_engine_unverified']

## 176. [structured_code/address_first] `hnq10k-v3-00735`
- **query**: `36 ngõ 85 sài đồng m`
- **clean_query**: `M 36 Ngõ 85 Sài Đồng`
- **POI**: M | 36 Ngõ 85 Sài Đồng Sài Đồng | building=yes
- **split**: train | surface=committed_text | gen=grounded_composition
- **compat**: 1 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['missing_sibling_address', 'track:structured_code'] train_excl=['missing_sibling_address', 'track:structured_code', 'structured_code_or_short_label'] review=['missing_sibling_address', 'structured_code_or_short_label']

## 177. [structured_code/address_namespace] `hnq20k-v4-add-01741`
- **query**: `ct6 43 phố hoàng quán chi`
- **clean_query**: `ct6 43 phố hoàng quán chi`
- **POI**: CT6 | 43 Phố Hoàng Quán Chi | building=apartments
- **split**: train | surface=committed_text | gen=grounded_field_composition
- **compat**: 1 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['track_structured_code', 'missing_address_sibling'] train_excl=['track_structured_code', 'missing_address_sibling'] review=['missing_address_sibling']

## 178. [structured_code/adjacent_transpose] `hnq10k-v3-01473`
- **query**: `hg5`
- **clean_query**: `GH5`
- **POI**: GH5 |  | building=apartments
- **split**: train | surface=committed_text | gen=controlled_typing_rule
- **compat**: 1 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **mutation**: gh5 → hg5 ops=None ime=None
- **flags**: main_excl=['track:structured_code'] train_excl=['track:structured_code', 'structured_code_or_short_label', 'namespace_not_in_query'] review=['structured_code_or_short_label', 'namespace_not_in_query']

## 179. [structured_code/clean_name] `hnq10k-v3-00766`
- **query**: `b11`
- **clean_query**: `B11`
- **POI**: B11 |  | building=apartments
- **split**: dev_synthetic | surface=committed_text | gen=grounded_composition
- **compat**: 3 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois', 'track:structured_code', 'cross_split_compatible', 'normalized_query_cross_split'] train_excl=['not_train_split', 'multiple_compatible_pois', 'track:structured_code', 'cross_split_compatible', 'normalized_query_cross_split', 'structured_code_or_short_label', 'namespace_not_in_query'] review=['multiple_compatible_pois', 'cross_split_compatible', 'normalized_query_cross_split', 'structured_code_or_short_label', 'namespace_not_in_query']

## 180. [structured_code/name_address] `hnq10k-v3-00722`
- **query**: `m 42 ngõ 85 sài đồng`
- **clean_query**: `M 42 Ngõ 85 Sài Đồng`
- **POI**: M | 42 Ngõ 85 Sài Đồng Sài Đồng | building=yes
- **split**: train | surface=committed_text | gen=grounded_composition
- **compat**: 1 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['missing_sibling_address', 'track:structured_code'] train_excl=['missing_sibling_address', 'track:structured_code', 'structured_code_or_short_label'] review=['missing_sibling_address', 'structured_code_or_short_label']

## 181. [structured_code/name_street] `hnq10k-v3-00725`
- **query**: `m ngõ 85 sài đồng`
- **clean_query**: `M`
- **POI**: M | 42 Ngõ 85 Sài Đồng Sài Đồng | building=yes
- **split**: train | surface=committed_text | gen=grounded_composition
- **compat**: 11 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois', 'missing_sibling_address', 'track:structured_code'] train_excl=['multiple_compatible_pois', 'missing_sibling_address', 'track:structured_code', 'structured_code_or_short_label', 'namespace_not_in_query'] review=['multiple_compatible_pois', 'missing_sibling_address', 'structured_code_or_short_label', 'namespace_not_in_query']

## 182. [structured_code/no_diacritics] `hnq10k-v3-01060`
- **query**: `thek2deluxe ngo 159 chua lang`
- **clean_query**: `TheK2Deluxe Ngõ 159 Chùa Láng`
- **POI**: TheK2Deluxe | Ngõ 159 Chùa Láng Láng Thượng | shop=shoes
- **split**: train | surface=committed_text | gen=controlled_typing_rule
- **compat**: 1 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['track:structured_code'] train_excl=['track:structured_code', 'structured_code_or_short_label'] review=['structured_code_or_short_label']

## 183. [structured_code/partial_diacritics] `hnq10k-v3-00593`
- **query**: `gs25 66 phô hà trung`
- **clean_query**: `GS25 66 Phố Hà Trung`
- **POI**: GS25 | 66 Phố Hà Trung | shop=convenience
- **split**: train | surface=committed_text | gen=controlled_typing_rule
- **compat**: 1 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['missing_sibling_address', 'track:structured_code'] train_excl=['missing_sibling_address', 'track:structured_code', 'structured_code_or_short_label'] review=['missing_sibling_address', 'structured_code_or_short_label']

## 184. [structured_code/prefix_1] `hnq10k-v3-00917`
- **query**: `m`
- **clean_query**: `M`
- **POI**: MB |  | amenity=atm
- **split**: test_synthetic | surface=committed_text | gen=controlled_typing_rule
- **compat**: 778 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois', 'track:structured_code', 'cross_split_compatible', 'normalized_query_cross_split'] train_excl=['not_train_split', 'multiple_compatible_pois', 'track:structured_code', 'cross_split_compatible', 'normalized_query_cross_split', 'unfinished_prefix', 'structured_code_or_short_label', 'namespace_not_in_query'] review=['multiple_compatible_pois', 'unfinished_prefix', 'cross_split_compatible', 'normalized_query_cross_split', 'structured_code_or_short_label', 'namespace_not_in_query']

## 185. [structured_code/prefix_2] `hnq10k-v3-00497`
- **query**: `n4`
- **clean_query**: `N4`
- **POI**: N4D | Đường Lê Văn Lương Nhân Chính | building=apartments
- **split**: dev_synthetic | surface=committed_text | gen=controlled_typing_rule
- **compat**: 6 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois', 'track:structured_code', 'cross_split_compatible', 'normalized_query_cross_split'] train_excl=['not_train_split', 'multiple_compatible_pois', 'track:structured_code', 'cross_split_compatible', 'normalized_query_cross_split', 'unfinished_prefix', 'structured_code_or_short_label', 'namespace_not_in_query'] review=['multiple_compatible_pois', 'unfinished_prefix', 'cross_split_compatible', 'normalized_query_cross_split', 'structured_code_or_short_label', 'namespace_not_in_query']

## 186. [structured_code/prefix_3] `hnq10k-v3-00697`
- **query**: `245`
- **clean_query**: `245`
- **POI**: 2457 |  | amenity=atm
- **split**: train | surface=committed_text | gen=controlled_typing_rule
- **compat**: 9 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois', 'track:structured_code'] train_excl=['multiple_compatible_pois', 'track:structured_code', 'unfinished_prefix', 'structured_code_or_short_label', 'namespace_not_in_query'] review=['multiple_compatible_pois', 'unfinished_prefix', 'structured_code_or_short_label', 'namespace_not_in_query']

## 187. [structured_code/search_phrase] `hnq10k-v3-04460`
- **query**: `đến 175`
- **clean_query**: `175`
- **POI**: 175 |  | amenity=atm
- **split**: train | surface=committed_text | gen=grounded_composition
- **compat**: 30 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois', 'track:structured_code', 'cross_split_compatible'] train_excl=['multiple_compatible_pois', 'track:structured_code', 'cross_split_compatible', 'structured_code_or_short_label', 'namespace_not_in_query'] review=['multiple_compatible_pois', 'cross_split_compatible', 'structured_code_or_short_label', 'namespace_not_in_query']

## 188. [structured_code/slash_alley_address] `hnq20k-v4-add-00983`
- **query**: `workshop14 6 ngõ 5 phố từ hoa`
- **clean_query**: `workshop14 6 ngõ 5 phố từ hoa`
- **POI**: Workshop14 | 6 Ngõ 5 Phố Từ Hoa Quảng An | amenity=bar
- **split**: architecture_holdout | surface=committed_text | gen=grounded_field_composition
- **compat**: 1 | train_elig=False | main_metric=False
- **label**: weak_unique_under_matching_policy / not_guaranteed | requires_review=False
- **flags**: main_excl=['track_structured_code'] train_excl=['track_structured_code', 'not_train_split'] review=[]

## 189. [structured_code/structured_code] `hnq20k-v4-add-00181`
- **query**: `e2`
- **clean_query**: `e2`
- **POI**: E2 |  | building=apartments
- **split**: train | surface=committed_text | gen=grounded_field_composition
- **compat**: 12 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['track_structured_code', 'multiple_known_compatible', 'cross_split_compatible'] train_excl=['track_structured_code', 'multiple_known_compatible', 'cross_split_compatible', 'namespace_not_in_query'] review=['multiple_known_compatible', 'namespace_not_in_query']

## 190. [structured_code/wrong_tone] `hnq10k-v3-09912`
- **query**: `d dd ngó 151 phố lê văn hiến`
- **clean_query**: `d dd Ngõ 151 Phố Lê Văn Hiến`
- **POI**: d | dd Ngõ 151 Phố Lê Văn Hiến Đức Thắng | amenity=restaurant
- **split**: train | surface=committed_text | gen=controlled_typing_rule
- **compat**: 1 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['missing_sibling_address', 'track:structured_code'] train_excl=['missing_sibling_address', 'track:structured_code', 'structured_code_or_short_label'] review=['missing_sibling_address', 'structured_code_or_short_label']

## 191. [structured_code/address_first] `hnq10k-v3-00250`
- **query**: `phố trần hữu dực ct2`
- **clean_query**: `CT2 Phố Trần Hữu Dực`
- **POI**: CT2 | Phố Trần Hữu Dực | building=apartments
- **split**: dev_synthetic | surface=committed_text | gen=grounded_composition
- **compat**: 1 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['missing_sibling_address', 'track:structured_code'] train_excl=['not_train_split', 'missing_sibling_address', 'track:structured_code', 'structured_code_or_short_label'] review=['missing_sibling_address', 'structured_code_or_short_label']

## 192. [structured_code/adjacent_transpose] `hnq10k-v3-00288`
- **query**: `tc5b`
- **clean_query**: `CT5B`
- **POI**: CT5B |  | building=apartments
- **split**: test_synthetic | surface=committed_text | gen=controlled_typing_rule
- **compat**: 3 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **mutation**: ct5b → tc5b ops=None ime=None
- **flags**: main_excl=['multiple_compatible_pois', 'track:structured_code', 'cross_split_compatible'] train_excl=['not_train_split', 'multiple_compatible_pois', 'track:structured_code', 'cross_split_compatible', 'structured_code_or_short_label', 'namespace_not_in_query'] review=['multiple_compatible_pois', 'cross_split_compatible', 'structured_code_or_short_label', 'namespace_not_in_query']

## 193. [structured_code/clean_name] `hnq10k-v3-00611`
- **query**: `ct1`
- **clean_query**: `CT1`
- **POI**: CT1 |  | building=apartments
- **split**: train | surface=committed_text | gen=grounded_composition
- **compat**: 59 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois', 'track:structured_code', 'cross_split_compatible'] train_excl=['multiple_compatible_pois', 'track:structured_code', 'cross_split_compatible', 'structured_code_or_short_label', 'namespace_not_in_query'] review=['multiple_compatible_pois', 'cross_split_compatible', 'structured_code_or_short_label', 'namespace_not_in_query']

## 194. [structured_code/name_address] `hnq10k-v3-01454`
- **query**: `ct10a đường phan trọng tuệ`
- **clean_query**: `CT10A Đường Phan Trọng Tuệ`
- **POI**: CT10A | CT10A Đường Phan Trọng Tuệ Đại Thanh | building=apartments
- **split**: train | surface=committed_text | gen=grounded_composition
- **compat**: 1 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['track:structured_code'] train_excl=['track:structured_code', 'structured_code_or_short_label'] review=['structured_code_or_short_label']

## 195. [structured_code/no_diacritics] `hnq10k-v3-00723`
- **query**: `m 42 ngo 85 sai dong`
- **clean_query**: `M 42 Ngõ 85 Sài Đồng`
- **POI**: M | 42 Ngõ 85 Sài Đồng Sài Đồng | building=yes
- **split**: train | surface=committed_text | gen=controlled_typing_rule
- **compat**: 1 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['missing_sibling_address', 'track:structured_code'] train_excl=['missing_sibling_address', 'track:structured_code', 'structured_code_or_short_label'] review=['missing_sibling_address', 'structured_code_or_short_label']

## 196. [structured_code/partial_diacritics] `hnq10k-v3-01368`
- **query**: `n4b đương lê văn lương`
- **clean_query**: `N4B Đường Lê Văn Lương`
- **POI**: N4B | Đường Lê Văn Lương Nhân Chính | building=apartments
- **split**: dev_synthetic | surface=committed_text | gen=controlled_typing_rule
- **compat**: 1 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['track:structured_code'] train_excl=['not_train_split', 'track:structured_code', 'structured_code_or_short_label'] review=['structured_code_or_short_label']

## 197. [structured_code/prefix_1] `hnq10k-v3-00797`
- **query**: `a`
- **clean_query**: `A`
- **POI**: A6 |  | leisure=sports_centre
- **split**: test_synthetic | surface=committed_text | gen=controlled_typing_rule
- **compat**: 890 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois', 'track:structured_code', 'cross_split_compatible', 'normalized_query_cross_split'] train_excl=['not_train_split', 'multiple_compatible_pois', 'track:structured_code', 'cross_split_compatible', 'normalized_query_cross_split', 'unfinished_prefix', 'structured_code_or_short_label', 'namespace_not_in_query'] review=['multiple_compatible_pois', 'unfinished_prefix', 'cross_split_compatible', 'normalized_query_cross_split', 'structured_code_or_short_label', 'namespace_not_in_query']

## 198. [structured_code/prefix_2] `hnq10k-v3-05432`
- **query**: `a1`
- **clean_query**: `A1`
- **POI**: A19 |  | amenity=clinic
- **split**: train | surface=committed_text | gen=controlled_typing_rule
- **compat**: 97 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois', 'track:structured_code', 'cross_split_compatible'] train_excl=['multiple_compatible_pois', 'track:structured_code', 'cross_split_compatible', 'unfinished_prefix', 'structured_code_or_short_label', 'namespace_not_in_query'] review=['multiple_compatible_pois', 'unfinished_prefix', 'cross_split_compatible', 'structured_code_or_short_label', 'namespace_not_in_query']

## 199. [structured_code/prefix_3] `hnq10k-v3-00287`
- **query**: `ct5`
- **clean_query**: `CT5`
- **POI**: CT5B |  | building=apartments
- **split**: test_synthetic | surface=committed_text | gen=controlled_typing_rule
- **compat**: 20 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois', 'track:structured_code', 'cross_split_compatible'] train_excl=['not_train_split', 'multiple_compatible_pois', 'track:structured_code', 'cross_split_compatible', 'unfinished_prefix', 'structured_code_or_short_label', 'namespace_not_in_query'] review=['multiple_compatible_pois', 'unfinished_prefix', 'cross_split_compatible', 'structured_code_or_short_label', 'namespace_not_in_query']

## 200. [structured_code/search_phrase] `hnq10k-v3-00944`
- **query**: `địa chỉ b3`
- **clean_query**: `B3`
- **POI**: B3 |  | building=yes
- **split**: train | surface=committed_text | gen=grounded_composition
- **compat**: 24 | train_elig=False | main_metric=False
- **label**: weak_review_required / not_guaranteed | requires_review=True
- **flags**: main_excl=['multiple_compatible_pois', 'track:structured_code'] train_excl=['multiple_compatible_pois', 'track:structured_code', 'structured_code_or_short_label', 'namespace_not_in_query'] review=['multiple_compatible_pois', 'structured_code_or_short_label', 'namespace_not_in_query']

