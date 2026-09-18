# W1-02 POI EDA — Vietnam `pois_core` (vn-poi-core-v1)

Chạy: `2026-09-16T03:38:53Z` · N=186,322 · file `pois_core.parquet` (sha12 `e5d75c4783f2`).

Universe chính = toàn bộ `pois_core` (= destination_searchable trong build này).
Same-name = ambiguity cho tới khi có bằng chứng cùng thực thể. Near-dup = ứng viên, chưa collapse.

## Metrics (n/N)

| metric | n | N | rate | universe |
| --- | ---: | ---: | ---: | --- |
| rows | 186322 | 186322 | 1.0 | pois_core |
| poi_id_unique | 186322 | 186322 | 1.0 | pois_core |
| duplicate_poi_id_rows | 0 | 186322 | 0.0 | pois_core |
| empty_name | 0 | 186322 | 0.0 | pois_core |
| with_alias | 14216 | 186322 | 0.076298 | pois_core |
| missing_ranking_point | 0 | 186322 | 0.0 | pois_core |
| invalid_latlon | 0 | 186322 | 0.0 | pois_core |
| outside_vn_bbox | 31 | 186322 | 0.000166 | pois_core |
| address_status_missing | 98062 | 186322 | 0.526304 | pois_core |
| address_status_direct | 88260 | 186322 | 0.473696 | pois_core |
| housenumber_and_street_or_place | 77190 | 186322 | 0.414283 | pois_core |
| subdistrict_missing | 490 | 186322 | 0.00263 | pois_core |
| province_unknown | 333 | 186322 | 0.001787 | pois_core |
| with_brand | 8952 | 186322 | 0.048046 | pois_core |
| with_ref | 625 | 186322 | 0.003354 | pois_core |
| preserve_individual_access_point | 15674 | 186322 | 0.084123 | pois_core |
| category_public_transport_platform_or_stop | 15729 | 186322 | 0.084418 | pois_core |
| category_unknown | 0 | 186322 | 0.0 | pois_core |
| folded_name_groups_size_ge_2 | 13312 | 147946 | 0.089979 | distinct_folded_names |
| pois_in_folded_name_groups_ge_2 | 51688 | 186322 | 0.277412 | named_pois |
| folded_name_province_groups_ge_2 | 11913 | 157668 | 0.075558 | distinct_folded_name_x_province |
| near_dup_pairs_same_fold_le_80m_excl_huge_groups | 8823 |  |  | pair_count_heuristic |
| node_way_same_fold_pairs_le_80m | 1508 |  |  | pair_count_heuristic |

## OSM type

| type | n |
| --- | ---: |
| node | 122389 |
| way | 63933 |

## Language heuristic (name)

| bucket | n |
| --- | ---: |
| vi_diacritic | 134129 |
| latin_no_vi_diacritic | 48722 |
| has_digit | 3310 |
| other | 161 |

## Category top 30 (first token)

| category | n |
| --- | ---: |
| address= | 51563 |
| public_transport=platform | 15304 |
| amenity=restaurant | 10704 |
| amenity=cafe | 8255 |
| amenity=school | 7858 |
| amenity=place_of_worship | 6209 |
| shop=convenience | 6128 |
| tourism=hotel | 5664 |
| building=yes | 4069 |
| amenity=fuel | 3627 |
| amenity=atm | 3086 |
| building=apartments | 2858 |
| amenity=bank | 2429 |
| office=government | 2417 |
| amenity=pharmacy | 2341 |
| amenity=hospital | 1748 |
| tourism=guest_house | 1732 |
| amenity=kindergarten | 1558 |
| amenity=marketplace | 1496 |
| shop=clothes | 1484 |
| leisure=park | 1391 |
| amenity=fast_food | 1380 |
| amenity=community_centre | 1322 |
| tourism=attraction | 1290 |
| shop=supermarket | 1265 |
| shop=department_store | 1083 |
| office=company | 1066 |
| tourism=hostel | 986 |
| amenity=townhall | 950 |
| amenity=police | 900 |

## Top ambiguous folded names (global)

| folded_name | n_pois | examples |
| --- | ---: | --- |
| winmart+ | 1221 | osm:node/729406837, osm:node/1769477893, osm:node/4239089490, osm:node/4384877966, osm:node/4531037510 |
| petrolimex | 1119 | osm:node/446043006, osm:node/481837948, osm:node/481838137, osm:node/729604368, osm:node/729604588 |
| a | 664 | osm:node/4965375262, osm:node/4965375266, osm:node/4965375268, osm:node/4965375270, osm:node/4965375275 |
| bidv | 511 | osm:node/444394820, osm:node/444394977, osm:node/445275063, osm:node/446043809, osm:node/724828979 |
| agribank | 445 | osm:node/444394841, osm:node/444395022, osm:node/446044157, osm:node/481836260, osm:node/481836277 |
| sua xe | 435 | osm:node/4744465824, osm:node/12378510161, osm:node/12385051620, osm:node/12701542472, osm:node/12701549418 |
| vietcombank | 404 | osm:node/444227294, osm:node/444395007, osm:node/444668652, osm:node/446044221, osm:node/448841326 |
| pv oil | 366 | osm:node/729787624, osm:node/977780862, osm:node/1021091948, osm:node/1021091954, osm:node/1024567385 |
| techcombank | 331 | osm:node/443064263, osm:node/444394919, osm:node/481837601, osm:node/724828983, osm:node/724829024 |
| vietinbank | 330 | osm:node/444394786, osm:node/444394867, osm:node/444394975, osm:node/446044219, osm:node/481836344 |
| vinfast | 266 | osm:node/9424945491, osm:node/10023518306, osm:node/10310391815, osm:node/10916618777, osm:node/11171092437 |
| highlands coffee | 258 | osm:node/442977691, osm:node/729406744, osm:node/1710192560, osm:node/1969579862, osm:node/1970245474 |
| pnj | 242 | osm:node/3227626772, osm:node/3630424393, osm:node/3640168116, osm:node/3654066981, osm:node/5251604549 |
| sacombank | 218 | osm:node/724829060, osm:node/724829136, osm:node/724829296, osm:node/724829676, osm:node/724829703 |
| circle k | 211 | osm:node/724829580, osm:node/729604579, osm:node/1276258190, osm:node/1933276047, osm:node/1969579596 |
| bach hoa xanh | 207 | osm:node/5606336360, osm:node/5638025421, osm:node/6326608156, osm:node/6370262588, osm:node/7063598056 |
| cua hang xang dau | 168 | osm:node/729604638, osm:node/11445725144, osm:node/11445811761, osm:node/11445833346, osm:node/11445895640 |
| tu doi pin vinfast | 156 | osm:node/13658912837, osm:node/13658912838, osm:node/13658912839, osm:node/13658912840, osm:node/13658912841 |
| winmart | 133 | osm:node/442977400, osm:node/1778803400, osm:node/1817686618, osm:node/2647229839, osm:node/3150526966 |
| tpbank livebank 24/7 | 126 | osm:node/1491048057, osm:node/10111821018, osm:node/12022604275, osm:node/12212544801, osm:node/12694082687 |
| acb | 124 | osm:node/724829156, osm:node/724829528, osm:node/724829567, osm:node/724829772, osm:node/724829862 |
| lotteria | 118 | osm:node/411918020, osm:node/729602633, osm:node/729602639, osm:node/729602662, osm:node/729602674 |
| vpbank | 108 | osm:node/446044135, osm:node/724829072, osm:node/724829160, osm:node/948325230, osm:node/1001774342 |
| ks, a | 101 | osm:node/5151193584, osm:node/5158659074, osm:node/5158659076, osm:node/5162759222, osm:node/5162759226 |
| kfc | 98 | osm:node/442913494, osm:node/481837568, osm:node/729602658, osm:node/729602660, osm:node/729602661 |
| pharmacity | 97 | osm:node/4559392591, osm:node/4965375504, osm:node/4991619470, osm:node/6758069582, osm:node/6770462388 |
| tap hoa | 95 | osm:node/4682943494, osm:node/4684692789, osm:node/4684711291, osm:node/4691616905, osm:node/4691715091 |
| the gioi di dong | 88 | osm:node/1778803900, osm:node/1783186913, osm:node/1810772439, osm:node/2494712806, osm:node/2494715831 |
| the coffee house | 77 | osm:node/946794525, osm:node/1769692429, osm:node/3247376711, osm:node/4274832592, osm:node/4274858294 |
| starbucks | 74 | osm:node/2141010788, osm:node/2340161840, osm:node/2616958820, osm:node/2616975924, osm:node/3193184663 |

## Near-dup sample (heuristic)

Pairs same-fold ≤80 m (groups size≤80): **8823**; node–way trong đó: **1508**.

| kind | fold | poi_a | poi_b | distance_m |
| --- | --- | --- | --- | ---: |
| same_fold_le_25m | gia lam | osm:node/2685835182 | osm:node/11279662341 | 7.1 |
| same_fold_le_25m | gia lam | osm:node/2685835182 | osm:node/11279662342 | 11.5 |
| same_fold_le_25m | gia lam | osm:node/11279662341 | osm:node/11279662342 | 4.4 |
| same_fold_le_25m | ubnd phuong 17 | osm:node/366459518 | osm:node/11868138118 | 22.5 |
| same_fold_le_25m | long bien | osm:node/445345254 | osm:node/11260029394 | 7.9 |
| same_fold_le_25m | vib | osm:node/4547532453 | osm:node/4547532455 | 13.3 |
| same_fold_le_25m | vib | osm:node/7056059367 | osm:node/10816361965 | 10.9 |
| same_fold_le_25m | vib | osm:node/7056059373 | osm:node/7056059374 | 2.5 |
| same_fold_le_25m | vib | osm:node/11104600818 | osm:node/11104600821 | 4.8 |
| same_fold_le_25m | mb bank | osm:node/2450217638 | osm:node/5344389829 | 4.5 |
| same_fold_le_25m | lpbank | osm:node/12615337071 | osm:node/12615337073 | 1.5 |
| node_way | lpbank | osm:node/13634068277 | osm:way/1487234665 | 2.1 |
| node_way | cho duong dong | osm:node/477604691 | osm:way/1328291798 | 68.0 |
| node_way | vcb | osm:node/4605036483 | osm:way/369836850 | 8.3 |
| same_fold_le_25m | hsbc | osm:node/2256217983 | osm:node/4764044322 | 17.2 |
| same_fold_le_25m | hsbc | osm:node/4603126389 | osm:node/5311889621 | 9.4 |
| same_fold_le_25m | hsbc | osm:node/6991435285 | osm:node/7575207786 | 4.0 |
| same_fold_le_25m | thap cham | osm:node/667360878 | osm:node/11196150538 | 23.7 |
| same_fold_le_25m | tuy hoa | osm:node/6576385313 | osm:node/6576385473 | 5.3 |
| same_fold_le_25m | tuy hoa | osm:node/6576385313 | osm:node/7631626345 | 6.7 |
| same_fold_le_25m | tuy hoa | osm:node/6576385313 | osm:node/7631637538 | 11.4 |
| same_fold_le_25m | tuy hoa | osm:node/6576385313 | osm:node/7631672207 | 23.7 |
| same_fold_le_25m | tuy hoa | osm:node/6576385473 | osm:node/7631626345 | 11.9 |
| same_fold_le_25m | tuy hoa | osm:node/6576385473 | osm:node/7631637538 | 6.2 |
| same_fold_le_25m | tuy hoa | osm:node/6576385473 | osm:node/7631662050 | 23.2 |

## Province distribution

| province | n |
| --- | ---: |
| Thành phố Hồ Chí Minh | 53186 |
| Hà Nội | 46692 |
| Thành phố Đà Nẵng | 14598 |
| Thành phố Bắc Ninh | 10396 |
| Tỉnh Lâm Đồng | 6751 |
| Thành phố Cần Thơ | 5594 |
| Thành phố Đồng Nai | 5266 |
| Thành phố Hải Phòng | 4555 |
| Khánh Hòa | 4344 |
| Tỉnh An Giang | 4123 |
| Thành phố Huế | 2390 |
| Tỉnh Ninh Bình | 2286 |
| Tỉnh Hưng Yên | 2133 |
| Tỉnh Tây Ninh | 2132 |
| Tỉnh Đắk Lắk | 2099 |
| Tỉnh Gia Lai | 2074 |
| Tỉnh Đồng Tháp | 1900 |
| Tỉnh Quảng Trị | 1756 |
| Tỉnh Lào Cai | 1623 |
| Tỉnh Vĩnh Long | 1540 |
| Tỉnh Tuyên Quang | 1409 |
| Tỉnh Quảng Ngãi | 1272 |
| Thành phố Quảng Ninh | 1244 |
| Tỉnh Phú Thọ | 1137 |
| Tỉnh Nghệ An | 840 |
| Hà Tĩnh | 807 |
| Tỉnh Thanh Hóa | 766 |
| Tỉnh Thái Nguyên | 754 |
| Tỉnh Cao Bằng | 525 |
| Tỉnh Lạng Sơn | 402 |
| Tỉnh Cà Mau | 382 |
| Tỉnh Lai Châu | 363 |
| Tỉnh Sơn La | 347 |
| (unknown) | 333 |
| Tỉnh Điện Biên | 303 |

## Kết luận ngắn

- ID unique: True; tọa độ thiếu/invalid: 0/0; ngoài bbox VN: 31.
- Address missing: 98,062/186,322 (52.6%).
- Folded same-name groups ≥2: 13,312 / 147,946 tên; ảnh hưởng 51,688 POI.
- Ứng viên node–way gần (≤80 m, cùng fold): 1508 cặp — cần pass dedup trước canonical.
- Không suy pickup/routing; access assumed per core schema.
