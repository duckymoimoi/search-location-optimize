# mE5 miss cases — độ dài query và top hits

Giả thuyết: query càng dài càng dễ. Dưới đây là R theo bucket độ dài + toàn bộ miss@100 của mE5 kèm top-10 dense/BM25 để đọc tay.

## 1. Phân bố độ dài (toàn gold)

n=1080 · min=11 · p50=32 · mean=31.7 · max=56

Spearman(char_len, mE5_rank) = **-0.066** (âm = dài hơn → rank tốt hơn)
Spearman(char_len, BM25_rank) = **-0.148**

## 2. Recall mE5 theo bucket độ dài (ký tự)

| char_len | n | R@10 | R@100 | R@1000 |
|---|---:|---:|---:|---:|
| (0, 15] | 26 | 1.000 | 1.000 | 1.000 |
| (15, 20] | 47 | 0.957 | 0.957 | 0.979 |
| (20, 25] | 157 | 0.924 | 0.975 | 0.981 |
| (25, 30] | 205 | 0.912 | 0.971 | 0.990 |
| (30, 35] | 307 | 0.925 | 0.958 | 0.984 |
| (35, 40] | 211 | 0.938 | 0.976 | 1.000 |
| (40, 60] | 127 | 0.929 | 0.969 | 1.000 |

## 3. Miss rate: ngắn vs dài

- **len≤20**: n=73 · miss@10=2 (2.7%) · miss@100=2 (2.7%)
- **len>20**: n=1007 · miss@10=75 (7.4%) · miss@100=32 (3.2%)
- **len≤25**: n=230 · miss@10=14 (6.1%) · miss@100=6 (2.6%)
- **len>25**: n=850 · miss@10=63 (7.4%) · miss@100=28 (3.3%)
- **len≤30**: n=435 · miss@10=32 (7.4%) · miss@100=12 (2.8%)
- **len>30**: n=645 · miss@10=45 (7.0%) · miss@100=22 (3.4%)

Mean len — miss@100: **31.6** · hit@100: **31.7** · overall: **31.7**
Mean tokens — miss@100: **7.5** · hit@100: **6.8**

## 4. Toàn bộ mE5 miss@100 (34 queries) — sort theo độ dài tăng dần

(Miss@10 = 77 queries — xem JSON examples nếu cần; dưới đây đủ sâu để đọc pattern.)

### `g150-149-v3` · len=17 · tokens=5 · dense_rank=1001 · lex_rank=777
- **query:** `BX Long An Tân An`
- family=`ALIAS` · operator=`abbreviation` · stratum=`code_transit_landmark`
- **target:** Bến xe Long An [osm:node/4452037189]
- **mE5 top-10:**
  1. BCEL —  [osm:node/4679739195]
  2. Sokimex —  [osm:node/7114360785]
  3. Savimex —  [osm:node/2633372214]
  4. Tela —  [osm:node/2633372215]
  5. TH-Bình Bắc - -Tân Long- phú giáo-Bình dương-0984672030 — Xã An Long, Thành phố Hồ Chí Minh [osm:node/7651043286]
  6. BDVHX Minh Tân — Xã Trung Chính, Thành phố Bắc Ninh [osm:way/419360416]
  7. ABA Bank —  [osm:node/5374919961]
  8. Qua BX Thường Tín 50m - Quốc Lộ 1A — Xã Hồng Vân, Hà Nội [osm:node/9024366572]
  9. Tanong Restaurant —  [osm:node/4940205821]
  10. Caltex —  [osm:node/12627999501]
- **BM25 top-10:**
  1. Chợ Long An — Xã Tân An, Tỉnh An Giang [osm:node/1813632282]
  2. TÂN TRUNG — Xã An Định, Tỉnh Vĩnh Long [osm:node/4758805139]
  3. Chi cục Thuế khu vực Tân Châu - An Phú — Phường Long Phú, Tỉnh An Giang [osm:way/1117144788]
  4. Nhà thi đấu Tân Châu — Phường Long Phú, Tỉnh An Giang [osm:way/1117144787]
  5. Mì cay Korea — Tán Kế, Phường An Hội, Tỉnh Vĩnh Long [osm:node/4105656289]
  6. VPP Bến Tre — 22A, Tán Kế, Phường An Hội, Tỉnh Vĩnh Long [osm:node/14077854184]
  7. KDL Trường An — Phường Tân Ngãi, Tỉnh Vĩnh Long [osm:way/1126965453]
  8. Honda Ôtô Long An - Tân An — 86 tuyến tránh, Quốc lộ 1, Phường Long An, Tỉnh Tây Ninh [osm:node/6088277986]
  9. Trung tâm Hành chính Công TX. Tân Châu — Phường Long Phú, Tỉnh An Giang [osm:way/1117144789]
  10. Chợ Thành An — Xã Tân Thành Bình, Tỉnh Vĩnh Long [osm:node/10806683345]

### `g150-059-v2` · len=18 · tokens=5 · dense_rank=530 · lex_rank=1
- **query:** `Pho ga Lam Lang Ha`
- family=`ORTHOGRAPHIC_IME` · operator=`strip_diacritics` · stratum=`named_clear`
- **target:** Phở gà Lâm [osm:way/1365472868]
- **mE5 top-10:**
  1. Tela —  [osm:node/2633372215]
  2. papa ratanakiri —  [osm:node/7103925986]
  3. DAGA —  [osm:way/1075962699]
  4. Thuy lam. (Com pho 30k) — Phường Mộc Châu, Tỉnh Sơn La [osm:node/6282092386]
  5. Svay Ah Ngoung —  [osm:node/4710985991]
  6. pho — Phường B'Lao, Tỉnh Lâm Đồng [osm:node/13584878502]
  7. pho — Phường B'Lao, Tỉnh Lâm Đồng [osm:node/13584879001]
  8. Best Pho ever! — Xã Ninh Gia, Tỉnh Lâm Đồng [osm:node/5475229423]
  9. Sokimex —  [osm:node/7114360785]
  10. Pho — Phường Xuân Hương - Đà Lạt, Tỉnh Lâm Đồng [osm:node/13590797402]
- **BM25 top-10:**
  1. Phở gà Lâm — 26, Phố Láng Hạ, Phường Láng, Hà Nội [osm:way/1365472868] <<TARGET
  2. Ga Lăng Cô — Xã Chân Mây - Lăng Cô, Thành phố Huế [osm:way/1275244614]
  3. Cơm Lam Gà nướng Tuyết Hoa — Phường Lang Biang - Đà Lạt, Tỉnh Lâm Đồng [osm:node/7234583385]
  4. Thịt nướng, gà nướng... — Phường Lang Biang - Đà Lạt, Tỉnh Lâm Đồng [osm:node/10692396808]
  5. Cơm gà Linh Chi — 8243+PFJ, Chân Mây, Cảnh Dương, Phú Lộc, Thành phố Huế, Xã Chân Mây -  [osm:node/12566747824]
  6. Ga Lang — Phường Vũng Tàu, Thành phố Hồ Chí Minh [osm:node/4547815941]
  7. Làng Bên Phô — 40, Xô Viết Nghệ Tỉnh, Phường Lang Biang - Đà Lạt, Tỉnh Lâm Đồng [osm:node/13056561502]
  8. Ga Lạng Sơn — Phường Đông Kinh, Tỉnh Lạng Sơn [osm:way/1207689406]
  9. Phở Gà - Hủ Tíu Gà — 47, Phố Yên Phụ, Phường Tây Hồ, Hà Nội [osm:node/14144385001]
  10. Ga Láng — Phường Đống Đa, Hà Nội [osm:way/512285540]

### `g150-162-v4` · len=22 · tokens=5 · dense_rank=1001 · lex_rank=1001
- **query:** `Keangnam Hà Nội Mễ Trì`
- family=`ALIAS` · operator=`name_area` · stratum=`building_code`
- **target:** Landmark72 [osm:way/1327061631]
- **mE5 top-10:**
  1. 45, Đường Mễ Trì — 45, Đường Mễ Trì, Phường Từ Liêm, Hà Nội [osm:node/12880386052]
  2. Ký túc xá Mễ Trì - Đại học Quốc gia Hà Nội — 182, Đường Lương Thế Vinh, Phường Thanh Xuân, Hà Nội [osm:way/736412443]
  3. Mễ Trì Park Playground — Phường Từ Liêm, Hà Nội [osm:way/1328336052]
  4. KINH DOANH — 50, Đường Mễ Trì, Phường Từ Liêm, Hà Nội [osm:node/8334779805]
  5. Golden Palace — Đường Mễ Trì, Phường Từ Liêm, Hà Nội [osm:way/1148733021]
  6. Trường Tiểu học Mễ Trì — Phường Từ Liêm, Hà Nội [osm:way/976255151]
  7. 50, Đường Mễ Trì — 50, Đường Mễ Trì, Phường Từ Liêm, Hà Nội [osm:node/6685466398]
  8. Chợ Mễ Trì — Ngõ 32 Đỗ Đức Dục, Phường Từ Liêm, Hà Nội [osm:node/12177717116]
  9. 27, Đường Hồ Mễ Trì — 27, Đường Hồ Mễ Trì, Phường Đại Mỗ, Hà Nội [osm:node/6677690284]
  10. Công viên Mễ Trì — Phường Từ Liêm, Hà Nội [osm:way/889113701]
- **BM25 top-10:**
  1. Đình Làng Mễ Trì Hạ — Mễ Trì Hạ, Phường Từ Liêm, Hà Nội [osm:way/412784309]
  2. 16, Phố Mễ Trì Thượng — 16, Phố Mễ Trì Thượng, Phường Từ Liêm, Hà Nội [osm:node/13340704390]
  3. 14, Phố Mễ Trì Thượng — 14, Phố Mễ Trì Thượng, Phường Từ Liêm, Hà Nội [osm:node/13340704389]
  4. 244, Phố Mễ Trì Thượng — 244, Phố Mễ Trì Thượng, Phường Từ Liêm, Hà Nội [osm:node/12880386071]
  5. Trường mầm non Mễ Trì — Tổ dân phố số 5 Mễ Trì Thượng, Phường Từ Liêm, Hà Nội [osm:node/12213825778]
  6. A312-BT1B, khu đô thị Mễ Trì Thượng — A312-BT1B, khu đô thị Mễ Trì Thượng, Phường Từ Liêm, Hà Nội [osm:node/13563828510]
  7. KFC Manor Mê Trì | KFC — Mễ Trì, Phường Từ Liêm, Hà Nội [osm:node/4554131889]
  8. 45, Đường Mễ Trì — 45, Đường Mễ Trì, Phường Từ Liêm, Hà Nội [osm:node/12880386052]
  9. 43, Đường Mễ Trì — 43, Đường Mễ Trì, Phường Từ Liêm, Hà Nội [osm:node/12880386053]
  10. 50, Đường Mễ Trì — 50, Đường Mễ Trì, Phường Từ Liêm, Hà Nội [osm:node/6685466398]

### `g150-058-v2` · len=24 · tokens=6 · dense_rank=1001 · lex_rank=1
- **query:** `Nha co Phung Hung Hoi An`
- family=`ORTHOGRAPHIC_IME` · operator=`strip_diacritics` · stratum=`named_clear`
- **target:** Nhà cổ Phùng Hưng [osm:node/4279640089]
- **mE5 top-10:**
  1. Nha hang hong phuong Cam thuy — Xã Cẩm Thủy, Tỉnh Thanh Hóa [osm:node/5521835921]
  2. Nha Hang Nam Chau Hoi Quan — Phường Kim Long, Thành phố Huế [osm:node/4401294793]
  3. Nha Tro —  [osm:node/4679748690]
  4. nha hang hoan my — Phường Hà Tiên, Tỉnh An Giang [osm:node/4231398694]
  5. Nha Nghi —  [osm:node/4679748689]
  6. Nha hang tiec cuoi Kim Son 1 — Hương lộ 5, Xã Long Hải, Thành phố Hồ Chí Minh [osm:node/5160214021]
  7. Nha Hang Com Nieu Hong Phuc 3 — Xã Bà Nà, Thành phố Đà Nẵng [osm:node/4401168602]
  8. TH-Chị Nhung - -Kỉnh Nhượng-Xã Vĩnh Hoà-Phú Giáo-0974784539 — Xã Phước Hòa, Thành phố Hồ Chí Minh [osm:node/7583684385]
  9. Nha Hang Bien Ngoc — QL1A, Phường Sa Huỳnh, Tỉnh Quảng Ngãi [osm:node/4443759489]
  10. Nha nghí — Xã Púng Luông, Tỉnh Lào Cai [osm:node/4557807491]
- **BM25 top-10:**
  1. Nhà cổ Phùng Hưng — 4, Nguyễn Thị Minh Khai, Phường Hội An, Thành phố Đà Nẵng [osm:node/4279640089] <<TARGET
  2. Rừng Cọ E — Xã Phụng Công, Tỉnh Hưng Yên [osm:way/875184371]
  3. Rừng Cọ A — Xã Phụng Công, Tỉnh Hưng Yên [osm:way/875184367]
  4. Rừng Cọ D — Xã Phụng Công, Tỉnh Hưng Yên [osm:way/875184370]
  5. Rừng Cọ B — Xã Phụng Công, Tỉnh Hưng Yên [osm:way/875184368]
  6. Rừng Cọ C — Xã Phụng Công, Tỉnh Hưng Yên [osm:way/875184369]
  7. Trước Y học cổ truyền Đại hữu xã Phụng Công — Xã Phụng Công, Tỉnh Hưng Yên [osm:node/8919736486]
  8. Vườn Tùng - Rừng Cọ — Xã Phụng Công, Tỉnh Hưng Yên [osm:node/11525014913]
  9. Đối diện A2 Rừng Cọ — Xã Phụng Công, Tỉnh Hưng Yên [osm:node/11525014912]
  10. Siêu thị Citimart - Rừng Cọ — Xã Phụng Công, Tỉnh Hưng Yên [osm:node/11525014915]

### `g150-082-v2` · len=25 · tokens=6 · dense_rank=536 · lex_rank=23
- **query:** `60 Le Thanh Dong Dong Hoi`
- family=`ORTHOGRAPHIC_IME` · operator=`strip_diacritics` · stratum=`address_street_building`
- **target:** 60, Lê Thành Đồng [osm:node/1011330677]
- **mE5 top-10:**
  1. 60 — Phường Ngô Quyền, Thành phố Hải Phòng [osm:way/1252428628]
  2. 6_1_60 — Phường Đông Ngạc, Hà Nội [osm:way/899949501]
  3. 60 Lê Thanh Nghị — Phường Bạch Mai, Hà Nội [osm:node/738813467]
  4. Nhà dân 6 — Phường Đông Ngạc, Hà Nội [osm:way/899881713]
  5. 6_1_50 — Phường Đông Ngạc, Hà Nội [osm:way/899946821]
  6. 6_1_56 — Phường Đông Ngạc, Hà Nội [osm:way/899948587]
  7. 60 Đinh Châu — Phường Cẩm Lệ, Thành phố Đà Nẵng [osm:node/11900103130]
  8. 6 — Phường Ngô Quyền, Thành phố Hải Phòng [osm:way/1252428619]
  9. 6 — Phường Ngô Quyền, Thành phố Hải Phòng [osm:way/1255510353]
  10. Svay Ah Ngoung —  [osm:node/4710985991]
- **BM25 top-10:**
  1. 60 Lê Thanh Nghị — Phường Bạch Mai, Hà Nội [osm:node/738813467]
  2. 10, Kiệt 60 Tô Hiệu — 10, Kiệt 60 Tô Hiệu, Phường Hòa Khánh, Thành phố Đà Nẵng [osm:node/6521531918]
  3. 15, Kiệt 60 Tô Hiệu — 15, Kiệt 60 Tô Hiệu, Phường Hòa Khánh, Thành phố Đà Nẵng [osm:node/6521483780]
  4. 03, Kiệt 60 Tô Hiệu — 03, Kiệt 60 Tô Hiệu, Phường Hòa Khánh, Thành phố Đà Nẵng [osm:node/6521483781]
  5. 60 Tân Xuân — Phường Đông Ngạc, Hà Nội [osm:node/12082634694]
  6. 75, Lê Thành Đồng — 75, Lê Thành Đồng, Phường Đồng Hới, Tỉnh Quảng Trị [osm:node/1011330419]
  7. 89, Lê Thành Đồng — 89, Lê Thành Đồng, Phường Đồng Hới, Tỉnh Quảng Trị [osm:node/1011330748]
  8. 50, Lê Thành Đồng — 50, Lê Thành Đồng, Phường Đồng Hới, Tỉnh Quảng Trị [osm:node/1011330232]
  9. 55, Lê Thành Đồng — 55, Lê Thành Đồng, Phường Đồng Hới, Tỉnh Quảng Trị [osm:node/1011330473]
  10. 13, Lê Thành Đồng — 13, Lê Thành Đồng, Phường Đồng Hới, Tỉnh Quảng Trị [osm:node/1011330721]

### `g150-029-v2` · len=25 · tokens=5 · dense_rank=1001 · lex_rank=34
- **query:** `Truong lien cap Khuong Ha`
- family=`ORTHOGRAPHIC_IME` · operator=`strip_diacritics` · stratum=`named_clear`
- **target:** Trường Tiểu học - Trung học cơ sở - Trung học phổ thông Khương Hạ [osm:way/957452559]
- **mE5 top-10:**
  1. Loungaloun —  [osm:node/4679739193]
  2. DAGA —  [osm:way/1075962699]
  3. Svay Ah Ngoung —  [osm:node/4710985991]
  4. Langeach Neuk —  [osm:node/7114482986]
  5. Preak Chrey Commune Council —  [osm:node/3905842209]
  6. 13 —  [osm:way/931263390]
  7. Tela —  [osm:node/2633372215]
  8. 12 —  [osm:way/931263389]
  9. Nha Tro —  [osm:node/4679748690]
  10. 3 —  [osm:way/931263379]
- **BM25 top-10:**
  1. Trường trung cấp nghề số 10 — Phường Khương Đình, Hà Nội [osm:way/1510217607]
  2. Trường liên cấp Vinschool — Phường Tây Mỗ, Hà Nội [osm:node/9548712890]
  3. Trường Liên cấp Everest — Phường Nghĩa Đô, Hà Nội [osm:way/910279785]
  4. Khu liền kề X1 — Phường Khương Đình, Hà Nội [osm:way/1460269212]
  5. Trường cấp 3 Tuy Phong — Xã Liên Hương, Tỉnh Lâm Đồng [osm:node/4609671093]
  6. shop bán túi xách siêu cấp — 32/133, Đường Nguyễn Xiển, Phường Khương Đình, Hà Nội [osm:node/7056021978]
  7. Trường Phổ thông Liên cấp Olympia — Phường Đại Mỗ, Hà Nội [osm:way/975967911]
  8. Trường phổ thông liên cấp Archimedes — Xã Phúc Thịnh, Hà Nội [osm:node/11527469429]
  9. Trường Phổ thông liên cấp H.A.S — Phường Dương Nội, Hà Nội [osm:way/1277977415]
  10. Trường Liên cấp Lômônôxốp Tây Hà Nội — Phường Dương Nội, Hà Nội [osm:way/1278002257]

### `g150-111-v2` · len=27 · tokens=7 · dense_rank=849 · lex_rank=89
- **query:** `Ca phe 22 Tran Huy Lieu Hue`
- family=`ORTHOGRAPHIC_IME` · operator=`strip_diacritics` · stratum=`category_local`
- **target:** Cheap and very good Vietnamese coffee (10k black, 15k with milk) [osm:node/6026702285]
- **mE5 top-10:**
  1. Nhà 22 — Đường phú khê, Xã Đức Hợp, Tỉnh Hưng Yên [osm:way/1367884294]
  2. S22 — Phường Phú Thủy, Tỉnh Lâm Đồng [osm:way/457736503]
  3. 22 — 22, Võ Thị Sáu, Phường Cao Lãnh, Tỉnh Đồng Tháp [osm:node/5830243180]
  4. L.H.R —  [osm:node/12627999302]
  5. 12 —  [osm:way/931263389]
  6. 22, Hà Huy Giáp — 22, Hà Huy Giáp, Phường An Phú Đông, Thành phố Hồ Chí Minh [osm:node/12107211384]
  7. 22 — Xã Tân Vĩnh Lộc, Thành phố Hồ Chí Minh [osm:way/305085417]
  8. E22 — Phường Phú Thủy, Tỉnh Lâm Đồng [osm:way/746329609]
  9. 22, Nguyễn Trãi — 22, Nguyễn Trãi, Phường Thanh Xuân, Hà Nội [osm:node/7056038734]
  10. Ca Phe RO22 — Phường Xuân Hòa, Thành phố Hồ Chí Minh [osm:node/5235916721]
- **BM25 top-10:**
  1. Vietnamese Restaurant - Hue specialty Restaurant - FastFood 22 - Coffee&Smothies & Restaurant — 22, Trần Huy Liệu, Phường Phú Xuân, Thành phố Huế [osm:node/12449708601]
  2. Tiệm Cà Phê 81 — 81, Huyền Trân Công Chúa, Phường Thủy Xuân, Thành phố Huế [osm:node/13339681701]
  3. Net 416 Trần Huy Liệu — Trần Huy Liệu, Phường Trường Thi, Tỉnh Ninh Bình [osm:node/5372032621]
  4. Cà Phê Hương Hà Nội — 71, Trần Huy Liệu, Phường Giảng Võ, Hà Nội [osm:node/5485732122]
  5. Nhà Hàng & Cà Phê EMM's — 110 D1, Trần Huy Liệu, Phường Giảng Võ, Hà Nội [osm:node/8129190713]
  6. Nhà Hàng & Cà Phê EMM's — 110 D1, Trần Huy Liệu, Phường Giảng Võ, Hà Nội [osm:node/4364361735]
  7. 49, Đường Trần Huy Liệu — 49, Đường Trần Huy Liệu, Phường Cẩm Lệ, Thành phố Đà Nẵng [osm:way/695509670]
  8. 30, Đường Trần Huy Liệu — 30, Đường Trần Huy Liệu, Phường Cẩm Lệ, Thành phố Đà Nẵng [osm:way/695511474]
  9. 28, Trần Huy Liệu — 28, Trần Huy Liệu, Phường Phú Nhuận, Thành phố Hồ Chí Minh [osm:node/5352258664]
  10. 85, Đường Trần Huy Liệu — 85, Đường Trần Huy Liệu, Phường Cẩm Lệ, Thành phố Đà Nẵng [osm:node/6530542705]

### `g150-112-v2` · len=27 · tokens=6 · dense_rank=1001 · lex_rank=1
- **query:** `Tieu hoc Thang Nhi Vung Tau`
- family=`ORTHOGRAPHIC_IME` · operator=`strip_diacritics` · stratum=`category_local`
- **target:** Trường Tiểu học Thắng Nhì [osm:way/259746455]
- **mE5 top-10:**
  1. Tieu hoc Tra An — 66, Le Hong Phong, Phường Thới An Đông, Thành phố Cần Thơ [osm:node/5195643394]
  2. Tela —  [osm:node/2633372215]
  3. Svay Ah Ngoung —  [osm:node/4710985991]
  4. Hun Sen Keo Seima —  [osm:way/655505384]
  5. Loungaloun —  [osm:node/4679739193]
  6. Chanthy —  [osm:node/4259913191]
  7. TT Nghien cuu va dao tao nghe nong thon — Phường Ninh Kiều, Thành phố Cần Thơ [osm:way/455028435]
  8. Nha Tro —  [osm:node/4679748690]
  9. VUONG THI THU — 15, Đường 106, Phường Tăng Nhơn Phú, Thành phố Hồ Chí Minh [osm:node/4888954354]
  10. Cua hang Dung cu y te Mien Tay — 12, 3/2, Phường Ninh Kiều, Thành phố Cần Thơ [osm:node/5253694490]
- **BM25 top-10:**
  1. Trường Tiểu học Thắng Nhì — 1, Thắng Nhì, Phường Vũng Tàu, Thành phố Hồ Chí Minh [osm:way/259746455] <<TARGET
  2. Trường Tiểu học Thắng Nhì — Ngư Phủ, Phường Vũng Tàu, Thành phố Hồ Chí Minh [osm:way/1338511473]
  3. Trạm Hoa tiêu Vũng Tàu — Phường Vũng Tàu, Thành phố Hồ Chí Minh [osm:node/2432348490]
  4. Trường Tiểu học Thắng Tam — Phường Vũng Tàu, Thành phố Hồ Chí Minh [osm:way/225083346]
  5. Đình Thắng Nhì — Phường Vũng Tàu, Thành phố Hồ Chí Minh [osm:node/13755372839]
  6. Trường Tiểu học Song ngữ Vũng Tàu — Phường Tam Thắng, Thành phố Hồ Chí Minh [osm:way/788350300]
  7. Đình thần Thắng Nhì — Phường Vũng Tàu, Thành phố Hồ Chí Minh [osm:way/259746456]
  8. UBND phường Thắng Nhì — Phường Vũng Tàu, Thành phố Hồ Chí Minh [osm:way/786450870]
  9. Trường Tiểu học Nhị Quý — Phường Nhị Quý, Tỉnh Đồng Tháp [osm:way/1331548893]
  10. Cảng tàu khách Vũng Tàu — Phường Vũng Tàu, Thành phố Hồ Chí Minh [osm:node/13078333525]

### `g150-039-v2` · len=28 · tokens=7 · dense_rank=162 · lex_rank=2
- **query:** `Mam non Kim Lien phan hieu 1`
- family=`ORTHOGRAPHIC_IME` · operator=`strip_diacritics` · stratum=`named_clear`
- **target:** Trường Mầm non Kim Liên (phân hiệu 1) [osm:way/814968070]
- **mE5 top-10:**
  1. 1 —  [osm:way/931263377]
  2. Hun Sen Keo Seima —  [osm:way/655505384]
  3. Chợ Bà Vẹt —  [osm:way/668071432]
  4. papa ratanakiri —  [osm:node/7103925986]
  5. E1 — Phường Kim Liên, Hà Nội [osm:way/840063135]
  6. Sokimex —  [osm:node/7114360785]
  7. Saom Primary School —  [osm:node/4682352214]
  8. 1, Phố Kim Ngưu — 1, Phố Kim Ngưu, Phường Bạch Mai, Hà Nội [osm:node/6631893759]
  9. Savimex —  [osm:node/2633372214]
  10. A1 — Phường Kim Liên, Hà Nội [osm:way/136258985]
- **BM25 top-10:**
  1. Trường Mầm non Kim Liên (phân hiệu 2) — Phường Kim Liên, Hà Nội [osm:way/1510837884]
  2. Trường Mầm non Kim Liên (phân hiệu 1) — 27, Phố Lương Định Của, Phường Kim Liên, Hà Nội [osm:way/814968070] <<TARGET
  3. Trường Mầm non Quang Hanh - phân hiệu 1 — Phường Quang Hanh, Thành phố Quảng Ninh [osm:way/678387922]
  4. Trường Mầm non Phương Mai (phân hiệu 2) — Phường Kim Liên, Hà Nội [osm:way/1314119672]
  5. Trường Mầm non Trung Tự (phân hiệu 2) — Phường Kim Liên, Hà Nội [osm:way/1303224796]
  6. Trường Mầm non Kim Liên — 19, Phố Hoàng Tích Trí, Phường Kim Liên, Hà Nội [osm:way/812557719]
  7. Trường Mầm non Phương Mai (phân hiệu 1) — 6, Phố Đào Duy Anh, Phường Kim Liên, Hà Nội [osm:way/1208800256]
  8. Trường Mầm non Tương Mai (thuộc phân hiệu 2) — Phường Tương Mai, Hà Nội [osm:way/1278051310]
  9. Trường Mầm non Bình Minh - Phân hiệu — 16, Phố Đinh Núp, Phường Yên Hòa, Hà Nội [osm:way/1203397070]
  10. Trường Mầm non Yên Hòa - Phân hiệu 2 — 24, Phố Đinh Núp, Phường Yên Hòa, Hà Nội [osm:way/1203397057]

### `g150-136-v2` · len=28 · tokens=8 · dense_rank=558 · lex_rank=1
- **query:** `Ben xe Bo Ke Ham Tien Mui Ne`
- family=`ORTHOGRAPHIC_IME` · operator=`strip_diacritics` · stratum=`code_transit_landmark`
- **target:** Trung tâm Bờ Kè - Hàm Tiến, Mũi Né [osm:node/5512213573]
- **mE5 top-10:**
  1. Tela —  [osm:node/2633372215]
  2. Hun Sen Keo Seima —  [osm:way/655505384]
  3. Sokimex —  [osm:node/7114360785]
  4. Savimex —  [osm:node/2633372214]
  5. Ham Tien Police Ward — Phường Mũi Né, Tỉnh Lâm Đồng [osm:node/10277523609]
  6. BCEL —  [osm:node/4679739195]
  7. papa ratanakiri —  [osm:node/7103925986]
  8. Religious site —  [osm:node/13715688103]
  9. Caltex —  [osm:node/12627999501]
  10. L.H.R —  [osm:node/12627999302]
- **BM25 top-10:**
  1. Trung tâm Bờ Kè - Hàm Tiến, Mũi Né — 122 (199), Nguyễn Đình Chiểu, Phường Mũi Né, Tỉnh Lâm Đồng [osm:node/5512213573] <<TARGET
  2. Một Nắng - Bờ kè Mũi Né — 122 (199), Nguyễn Đình Chiểu, Phường Mũi Né, Tỉnh Lâm Đồng [osm:node/5355409322]
  3. Suối tiên Mũi Né — Phường Mũi Né, Tỉnh Lâm Đồng [osm:node/4290667290]
  4. Bo Ke Seafood — Phường Mũi Né, Tỉnh Lâm Đồng [osm:way/75392596]
  5. Bo kè mr crab — Phường Mũi Né, Tỉnh Lâm Đồng [osm:node/10267400109]
  6. Thuc Don bo ke — Phường Mũi Né, Tỉnh Lâm Đồng [osm:node/7121682885]
  7. Ham Tien Police Ward — Phường Mũi Né, Tỉnh Lâm Đồng [osm:node/10277523609]
  8. Bờ Kè 79 — 98, Nguyễn Đình Chiểu, Phường Mũi Né, Tỉnh Lâm Đồng [osm:node/5219441129]
  9. bờ kè thỏ — 144, Nguyễn Đình Chiểu, Phường Mũi Né, Tỉnh Lâm Đồng [osm:node/5119055921]
  10. Bo Ke Hong Hao — 187, Nguyễn Đình Chiểu, Phường Mũi Né, Tỉnh Lâm Đồng [osm:node/4426059693]

### `g150-133-v2` · len=30 · tokens=7 · dense_rank=710 · lex_rank=1
- **query:** `Ben xe Bien Hoa Nguyen Ai Quoc`
- family=`ORTHOGRAPHIC_IME` · operator=`strip_diacritics` · stratum=`code_transit_landmark`
- **target:** Bến xe Biên Hòa [osm:way/970251629]
- **mE5 top-10:**
  1. Svay Ah Ngoung —  [osm:node/4710985991]
  2. Benh Vien Ngoai Khoa Nguyen Van Thai — Phường An Hải, Thành phố Đà Nẵng [osm:node/729405661]
  3. Sokimex —  [osm:node/7114360785]
  4. Hun Sen Keo Seima —  [osm:way/655505384]
  5. Tela —  [osm:node/2633372215]
  6. 9 —  [osm:way/931263386]
  7. Nice Coffee —  [osm:node/13399378683]
  8. 5 —  [osm:way/931263381]
  9. Chốt Bảo Vệ Dân phố — 60, Đường Nguyễn Thái Bình, Phường Bến Thành, Thành phố Hồ Chí Minh [osm:node/2674334699]
  10. Nhà lâu bền —  [osm:way/1375330253]
- **BM25 top-10:**
  1. Bến xe Biên Hòa — 4, Đường Nguyễn Ái Quốc, Phường Trấn Biên, Thành phố Đồng Nai [osm:way/970251629] <<TARGET
  2. lốp xe — Xã Bác Ái Đông, Khánh Hòa [osm:node/12438388014]
  3. Tiệm Sửa Xe Chính Hoa — Quốc lộ 217, Xã Biện Thượng, Tỉnh Thanh Hóa [osm:node/14072477401]
  4. Bến xe khách Điện Biên Phủ — Phường Điện Biên Phủ, Tỉnh Điện Biên [osm:way/1529280325]
  5. Phước Đại — Quốc lộ 27B, Xã Bác Ái Đông, Khánh Hòa [osm:node/5362507122]
  6. Ptdt bán trú Tiểu Học Phước Đại A — Quốc lộ 27B, Xã Bác Ái Đông, Khánh Hòa [osm:node/5529508122]
  7. 1034/1/7, Đường Nguyễn Ái Quốc — 1034/1/7, Đường Nguyễn Ái Quốc, Phường Trảng Dài, Thành phố Đồng Nai [osm:way/1177980324]
  8. G6, Đường Nguyễn Ái Quốc — G6, Đường Nguyễn Ái Quốc, Phường Trảng Dài, Thành phố Đồng Nai [osm:way/1163515892]
  9. 1034/1/10, Đường Nguyễn Ái Quốc — 1034/1/10, Đường Nguyễn Ái Quốc, Phường Trảng Dài, Thành phố Đồng Nai [osm:way/1160808052]
  10. 1034/2, Đường Nguyễn Ái Quốc — 1034/2, Đường Nguyễn Ái Quốc, Phường Trảng Dài, Thành phố Đồng Nai [osm:way/1164344056]

### `g150-044-v2` · len=30 · tokens=7 · dense_rank=1001 · lex_rank=1
- **query:** `Nha van hoa thon Dang Thuan An`
- family=`ORTHOGRAPHIC_IME` · operator=`strip_diacritics` · stratum=`named_clear`
- **target:** Nhà văn hóa thôn Đặng [osm:way/1142005105]
- **mE5 top-10:**
  1. Loungaloun —  [osm:node/4679739193]
  2. Tela —  [osm:node/2633372215]
  3. Nha Tro —  [osm:node/4679748690]
  4. Langeach Neuk —  [osm:node/7114482986]
  5. Sokimex —  [osm:node/7114360785]
  6. Svay Ah Ngoung —  [osm:node/4710985991]
  7. papa ratanakiri —  [osm:node/7103925986]
  8. My My Homestay — Xã Du Già, Tỉnh Tuyên Quang [osm:node/11174391337]
  9. Tanong Restaurant —  [osm:node/4940205821]
  10. ផ្ទះសំណាក់ ភូមិយើង —  [osm:node/3273033548]
- **BM25 top-10:**
  1. Nhà văn hóa thôn Đặng — 100, Ngõ 405 đường Ỷ Lan, Xã Thuận An, Hà Nội [osm:way/1142005105] <<TARGET
  2. Nhà văn hóa thôn An Đà — Xã Thuận An, Hà Nội [osm:way/1222783989]
  3. Nhà văn hóa thôn An Đà — Xã Thuận An, Hà Nội [osm:way/1222783979]
  4. Nhà văn hóa thôn Lở — Xã Thuận An, Hà Nội [osm:way/1147083167]
  5. Nhà văn hóa thôn Hoàng Long — Xã Thuận An, Hà Nội [osm:way/1214031949]
  6. Nhà văn hóa thôn Hàn Lạc — Xã Thuận An, Hà Nội [osm:way/1224796548]
  7. Nhà văn hóa thôn Bài Tâm — Xã Thuận An, Hà Nội [osm:node/8995358233]
  8. Nhà văn hóa thôn Tô Khê — Xã Thuận An, Hà Nội [osm:way/1223814218]
  9. Nhà văn hóa thôn Kim Âu — Xã Thuận An, Hà Nội [osm:way/1224542087]
  10. Nhà văn hóa thôn Cự Đà — Xã Thuận An, Hà Nội [osm:way/1222284710]

### `g150-149-v2` · len=31 · tokens=9 · dense_rank=101 · lex_rank=1
- **query:** `Ben xe Long An Quoc lo 1 Tan An`
- family=`ORTHOGRAPHIC_IME` · operator=`strip_diacritics` · stratum=`code_transit_landmark`
- **target:** Bến xe Long An [osm:node/4452037189]
- **mE5 top-10:**
  1. Tela —  [osm:node/2633372215]
  2. Sokimex —  [osm:node/7114360785]
  3. Nhà lâu bền —  [osm:way/1375330253]
  4. Tanong Restaurant —  [osm:node/4940205821]
  5. L.H.R —  [osm:node/12627999302]
  6. BCEL —  [osm:node/4679739195]
  7. Savimex —  [osm:node/2633372214]
  8. Hun Sen Keo Seima —  [osm:way/655505384]
  9. Caltex —  [osm:node/12627999501]
  10. Khu vực biên giới Long Bang —  [osm:way/856224954]
- **BM25 top-10:**
  1. Bến xe Long An — 113, Quốc lộ 1, Phường Long An, Tỉnh Tây Ninh [osm:node/4452037189] <<TARGET
  2. Bến xe Long Xuyên — Phường Long Xuyên, Tỉnh An Giang [osm:node/12103763887]
  3. Bến xe khách Long Xuyên — Phường Long Xuyên, Tỉnh An Giang [osm:node/2668086049]
  4. Honda Ôtô Long An - Tân An — 86 tuyến tránh, Quốc lộ 1, Phường Long An, Tỉnh Tây Ninh [osm:node/6088277986]
  5. Bến xe Tân Châu — Phường Tân Châu, Tỉnh An Giang [osm:node/12103763893]
  6. Trạm xe khách số 1 — Phường An Hội, Tỉnh Vĩnh Long [osm:node/12750224911]
  7. Bến xe Cửa Lò — Phường Cửa Lò, Tỉnh Nghệ An [osm:way/1307012811]
  8. Kho Tân an — Quốc Lộ 62, Phường Long An, Tỉnh Tây Ninh [osm:node/4732373422]
  9. Trung tâm đăng kiểm xe cơ giới 6201S - Long An — 12, Quốc lộ 1, Phường Long An, Tỉnh Tây Ninh [osm:node/13363289791]
  10. iPhone Long Xuyên — Quốc lộ 91, Phường Long Xuyên, Tỉnh An Giang [osm:node/4737506922]

### `g150-126-v6` · len=31 · tokens=7 · dense_rank=253 · lex_rank=373
- **query:** `Văn phòng phẩm Minh Trâu Mũi Né`
- family=`PHONOLOGICAL` · operator=`phonological_confusion` · stratum=`explicit_area_cross_region`
- **target:** minh châu [osm:node/5065478058]
- **mE5 top-10:**
  1. Nhật Trinh59b — 59b, Nguyễn Đình Chiểu, Phường Mũi Né, Tỉnh Lâm Đồng [osm:node/4744464124]
  2. Văn phòng phẩm — Mặt hồ tai trâu, Phường Bồ Đề, Hà Nội [osm:way/583891757]
  3. thuỷ tiên 2 — 45, Nguyễn Đình Chiểu, Phường Mũi Né, Tỉnh Lâm Đồng [osm:node/5095964521]
  4. Kinh my — 387, Nguyễn Đình Chiểu, Phường Mũi Né, Tỉnh Lâm Đồng [osm:node/4735613222]
  5. phương trâm — 138, Nguyễn Đình Chiểu, Phường Mũi Né, Tỉnh Lâm Đồng [osm:node/5118785525]
  6. a tùng — 97, Nguyễn Đình Chiểu, Phường Mũi Né, Tỉnh Lâm Đồng [osm:node/5085219622]
  7. victor tuor — 48, Nguyễn Đình Chiểu, Phường Mũi Né, Tỉnh Lâm Đồng [osm:node/5095964421]
  8. Minh Trang — 99, Nguyễn Đình Chiểu, Phường Mũi Né, Tỉnh Lâm Đồng [osm:node/5220872824]
  9. TH chú phong 333 — 333, Nguyễn Đình Chiểu, Phường Mũi Né, Tỉnh Lâm Đồng [osm:node/4789273022]
  10. tuấn thảo — 45D, Nguyễn Đình Chiểu, Phường Mũi Né, Tỉnh Lâm Đồng [osm:node/5118696521]
- **BM25 top-10:**
  1. vạn chài mũi né — 100A, Huỳnh Thúc Kháng, Phường Mũi Né, Tỉnh Lâm Đồng [osm:node/5116469422]
  2. Calif Mui Ne — Phường Mũi Né, Tỉnh Lâm Đồng [osm:way/75223429]
  3. Chợ Mũi Né — Phường Mũi Né, Tỉnh Lâm Đồng [osm:way/543900216]
  4. Mui Ne Gardens — Phường Mũi Né, Tỉnh Lâm Đồng [osm:node/5456293421]
  5. iHome Mui Ne — Phường Mũi Né, Tỉnh Lâm Đồng [osm:node/5903219985]
  6. Mũi Né harbor — Phường Mũi Né, Tỉnh Lâm Đồng [osm:node/491537831]
  7. Mui Ne Glamping — Phường Mũi Né, Tỉnh Lâm Đồng [osm:node/13449373529]
  8. Mui Ne Resort — Phường Mũi Né, Tỉnh Lâm Đồng [osm:node/2281493558]
  9. ihome mui ne — Phường Mũi Né, Tỉnh Lâm Đồng [osm:node/6194484189]
  10. Longson Mui Ne — Phường Mũi Né, Tỉnh Lâm Đồng [osm:node/4335283890]

### `g150-161-v2` · len=31 · tokens=7 · dense_rank=279 · lex_rank=3
- **query:** `Toa S2 Sun Grand City Thuy Khue`
- family=`ORTHOGRAPHIC_IME` · operator=`strip_diacritics` · stratum=`building_code`
- **target:** Tòa S2 [osm:way/933218908]
- **mE5 top-10:**
  1. Hun Sen Keo Seima —  [osm:way/655505384]
  2. Tela —  [osm:node/2633372215]
  3. ດ່ານ ພູ ເກືອ —  [osm:way/259050054]
  4. សាលាបឋមសិក្សា ភូមិថ្កូវ —  [osm:way/476280947]
  5. 2 —  [osm:way/931263378]
  6. Sokimex —  [osm:node/7114360785]
  7. ស្នាក់ការបក្សឃុំជាំ —  [osm:node/5724901221]
  8. papa ratanakiri —  [osm:node/7103925986]
  9. ផ្ទះជួលពូខុម —  [osm:node/5017924621]
  10. វត្តបឹងជ្រោង —  [osm:node/4888806222]
- **BM25 top-10:**
  1. Chung cư Sun Grand City — 69B, Đường Thụy Khuê, Phường Tây Hồ, Hà Nội [osm:node/9586984260]
  2. Sun Grand City Ancora — 3, Lương Yên, Phường Hai Bà Trưng, Hà Nội [osm:way/854251683]
  3. Tòa S2 — 69B, Thụy Khuê, Phường Tây Hồ, Hà Nội [osm:way/933218908] <<TARGET
  4. Tòa S2 — Phường Đại Mỗ, Hà Nội [osm:way/965287262]
  5. Sun City — 4, Ton Dan, Phường Nha Trang, Khánh Hòa [osm:node/2574087800]
  6. Homestay the Sun Grand World — Đặc khu Phú Quốc, Tỉnh An Giang [osm:way/746378111]
  7. Sun City Building — 13, Phố Hai Bà Trưng, Phường Cửa Nam, Hà Nội [osm:way/704147266]
  8. 16, Thuỵ Khuê — 16, Thuỵ Khuê, Phường Tây Hồ, Hà Nội [osm:node/12922861244]
  9. Blanca City Sun Group Vũng Tàu — Phường Phước Thắng, Thành phố Hồ Chí Minh [osm:node/12948696385]
  10. City view — Phường Thủy Nguyên, Thành phố Hải Phòng [osm:node/2487786279]

### `g150-126-v2` · len=31 · tokens=7 · dense_rank=959 · lex_rank=66
- **query:** `Van phong pham Minh Chau Mui Ne`
- family=`ORTHOGRAPHIC_IME` · operator=`strip_diacritics` · stratum=`explicit_area_cross_region`
- **target:** minh châu [osm:node/5065478058]
- **mE5 top-10:**
  1. Van Phong Pham Bac Trang — Xã Bình Khê, Tỉnh Gia Lai [osm:node/6426192133]
  2. Svay Ah Ngoung —  [osm:node/4710985991]
  3. MilanoCoffee Nguyen Van Cu — Phường Phan Rang, Khánh Hòa [osm:node/6442332716]
  4. To chau (mi quang, sup cua) — 299, Phan Đình Phùng, Phường Cẩm Thành, Tỉnh Quảng Ngãi [osm:node/13844207001]
  5. 9 —  [osm:way/931263386]
  6. Wat Pak Nam —  [osm:way/387272522]
  7. Shop tưởng van — 73, Huỳnh Thúc Kháng, Phường Mũi Né, Tỉnh Lâm Đồng [osm:node/4735562922]
  8. 26 — THUA 585, Đình Phong Phú, Phường Tăng Nhơn Phú, Thành phố Hồ Chí Minh [osm:node/5267458350]
  9. Savimex —  [osm:node/2633372214]
  10. 10 —  [osm:way/931263387]
- **BM25 top-10:**
  1. vạn chài mũi né — 100A, Huỳnh Thúc Kháng, Phường Mũi Né, Tỉnh Lâm Đồng [osm:node/5116469422]
  2. ihome mui ne — Phường Mũi Né, Tỉnh Lâm Đồng [osm:node/6194484189]
  3. Mũi Né harbor — Phường Mũi Né, Tỉnh Lâm Đồng [osm:node/491537831]
  4. iHome Mui Ne — Phường Mũi Né, Tỉnh Lâm Đồng [osm:node/5903219985]
  5. mui ne cape — Phường Mũi Né, Tỉnh Lâm Đồng [osm:node/6076276485]
  6. Mui Ne Gardens — Phường Mũi Né, Tỉnh Lâm Đồng [osm:node/5456293421]
  7. Mui Ne Glamping — Phường Mũi Né, Tỉnh Lâm Đồng [osm:node/13449373529]
  8. Mui Ne Hils — Phường Mũi Né, Tỉnh Lâm Đồng [osm:node/4916322321]
  9. Chợ Mũi Né — Phường Mũi Né, Tỉnh Lâm Đồng [osm:way/543900216]
  10. Mui Ne Resort — Phường Mũi Né, Tỉnh Lâm Đồng [osm:node/2281493558]

### `g150-035-v2` · len=31 · tokens=7 · dense_rank=1001 · lex_rank=2
- **query:** `Cua Hang Kien Huyen Ho Tung Mau`
- family=`ORTHOGRAPHIC_IME` · operator=`strip_diacritics` · stratum=`named_clear`
- **target:** CH Kiên Huyền [osm:node/5372078121]
- **mE5 top-10:**
  1. Svay Ah Ngoung —  [osm:node/4710985991]
  2. Cua hang Dien thoai Phuong Tung — Nguyễn Trãi, Phường Cái Khế, Thành phố Cần Thơ [osm:node/5177612401]
  3. Loungaloun —  [osm:node/4679739193]
  4. Wat Pak Nam —  [osm:way/387272522]
  5. Hun Sen Keo Seima —  [osm:way/655505384]
  6. Wat Pong Andaeuk —  [osm:way/475133353]
  7. Cua hang Dung cu y te Mien Tay — 12, 3/2, Phường Ninh Kiều, Thành phố Cần Thơ [osm:node/5253694490]
  8. Ma Me Ancient Village — 22, Nguyen khang, Xã Lũng Cú, Tỉnh Tuyên Quang [osm:node/4846795723]
  9. Langeach Neuk —  [osm:node/7114482986]
  10. Wat Sangkom Mean Chey —  [osm:way/487559102]
- **BM25 top-10:**
  1. Cửa Hàng Linh Phụ Kiện Điện Thoại Huyền Trâm — Phường Đông Ngạc, Hà Nội [osm:node/8360862326]
  2. CH Kiên Huyền — 5, Hồ Tùng Mâuj, Phường Nam Định, Tỉnh Ninh Bình [osm:node/5372078121] <<TARGET
  3. Cửa hàng Skype Minh Hằng — Xã Kiến Đức, Tỉnh Lâm Đồng [osm:node/5483893523]
  4. Cửa hàng đồ khô Tú Hoa — Phường Tùng Thiện, Hà Nội [osm:node/11543419834]
  5. Cửa Hàng Bít Tết 53 Cô Mẫu — 53b, Hàng Bài, Phường Cửa Nam, Hà Nội [osm:node/4735627523]
  6. Qua cửa hàng thuốc Thú Y Quang Bình — Phường Tùng Thiện, Hà Nội [osm:node/11543419838]
  7. Đối diện cửa hàng tủ bếp Châu Âu — Phường Tùng Thiện, Hà Nội [osm:node/11543441898]
  8. Cửa Hàng Xăng Dầu Số 12 – Tản Lĩnh | Petrolimex — Phường Tùng Thiện, Hà Nội [osm:node/2888537586]
  9. Cửa hàng trang sức — Xã Kiên Lương, Tỉnh An Giang [osm:node/2331837108]
  10. Trước đối diện cửa hàng thuốc Thú Y Quang Bình — Phường Tùng Thiện, Hà Nội [osm:node/11543441894]

### `g150-064-v2` · len=32 · tokens=8 · dense_rank=1001 · lex_rank=1
- **query:** `Diem Y te Dinh Cong Dinh Cong Ha`
- family=`ORTHOGRAPHIC_IME` · operator=`strip_diacritics` · stratum=`named_clear`
- **target:** Điểm Y tế Định Công [osm:way/1475290264]
- **mE5 top-10:**
  1. Tela —  [osm:node/2633372215]
  2. Loungaloun —  [osm:node/4679739193]
  3. DAGA —  [osm:way/1075962699]
  4. 13 —  [osm:way/931263390]
  5. Svay Ah Ngoung —  [osm:node/4710985991]
  6. 10 —  [osm:way/931263387]
  7. 11 —  [osm:way/931263388]
  8. 9 —  [osm:way/931263386]
  9. 12 —  [osm:way/931263389]
  10. 5 —  [osm:way/931263381]
- **BM25 top-10:**
  1. Điểm Y tế Định Công — 58, Phố Định Công Hạ, Phường Định Công, Hà Nội [osm:way/1475290264] <<TARGET
  2. Điểm Y tế Đại Kim — 2, Ngõ 292 Đường Kim Giang, Phường Định Công, Hà Nội [osm:way/1046719158]
  3. Ngõ 99 Công Hạ, Ngõ 99 Định Công Hạ — Ngõ 99 Công Hạ, Ngõ 99 Định Công Hạ, Phường Định Công, Hà Nội [osm:node/6596886451]
  4. 134, Định Công Hạ — 134, Định Công Hạ, Phường Định Công, Hà Nội [osm:node/6591605971]
  5. 104, Định Công Hạ — 104, Định Công Hạ, Phường Định Công, Hà Nội [osm:node/6591605967]
  6. 76, Định Công Hạ — 76, Định Công Hạ, Phường Định Công, Hà Nội [osm:node/6597578237]
  7. 144, Định Công Hạ — 144, Định Công Hạ, Phường Định Công, Hà Nội [osm:node/6591605974]
  8. 92, Định Công Hạ — 92, Định Công Hạ, Phường Định Công, Hà Nội [osm:node/6591634507]
  9. 129, Định Công Hạ — 129, Định Công Hạ, Phường Định Công, Hà Nội [osm:node/6592074549]
  10. 147, Định Công Hạ — 147, Định Công Hạ, Phường Định Công, Hà Nội [osm:node/6592074550]

### `g150-141-v2` · len=32 · tokens=7 · dense_rank=1001 · lex_rank=1
- **query:** `Chua Bao Quoc Duong Bao Quoc Hue`
- family=`ORTHOGRAPHIC_IME` · operator=`strip_diacritics` · stratum=`code_transit_landmark`
- **target:** Chùa Báo Quốc [osm:way/1170979640]
- **mE5 top-10:**
  1. Tela —  [osm:node/2633372215]
  2. Loungaloun —  [osm:node/4679739193]
  3. Cua hang xang dau so 1 — Xã Phú Lộc, Thành phố Huế [osm:node/4231601889]
  4. Svay Ah Ngoung —  [osm:node/4710985991]
  5. Hun Sen Keo Seima —  [osm:way/655505384]
  6. Chợ Bà Vẹt —  [osm:way/668071432]
  7. Sokimex —  [osm:node/7114360785]
  8. papa ratanakiri —  [osm:node/7103925986]
  9. 2 —  [osm:way/931263378]
  10. Nha Tro —  [osm:node/4679748690]
- **BM25 top-10:**
  1. Chùa Báo Quốc — 17, Bảo Quốc, Phường Thuận Hoá, Thành phố Huế [osm:way/1170979640] <<TARGET
  2. Thuy Duong Hotel — Quốc Lộ 34, Xã Bảo Lạc, Tỉnh Cao Bằng [osm:node/3271203227]
  3. Bảo tàng Lịch sử Quốc gia Việt Nam — Bảo tàng Lịch sử Quốc gia Việt Nam, Phường Cửa Nam, Hà Nội [osm:node/13271879877]
  4. VƯỜN QUỐC GIA PHÚ QUỐC BIỂN BÁO HIỆU CẤP DỰ BÁO CHÁY RỪNG — Đặc khu Phú Quốc, Tỉnh An Giang [osm:node/13664486968]
  5. Bao Lac Homestay & Foods - Coffe - Beer — Khu 1, Quốc Lộ 34, TT Bảo Lạc, Cao Bằng, Xã Bảo Lạc, Tỉnh Cao Bằng [osm:node/8117798517]
  6. HĐND - UBND Xã Bảo Lâm 3 — Quốc lộ 55, Xã Bảo Lâm 3, Tỉnh Lâm Đồng [osm:way/1396236914]
  7. Phương Thảo — Quốc lộ 34, Xã Bảo Lâm, Tỉnh Cao Bằng [osm:node/12307234101]
  8. Đảng ủy - HĐND - UBND Xã Bảo Lâm 5 — Quốc lộ 55, Xã Bảo Lâm 5, Tỉnh Lâm Đồng [osm:way/1396236915]
  9. Bến xe khách Ninh Thuận — 52, Quốc lộ 1A, Phường Bảo An, Khánh Hòa [osm:node/6678202185]
  10. Đảng Ủy - HĐND - UBND - UBMTTQ Xã Bảo Lâm 2 — Quốc lộ 20, Xã Bảo Lâm 2, Tỉnh Lâm Đồng [osm:way/1396236913]

### `g150-015-v1` · len=33 · tokens=8 · dense_rank=761 · lex_rank=1001
- **query:** `Cây xăng PV Oil Ngô Quyền Đà Nẵng`
- family=`CLEAN` · operator=`canonical` · stratum=`brand_branch`
- **target:** Vĩnh Phú [osm:way/693404962]
- **mE5 top-10:**
  1. PV Oil | petro vietnam — Đường Ngô Quyền, Phường An Hải, Thành phố Đà Nẵng [osm:way/693361870]
  2. PV Oil | petro vietnam — Đường Ngô Quyền, Phường An Hải, Thành phố Đà Nẵng [osm:way/693368219]
  3. Cây xăng dầu Hùng Vương — Phường Tam Kỳ, Thành phố Đà Nẵng [osm:node/13805656755]
  4. Cây xăng dầu Quang Vinh — Xã Hòa Tiến, Thành phố Đà Nẵng [osm:way/593647268]
  5. Cây xăng Tấn Thanh Toàn — Phường Ngũ Hành Sơn, Thành phố Đà Nẵng [osm:node/11891349403]
  6. Cây xăng Lê Hồng Phong — Phường Ngô Quyền, Thành phố Hải Phòng [osm:way/1188490993]
  7. PV Oil | PV Oil — Đường Hoàng Văn Thái, Phường Hòa Khánh, Thành phố Đà Nẵng [osm:way/694804416]
  8. PV Oil | PV Oil — Đường Lê Văn Hiến, Phường Ngũ Hành Sơn, Thành phố Đà Nẵng [osm:way/695637975]
  9. PV Oil | PV Oil — Đường Ngũ Hành Sơn, Phường Ngũ Hành Sơn, Thành phố Đà Nẵng [osm:way/699422484]
  10. Cây xăng Hòa Hiệp 2 — Phường Hòa Xuân, Thành phố Đà Nẵng [osm:node/11894149732]
- **BM25 top-10:**
  1. cây xăng PV oil — Phường Hồng Bàng, Thành phố Hải Phòng [osm:node/2494987930]
  2. cây xăng Pv oil — Phường Hồng Bàng, Thành phố Hải Phòng [osm:node/2494901583]
  3. Cây Xăng PV Oil — Quốc Lộ 1, Xã Thanh Hưng, Tỉnh Đồng Tháp [osm:node/6291381488]
  4. PV Oil | petro vietnam — Đường Ngô Quyền, Phường An Hải, Thành phố Đà Nẵng [osm:way/693361870]
  5. PV Oil | petro vietnam — Đường Ngô Quyền, Phường An Hải, Thành phố Đà Nẵng [osm:way/693368219]
  6. PV Oil — Xã Thăng Điền, Thành phố Đà Nẵng [osm:node/12706339301]
  7. PV Oil — Xã Nam Giang, Thành phố Đà Nẵng [osm:node/6966288906]
  8. PV Oil — Xã Tam Anh, Thành phố Đà Nẵng [osm:node/4444057992]
  9. PV OIL — Xã Nam Giang, Thành phố Đà Nẵng [osm:node/7196623787]
  10. PV Oil | PV Oil — Phường Hội An Đông, Thành phố Đà Nẵng [osm:node/13413242485]

### `g150-015-v2` · len=33 · tokens=8 · dense_rank=1001 · lex_rank=1001
- **query:** `Cây xang PV Oil Ngo Quyen Da Nang`
- family=`ORTHOGRAPHIC_IME` · operator=`partial_diacritics` · stratum=`brand_branch`
- **target:** Vĩnh Phú [osm:way/693404962]
- **mE5 top-10:**
  1. Cây Xăng PV Oil — Quốc Lộ 1, Xã Thanh Hưng, Tỉnh Đồng Tháp [osm:node/6291381488]
  2. PV Oil | PV Oil — Xã Quỳnh Tam, Tỉnh Nghệ An [osm:way/1343459498]
  3. PV Oil | PV Oil — Xã Vạn Ninh, Khánh Hòa [osm:node/4394577797]
  4. PV Oil | PV Oil — Xã Vạn Ninh, Khánh Hòa [osm:node/4472098793]
  5. PV Oil — Xã Hương Khê, Hà Tĩnh [osm:node/4440518593]
  6. PV Oil — Xã Vạn Hưng, Khánh Hòa [osm:node/4395552391]
  7. PV Oil — Xã Nghi Xuân, Hà Tĩnh [osm:node/4386956792]
  8. PV Oil | PV Oil — Xã Cẩm Hưng, Hà Tĩnh [osm:node/13406755102]
  9. PV Oil | PV Oil — Xã Cẩm Hưng, Hà Tĩnh [osm:node/13672080704]
  10. PV oil | PV Oil — Nguyễn Thái Học, Phường Hà Giang 2, Tỉnh Tuyên Quang [osm:node/4307028589]
- **BM25 top-10:**
  1. cây xăng PV oil — Phường Hồng Bàng, Thành phố Hải Phòng [osm:node/2494987930]
  2. cây xăng Pv oil — Phường Hồng Bàng, Thành phố Hải Phòng [osm:node/2494901583]
  3. Cây Xăng PV Oil — Quốc Lộ 1, Xã Thanh Hưng, Tỉnh Đồng Tháp [osm:node/6291381488]
  4. PV Oil | petro vietnam — Đường Ngô Quyền, Phường An Hải, Thành phố Đà Nẵng [osm:way/693361870]
  5. PV Oil | petro vietnam — Đường Ngô Quyền, Phường An Hải, Thành phố Đà Nẵng [osm:way/693368219]
  6. PV Oil — Xã Thăng Điền, Thành phố Đà Nẵng [osm:node/12706339301]
  7. PV Oil — Xã Nam Giang, Thành phố Đà Nẵng [osm:node/6966288906]
  8. PV Oil — Xã Tam Anh, Thành phố Đà Nẵng [osm:node/4444057992]
  9. PV OIL — Xã Nam Giang, Thành phố Đà Nẵng [osm:node/7196623787]
  10. PV Oil | PV Oil — Phường Hội An Đông, Thành phố Đà Nẵng [osm:node/13413242485]

### `g150-015-v6` · len=33 · tokens=8 · dense_rank=1001 · lex_rank=858
- **query:** `Cây xăng PV Oil Ngô Qyuền Đà Nẵng`
- family=`MECHANICAL_TYPO` · operator=`char_transpose` · stratum=`brand_branch`
- **target:** Vĩnh Phú [osm:way/693404962]
- **mE5 top-10:**
  1. Cây xăng dầu Quang Vinh — Xã Hòa Tiến, Thành phố Đà Nẵng [osm:way/593647268]
  2. PV Oil | petro vietnam — Đường Ngô Quyền, Phường An Hải, Thành phố Đà Nẵng [osm:way/693361870]
  3. PV Oil | petro vietnam — Đường Ngô Quyền, Phường An Hải, Thành phố Đà Nẵng [osm:way/693368219]
  4. PV Oil | PV Oil — Đường Lê Văn Hiến, Phường Ngũ Hành Sơn, Thành phố Đà Nẵng [osm:way/695637975]
  5. Cây xăng Tấn Thanh Toàn — Phường Ngũ Hành Sơn, Thành phố Đà Nẵng [osm:node/11891349403]
  6. PV Oil | PV Oil — Đường Hoàng Văn Thái, Phường Hòa Khánh, Thành phố Đà Nẵng [osm:way/694804416]
  7. Đối diện Cây xăng số 5 — Xã Hòa Tiến, Thành phố Đà Nẵng [osm:node/11903086039]
  8. PV Oil | PV Oil — Đường Quốc lộ 1, Phường Hòa Xuân, Thành phố Đà Nẵng [osm:way/699685197]
  9. Cây xăng dầu Hùng Vương — Phường Tam Kỳ, Thành phố Đà Nẵng [osm:node/13805656755]
  10. Kề Cây xăng số 5 — Xã Hòa Tiến, Thành phố Đà Nẵng [osm:node/11903086037]
- **BM25 top-10:**
  1. cây xăng Pv oil — Phường Hồng Bàng, Thành phố Hải Phòng [osm:node/2494901583]
  2. cây xăng PV oil — Phường Hồng Bàng, Thành phố Hải Phòng [osm:node/2494987930]
  3. Cây Xăng PV Oil — Quốc Lộ 1, Xã Thanh Hưng, Tỉnh Đồng Tháp [osm:node/6291381488]
  4. PV Oil | petro vietnam — Đường Ngô Quyền, Phường An Hải, Thành phố Đà Nẵng [osm:way/693361870]
  5. PV Oil | petro vietnam — Đường Ngô Quyền, Phường An Hải, Thành phố Đà Nẵng [osm:way/693368219]
  6. PV OIL — Xã Nam Giang, Thành phố Đà Nẵng [osm:node/7196623787]
  7. PV Oil — Xã Tam Anh, Thành phố Đà Nẵng [osm:node/4444057992]
  8. PV Oil — Xã Nam Giang, Thành phố Đà Nẵng [osm:node/6966288906]
  9. PV Oil — Xã Thăng Điền, Thành phố Đà Nẵng [osm:node/12706339301]
  10. PV Oil — Phường Điện Bàn Đông, Thành phố Đà Nẵng [osm:node/4444112091]

### `g150-114-v2` · len=34 · tokens=9 · dense_rank=725 · lex_rank=1
- **query:** `THCS Chu Van An Le Dinh Ly Da Nang`
- family=`ORTHOGRAPHIC_IME` · operator=`strip_diacritics` · stratum=`explicit_area_cross_region`
- **target:** Trường Trung học cơ sở Chu Văn An [osm:way/1325575632]
- **mE5 top-10:**
  1. CLB TSH-DS Liên Chiểu — 01, Phú Thạnh 4, Phường Hòa Khánh, Thành phố Đà Nẵng [osm:node/6337142202]
  2. L.H.R —  [osm:node/12627999302]
  3. Cua hang Dung cu y te Mien Tay — 12, 3/2, Phường Ninh Kiều, Thành phố Cần Thơ [osm:node/5253694490]
  4. Tela —  [osm:node/2633372215]
  5. TH Cúc — 262, Tôn Đức Thắng, Phường Phú Thủy, Tỉnh Lâm Đồng [osm:node/4789644521]
  6. TH Dung — Lý Thái Tổ, Xã Tân Hải, Tỉnh Lâm Đồng [osm:node/4846866321]
  7. Sokimex —  [osm:node/7114360785]
  8. Cột dsienej lưc đi bên trái — Xã Sơn Thủy, Tỉnh Tuyên Quang [osm:node/13463647801]
  9. Loungaloun —  [osm:node/4679739193]
  10. Svay Ah Ngoung —  [osm:node/4710985991]
- **BM25 top-10:**
  1. Trường Trung học cơ sở Chu Văn An — 70, Đường Lê Đình Lý, Phường Thanh Khê, Thành phố Đà Nẵng [osm:way/1325575632] <<TARGET
  2. 23, Đường Lê Đình Lý — 23, Đường Lê Đình Lý, Phường Thanh Khê, Thành phố Đà Nẵng [osm:node/6555890878]
  3. 89, Đường Lê Đình Lý — 89, Đường Lê Đình Lý, Phường Thanh Khê, Thành phố Đà Nẵng [osm:node/6530038701]
  4. 42, Đường Lê Đình Lý — 42, Đường Lê Đình Lý, Phường Thanh Khê, Thành phố Đà Nẵng [osm:node/6530189187]
  5. 101, Đường Lê Đình Lý — 101, Đường Lê Đình Lý, Phường Thanh Khê, Thành phố Đà Nẵng [osm:node/6553521256]
  6. 95, Đường Lê Đình Lý — 95, Đường Lê Đình Lý, Phường Thanh Khê, Thành phố Đà Nẵng [osm:node/6553521253]
  7. 171, Đường Lê Đình Lý — 171, Đường Lê Đình Lý, Phường Hòa Cường, Thành phố Đà Nẵng [osm:node/6524294193]
  8. 157, Đường Lê Đình Lý — 157, Đường Lê Đình Lý, Phường Hòa Cường, Thành phố Đà Nẵng [osm:node/6524294194]
  9. 211, Đường Lê Đình Lý — 211, Đường Lê Đình Lý, Phường Hòa Cường, Thành phố Đà Nẵng [osm:node/6522192721]
  10. 104, Đường Lê Đình Lý — 104, Đường Lê Đình Lý, Phường Thanh Khê, Thành phố Đà Nẵng [osm:way/697822849]

### `g150-015-v5` · len=34 · tokens=8 · dense_rank=883 · lex_rank=721
- **query:** `Cây xăng PV Oill Ngô Quyền Đà Nẵng`
- family=`MECHANICAL_TYPO` · operator=`double_letter` · stratum=`brand_branch`
- **target:** Vĩnh Phú [osm:way/693404962]
- **mE5 top-10:**
  1. PV Oil | petro vietnam — Đường Ngô Quyền, Phường An Hải, Thành phố Đà Nẵng [osm:way/693361870]
  2. PV Oil | petro vietnam — Đường Ngô Quyền, Phường An Hải, Thành phố Đà Nẵng [osm:way/693368219]
  3. Cây xăng dầu Hùng Vương — Phường Tam Kỳ, Thành phố Đà Nẵng [osm:node/13805656755]
  4. Cây xăng Tấn Thanh Toàn — Phường Ngũ Hành Sơn, Thành phố Đà Nẵng [osm:node/11891349403]
  5. Cây xăng Lê Hồng Phong — Phường Ngô Quyền, Thành phố Hải Phòng [osm:way/1188490993]
  6. PV Oil | PV Oil — Đường Nguyễn Lương Bằng, Phường Hải Vân, Thành phố Đà Nẵng [osm:way/694333640]
  7. Cây xăng Gia Nguyễn Tâm — Đường Nguyễn Tất Thành, Phường Hải Vân, Thành phố Đà Nẵng [osm:way/696751579]
  8. Cây xăng Hòa Hiệp 2 — Phường Hòa Xuân, Thành phố Đà Nẵng [osm:node/11894149732]
  9. Cây xăng dầu Quang Vinh — Xã Hòa Tiến, Thành phố Đà Nẵng [osm:way/593647268]
  10. PV Oil | PV Oil — Đường Hoàng Văn Thái, Phường Hòa Khánh, Thành phố Đà Nẵng [osm:way/694804416]
- **BM25 top-10:**
  1. Cây xăng Mộc Bài — Xã Xuân Phú, Thành phố Đà Nẵng [osm:node/11898042429]
  2. Cây xăng dầu Hùng Vương — Phường Tam Kỳ, Thành phố Đà Nẵng [osm:node/13805656755]
  3. Cây Xăng Dầu Kiểm Lâm — Xã Thu Bồn, Thành phố Đà Nẵng [osm:node/10304644626]
  4. Kề Cây xăng số 5 — Xã Hòa Tiến, Thành phố Đà Nẵng [osm:node/11903086037]
  5. Cây xăng Hòa Hiệp 2 — Phường Hòa Xuân, Thành phố Đà Nẵng [osm:node/11894149732]
  6. Cây xăng dầu Quang Vinh — Xã Hòa Tiến, Thành phố Đà Nẵng [osm:way/593647268]
  7. cây xăng PV oil — Phường Hồng Bàng, Thành phố Hải Phòng [osm:node/2494987930]
  8. cây xăng Pv oil — Phường Hồng Bàng, Thành phố Hải Phòng [osm:node/2494901583]
  9. Đối diện Cây xăng số 5 — Xã Hòa Tiến, Thành phố Đà Nẵng [osm:node/11903086039]
  10. Đối diện Cây xăng Vạn Phú — Xã Bà Nà, Thành phố Đà Nẵng [osm:node/11903086048]

### `g150-113-v2` · len=35 · tokens=8 · dense_rank=378 · lex_rank=11
- **query:** `Nha sach Ngoc Anh Hiep Binh Thu Duc`
- family=`ORTHOGRAPHIC_IME` · operator=`strip_diacritics` · stratum=`explicit_area_cross_region`
- **target:** Ngọc anh [osm:node/4686167990]
- **mE5 top-10:**
  1. Langeach Neuk —  [osm:node/7114482986]
  2. Svay Ah Ngoung —  [osm:node/4710985991]
  3. Nha Tro —  [osm:node/4679748690]
  4. Nha Nghi —  [osm:node/4679748689]
  5. San Vichet —  [osm:node/4402034389]
  6. Loungaloun —  [osm:node/4679739193]
  7. Duc Me Suoi An Binh — Xã Đạ Huoai 2, Tỉnh Lâm Đồng [osm:node/6365584085]
  8. Ngoc My — Xã Tân Biên, Tỉnh Tây Ninh [osm:node/4434143489]
  9. L.H.R —  [osm:node/12627999302]
  10. Sokimex —  [osm:node/7114360785]
- **BM25 top-10:**
  1. Nhà Thuốc Tây Anh Thư — Phường Hiệp Bình, Thành phố Hồ Chí Minh [osm:node/6778306449]
  2. Nhà sách Anh Thư — Xã Thạnh Hòa, Thành phố Cần Thơ [osm:node/1806802064]
  3. Nhà thờ Tin Lành Thủ Đức — Phường Hiệp Bình, Thành phố Hồ Chí Minh [osm:way/301261207]
  4. Chung cư 4S Riverside Garden Bình Triệu — Số 17, khu phố 3, Hiệp Bình Chánh, Thu Duc District, Số 17, Phường Hiệ [osm:way/258020288]
  5. Nhà sách Bình Minh — Phường Thủ Dầu Một, Thành phố Hồ Chí Minh [osm:node/5001651727]
  6. Nhà sách Bình Minh — Phường Thủ Dầu Một, Thành phố Hồ Chí Minh [osm:node/12345191089]
  7. Nhà sách Bình Minh — Phường Thủ Dầu Một, Thành phố Hồ Chí Minh [osm:node/4214878557]
  8. Nhà sách Thủ Đức — Phường Linh Xuân, Thành phố Hồ Chí Minh [osm:node/11769143910]
  9. NADAM SPA — Highway 13, Hiep Binh Chanh Ward, Thu Duc District, Ho Chi Minh, Vietn [osm:node/5345641822]
  10. Tạp hóa thu hoa 6/27 hương lộ ngọc hiệp — Phường Tây Nha Trang, Khánh Hòa [osm:node/5011118722]

### `g150-137-v2` · len=36 · tokens=8 · dense_rank=126 · lex_rank=1
- **query:** `Dinh lang Huu Chap Kinh Bac Bac Ninh`
- family=`ORTHOGRAPHIC_IME` · operator=`strip_diacritics` · stratum=`code_transit_landmark`
- **target:** Đình làng Hữu Chấp [osm:way/1416432466]
- **mE5 top-10:**
  1. Chùa Thanh Lãng — 143, Đường Ngũ Huyện Khê, Phường Kinh Bắc, Thành phố Bắc Ninh [osm:way/1423914852]
  2. Khám chữa bệnh - Cắt thuốc Nam Bắc - Châm cứu - Xoa bóp - Bấm huyệt — 2G, Đường Phù Đổng Thiên Vương, Phường Kinh Bắc, Thành phố Bắc Ninh [osm:node/13484010004]
  3. B — Phường Kinh Bắc, Thành phố Bắc Ninh [osm:way/1050444675]
  4. Nhà văn hóa Xóm Láng — 49, Đường Ngũ Huyện Khê, Phường Kinh Bắc, Thành phố Bắc Ninh [osm:way/1423914849]
  5. A — Phường Kinh Bắc, Thành phố Bắc Ninh [osm:way/1050444677]
  6. C — Phường Kinh Bắc, Thành phố Bắc Ninh [osm:way/1050444676]
  7. Nha hàng Sarangbang — Phường Kinh Bắc, Thành phố Bắc Ninh [osm:node/6545253561]
  8. Căng tin — Phường Kinh Bắc, Thành phố Bắc Ninh [osm:node/11999036286]
  9. 36, Đường Giếng Ngọc — 36, Đường Giếng Ngọc, Phường Kinh Bắc, Thành phố Bắc Ninh [osm:node/12993769627]
  10. 64, Đường Giếng Ngọc — 64, Đường Giếng Ngọc, Phường Kinh Bắc, Thành phố Bắc Ninh [osm:node/12993769611]
- **BM25 top-10:**
  1. Đình làng Hữu Chấp — 52, Đường Hữu Chấp, Phường Kinh Bắc, Thành phố Bắc Ninh [osm:way/1416432466] <<TARGET
  2. 38, Đường Hữu Chấp — 38, Đường Hữu Chấp, Phường Kinh Bắc, Thành phố Bắc Ninh [osm:node/13016535584]
  3. 30A, Đường Hữu Chấp — 30A, Đường Hữu Chấp, Phường Kinh Bắc, Thành phố Bắc Ninh [osm:node/13016535582]
  4. 89, Đường Hữu Chấp — 89, Đường Hữu Chấp, Phường Kinh Bắc, Thành phố Bắc Ninh [osm:node/13016517872]
  5. 43, Đường Hữu Chấp — 43, Đường Hữu Chấp, Phường Kinh Bắc, Thành phố Bắc Ninh [osm:node/13016535611]
  6. 56, Đường Hữu Chấp — 56, Đường Hữu Chấp, Phường Kinh Bắc, Thành phố Bắc Ninh [osm:node/13016535651]
  7. 85, Đường Hữu Chấp — 85, Đường Hữu Chấp, Phường Kinh Bắc, Thành phố Bắc Ninh [osm:node/13016535504]
  8. 49, Đường Hữu Chấp — 49, Đường Hữu Chấp, Phường Kinh Bắc, Thành phố Bắc Ninh [osm:node/13016535644]
  9. 100, Đường Hữu Chấp — 100, Đường Hữu Chấp, Phường Kinh Bắc, Thành phố Bắc Ninh [osm:node/13016535502]
  10. 34, Đường Hữu Chấp — 34, Đường Hữu Chấp, Phường Kinh Bắc, Thành phố Bắc Ninh [osm:node/13016535583]

### `g150-145-v2` · len=36 · tokens=8 · dense_rank=650 · lex_rank=1
- **query:** `Chua Lien Tri Chon Nhu QL51 Dong Nai`
- family=`ORTHOGRAPHIC_IME` · operator=`strip_diacritics` · stratum=`code_transit_landmark`
- **target:** Chùa Liên Trí Chơn Như [osm:node/11244217845]
- **mE5 top-10:**
  1. QT Ngô Thị Kiều Dung 05 — Xã Ea Wer, Tỉnh Đắk Lắk [osm:node/6167324985]
  2. lan — Quốc Lộ 51, Phường Long Hương, Thành phố Hồ Chí Minh [osm:node/4751837830]
  3. Cua hang Dung cu y te Mien Tay — 12, 3/2, Phường Ninh Kiều, Thành phố Cần Thơ [osm:node/5253694490]
  4. Cua hang sua Tu Tri — 65, 30/4, Phường An Hội, Tỉnh Vĩnh Long [osm:node/6333043785]
  5. Nhu' Ngqc — 483, Duong Tran Ninh, Phường Tô Hiệu, Tỉnh Sơn La [osm:node/5293428629]
  6. 51 Hoàng Tăng Bí — Phường Đông Ngạc, Hà Nội [osm:node/8954351040]
  7. QT Phạm Thị Dung 03 — 276, tổ 10 khối 6 buôn trấp. huyện Krong Âna, Xã Krông Ana, Tỉnh Đắk L [osm:node/6164986685]
  8. Honda Nhung Hồng 5 | Honda — 51, QL3, Xã Sóc Sơn, Hà Nội [osm:node/12584872746]
  9. CH Ngocj Thuy' — 116, to 18 TT. Xuan Truong, Xã Xuân Trường, Tỉnh Ninh Bình [osm:node/5400686026]
  10. khánh nhung — Quốc Lộ 51, Phường Tân Hải, Thành phố Hồ Chí Minh [osm:node/4763432422]
- **BM25 top-10:**
  1. Chùa Liên Trí Chơn Như — 289, QL 51, Phường Long Hưng, Thành phố Đồng Nai [osm:node/11244217845] <<TARGET
  2. Quầy Thuốc Ngọc Liên — 59, Quốc lộ 13, Phường Chơn Thành, Thành phố Đồng Nai [osm:node/12985088650]
  3. cf mobile-ql13,t.t Chơn Thành — Phường Chơn Thành, Thành phố Đồng Nai [osm:node/7288117688]
  4. Công viên Chơn Thành — Phường Chơn Thành, Thành phố Đồng Nai [osm:way/796474958]
  5. UBND Phường Chơn Thành — Phường Chơn Thành, Thành phố Đồng Nai [osm:way/930408699]
  6. th cô Trang-ql14,t.t chơn thành-120000095936 — Phường Chơn Thành, Thành phố Đồng Nai [osm:node/7288117390]
  7. Trạm thu phí Chơn Thành — Phường Chơn Thành, Thành phố Đồng Nai [osm:way/993583970]
  8. photo sương-ngã tư Chơn Thành-120000099609 — Phường Chơn Thành, Thành phố Đồng Nai [osm:node/7288117687]
  9. Đảng ủy Phường Chơn Thành — Phường Chơn Thành, Thành phố Đồng Nai [osm:way/930408704]
  10. cf hoa nắng-kcn Chơn Thành-120000101294 — Phường Chơn Thành, Thành phố Đồng Nai [osm:node/7288117387]

### `g150-118-v2` · len=36 · tokens=9 · dense_rank=781 · lex_rank=1
- **query:** `Tieu hoc Le Loi Tang Bat Ho Quy Nhon`
- family=`ORTHOGRAPHIC_IME` · operator=`strip_diacritics` · stratum=`explicit_area_cross_region`
- **target:** Trường Tiểu học Lê Lợi [osm:node/1527921385]
- **mE5 top-10:**
  1. Hun Sen Keo Seima —  [osm:way/655505384]
  2. Svay Ah Ngoung —  [osm:node/4710985991]
  3. Tela —  [osm:node/2633372215]
  4. Loungaloun —  [osm:node/4679739193]
  5. Dakta Ok Lao border checkpoint —  [osm:way/1474084813]
  6. Chanthy —  [osm:node/4259913191]
  7. Sapaco Ta Loeung —  [osm:node/4220603977]
  8. Tanong Restaurant —  [osm:node/4940205821]
  9. Peace Library —  [osm:way/387271615]
  10. Temple —  [osm:way/486566779]
- **BM25 top-10:**
  1. Trường Tiểu học Lê Lợi — 3, Tăng Bạt Hổ, Phường Quy Nhơn, Tỉnh Gia Lai [osm:node/1527921385] <<TARGET
  2. BTS 1A/27 Tăng bạt hổ — 1A/27, Tăng Bạt Hổ, Phường Quy Nhơn, Tỉnh Gia Lai [osm:node/5495730222]
  3. Trường Tiểu học Lê Văn Việt — Phường Tăng Nhơn Phú, Thành phố Hồ Chí Minh [osm:way/507538766]
  4. 10, Lê Lợi — 10, Lê Lợi, Phường Tăng Nhơn Phú, Thành phố Hồ Chí Minh [osm:node/4994454819]
  5. 5, Lê Lợi — 5, Lê Lợi, Phường Tăng Nhơn Phú, Thành phố Hồ Chí Minh [osm:node/4995983663]
  6. Trường Tiểu học Nhơn Hải — Phường Quy Nhơn Đông, Tỉnh Gia Lai [osm:node/5344171795]
  7. Trường Tiểu Học Ngô Mây — Phường Quy Nhơn Nam, Tỉnh Gia Lai [osm:node/1532502519]
  8. Trường Trung học cơ sở Lê Lợi — Phường Quy Nhơn, Tỉnh Gia Lai [osm:way/1167733592]
  9. Trường Tiểu học Bát Tràng — Xã Bát Tràng, Hà Nội [osm:way/1224936767]
  10. Trường Tiểu học Tòng Bạt — Xã Bất Bạt, Hà Nội [osm:way/1090886428]

### `g150-135-v2` · len=37 · tokens=8 · dense_rank=122 · lex_rank=20
- **query:** `Dinh Ha Lieu Ton That Thuyet Bac Ninh`
- family=`ORTHOGRAPHIC_IME` · operator=`strip_diacritics` · stratum=`code_transit_landmark`
- **target:** Đình Hà Liễu [osm:way/1327195096]
- **mE5 top-10:**
  1. Loungaloun —  [osm:node/4679739193]
  2. Bird watching —  [osm:node/12480444201]
  3. Svay Ah Ngoung —  [osm:node/4710985991]
  4. B — Phường Kinh Bắc, Thành phố Bắc Ninh [osm:way/1050444675]
  5. It's not a road, you cannot go to DU GIA by this way — Xã Niêm Sơn, Tỉnh Tuyên Quang [osm:node/6359830887]
  6. C — Phường Kinh Bắc, Thành phố Bắc Ninh [osm:way/1050444676]
  7. Langeach Neuk —  [osm:node/7114482986]
  8. đất trống — Phường Bắc Giang, Thành phố Bắc Ninh [osm:node/11449802004]
  9. đất trống — Phường Bắc Giang, Thành phố Bắc Ninh [osm:way/1233854561]
  10. A — Phường Kinh Bắc, Thành phố Bắc Ninh [osm:way/1050444677]
- **BM25 top-10:**
  1. 7, Phố Tôn Thất Thuyết — 7, Phố Tôn Thất Thuyết, Phường Phương Liễu, Thành phố Bắc Ninh [osm:node/12304240283]
  2. 5, Phố Tôn Thất Thuyết — 5, Phố Tôn Thất Thuyết, Phường Phương Liễu, Thành phố Bắc Ninh [osm:node/12304240282]
  3. 12, Phố Tôn Thất Thuyết — 12, Phố Tôn Thất Thuyết, Phường Phương Liễu, Thành phố Bắc Ninh [osm:node/12351163333]
  4. 14, Phố Tôn Thất Thuyết — 14, Phố Tôn Thất Thuyết, Phường Phương Liễu, Thành phố Bắc Ninh [osm:node/12351163332]
  5. 29, Phố Tôn Thất Thuyết — 29, Phố Tôn Thất Thuyết, Phường Phương Liễu, Thành phố Bắc Ninh [osm:node/12851212093]
  6. 20, Phố Tôn Thất Thuyết — 20, Phố Tôn Thất Thuyết, Phường Phương Liễu, Thành phố Bắc Ninh [osm:node/12424632649]
  7. 3, Phố Tôn Thất Thuyết — 3, Phố Tôn Thất Thuyết, Phường Phương Liễu, Thành phố Bắc Ninh [osm:node/12304240281]
  8. 1, Phố Tôn Thất Thuyết — 1, Phố Tôn Thất Thuyết, Phường Phương Liễu, Thành phố Bắc Ninh [osm:node/12304240279]
  9. 2, Phố Tôn Thất Thuyết — 2, Phố Tôn Thất Thuyết, Phường Phương Liễu, Thành phố Bắc Ninh [osm:node/12304240280]
  10. 22, Phố Tôn Thất Thuyết — 22, Phố Tôn Thất Thuyết, Phường Phương Liễu, Thành phố Bắc Ninh [osm:node/12636096671]

### `g150-143-v2` · len=38 · tokens=10 · dense_rank=816 · lex_rank=1
- **query:** `Nha Dat Vang Can Tho Duong so 6 Tan An`
- family=`ORTHOGRAPHIC_IME` · operator=`strip_diacritics` · stratum=`code_transit_landmark`
- **target:** NHÀ DÁT VÀNG CẦN THƠ [osm:way/1227132982]
- **mE5 top-10:**
  1. 6 Đời 1 — Nguyễn Văn Cừ Nối dài, Phường Tân An, Thành phố Cần Thơ [osm:way/543245355]
  2. Svay Ah Ngoung —  [osm:node/4710985991]
  3. Wat Pak Nam —  [osm:way/387272522]
  4. 6 — 6, Ngô Thời Nhậm, Phường Cao Lãnh, Tỉnh Đồng Tháp [osm:node/5830243167]
  5. Nha Tro —  [osm:node/4679748690]
  6. Hun Sen Keo Seima —  [osm:way/655505384]
  7. Tanong Restaurant —  [osm:node/4940205821]
  8. Hai san bịnh dan 66 tran phu — 66, Trần Phú, Phường Nha Trang, Khánh Hòa [osm:node/4896333321]
  9. sáu an — Xã Châu Pha, Thành phố Hồ Chí Minh [osm:node/6757037304]
  10. Six Do — Phường Vĩnh Tuy, Hà Nội [osm:way/1331658934]
- **BM25 top-10:**
  1. NHÀ DÁT VÀNG CẦN THƠ — 18, Đường số 6, Phường Tân An, Thành phố Cần Thơ [osm:way/1227132982] <<TARGET
  2. NHÀ MAY NHO — 28, Đường số 6 KTDC ĐẠI HỌC Y DƯỢC, Phường Tân An, Thành phố Cần Thơ [osm:node/8310155418]
  3. nha may Bong Vang — Phường An Bình, Thành phố Cần Thơ [osm:way/543810246]
  4. Nhà máy Bông Vang — Phường An Bình, Thành phố Cần Thơ [osm:way/543810247]
  5. Nhà thuốc Trung Sơn 6 — Phường Tân An, Thành phố Cần Thơ [osm:node/11420288424]
  6. Cây xăng số 6 — Phường An Bình, Thành phố Cần Thơ [osm:node/1794139757]
  7. tiệm vàng Kim Sang — Phường Tân An, Thành phố Cần Thơ [osm:node/5250470894]
  8. 6, Đường số 6 — 6, Đường số 6, Phường Cái Răng, Thành phố Cần Thơ [osm:way/1411225020]
  9. Nha khoa Thiên Ân Cần Thơ — Phường Tân An, Thành phố Cần Thơ [osm:node/5251645045]
  10. Nhóm trẻ độc lập tư thục Nai Vàng — Phường Tân An, Thành phố Cần Thơ [osm:node/5246579678]

### `g150-127-v2` · len=41 · tokens=9 · dense_rank=439 · lex_rank=1
- **query:** `Vang bac Ngoc Tram Tran Hung Dao Bac Ninh`
- family=`ORTHOGRAPHIC_IME` · operator=`strip_diacritics` · stratum=`explicit_area_cross_region`
- **target:** Ngọc Trầm [osm:node/13470857329]
- **mE5 top-10:**
  1. 39-41 Nguyễn Trãi — Phường Kinh Bắc, Thành phố Bắc Ninh [osm:node/13390974895]
  2. 275-277 Nguyễn Trãi — Phường Võ Cường, Thành phố Bắc Ninh [osm:node/12326927003]
  3. Nha hang Bac Trieu Tien Ryu Gyong — 30, Lê Quý Đôn, Phường Xuân Hòa, Thành phố Hồ Chí Minh [osm:node/4359968492]
  4. Svay Ah Ngoung —  [osm:node/4710985991]
  5. tram — Xã Ba Chúc, Tỉnh An Giang [osm:node/6039149387]
  6. 208 Nguyễn Trãi — Phường Võ Cường, Thành phố Bắc Ninh [osm:node/13390974873]
  7. №01, 03 — Phường Bắc Nha Trang, Khánh Hòa [osm:node/4785368222]
  8. 56-58 Nguyễn Trãi — Phường Kinh Bắc, Thành phố Bắc Ninh [osm:node/13390974896]
  9. Nha Tro —  [osm:node/4679748690]
  10. Trumg tâm Điều hành và Giám sát Giao thông vận tải tỉnh Bắc Ninh — Đường Nguyễn Văn Cừ, Phường Võ Cường, Thành phố Bắc Ninh [osm:way/1524895038]
- **BM25 top-10:**
  1. Ngọc Trầm — 1, Đường Trần Hưng Đạo, Phường Kinh Bắc, Thành phố Bắc Ninh [osm:node/13470857329] <<TARGET
  2. Trường Trung học phổ thông Trần Hưng Đạo — Phường Đào Viên, Thành phố Bắc Ninh [osm:way/1448538265]
  3. Trang Sức Vàng Bạc Cara Luna Bắc Ninh — 162, Đường Trần Hưng Đạo, Phường Kinh Bắc, Thành phố Bắc Ninh [osm:node/13437915833]
  4. 353 Trần Hưng Đạo — 353, Đường Trần Hưng Đạo, Phường Võ Cường, Thành phố Bắc Ninh [osm:node/13269406225]
  5. Vascara Trần Hưng Đạo — 252B, Đường Trần Hưng Đạo, Phường Võ Cường, Thành phố Bắc Ninh [osm:node/13512377150]
  6. 295, Đường Trần Hưng Đạo — 295, Đường Trần Hưng Đạo, Phường Võ Cường, Thành phố Bắc Ninh [osm:way/1394203764]
  7. 131, Đường Trần Hưng Đạo — 131, Đường Trần Hưng Đạo, Phường Võ Cường, Thành phố Bắc Ninh [osm:way/1493915096]
  8. 125, Đường Trần Hưng Đạo — 125, Đường Trần Hưng Đạo, Phường Võ Cường, Thành phố Bắc Ninh [osm:way/1525644048]
  9. 16, Đường Trần Hưng Đạo — 16, Đường Trần Hưng Đạo, Phường Gia Bình, Thành phố Bắc Ninh [osm:way/1557507289]
  10. 281, Đường Trần Hưng Đạo — 281, Đường Trần Hưng Đạo, Phường Võ Cường, Thành phố Bắc Ninh [osm:way/1394203757]

### `g150-103-v2` · len=42 · tokens=9 · dense_rank=874 · lex_rank=1
- **query:** `Nha thuoc Tan Hung Chau Van Liem Ninh Kieu`
- family=`ORTHOGRAPHIC_IME` · operator=`strip_diacritics` · stratum=`category_local`
- **target:** Nhà thuốc Tân Hưng [osm:node/5211609373]
- **mE5 top-10:**
  1. Tuan Bin;Thanh Kieu;thanh kiều — 110, Quốc lộ 1A, Xã Tân Lập, Tỉnh Lâm Đồng [osm:node/7114481292]
  2. Nha Tro —  [osm:node/4679748690]
  3. nha tro phu quy — Xã Tân Nhuận Đông, Tỉnh Đồng Tháp [osm:node/5148521321]
  4. Svay Ah Ngoung —  [osm:node/4710985991]
  5. Nha Nghi —  [osm:node/4679748689]
  6. Cau Lim — Phường Hoa Lư, Tỉnh Ninh Bình [osm:node/5325374423]
  7. nha tro cay ban — Phường Bình Đức, Tỉnh An Giang [osm:node/5103632623]
  8. My Phuoc — 27, Nguyen Van Linh, Phường Tân An, Tỉnh Đắk Lắk [osm:node/4400996502]
  9. Langeach Neuk —  [osm:node/7114482986]
  10. Border VN- China —  [osm:node/8950407717]
- **BM25 top-10:**
  1. Nhà thuốc Tân Hưng — 141, Châu Văn Liêm, Phường Ninh Kiều, Thành phố Cần Thơ [osm:node/5211609373] <<TARGET
  2. Nhà Thuốc Long Châu — Xã Như Quỳnh, Tỉnh Hưng Yên [osm:way/1489381790]
  3. Nhà thuốc Sơn Huyền — 96, Đường 30 Tháng 4, Phường Tân Phong, Tỉnh Lai Châu [osm:node/14137277202]
  4. 41 Châu Văn Liêm — Phường Ninh Kiều, Thành phố Cần Thơ [osm:node/11920077206]
  5. Nhà Thuốc FPT Long Châu — 141, Đường Trần Hưng Đạo, Phường Quế Võ, Thành phố Bắc Ninh [osm:way/1327759796]
  6. Nhà Thuốc FPT Long Châu — 165, Đường Trần Hưng Đạo, Phường Võ Cường, Thành phố Bắc Ninh [osm:node/13688769778]
  7. Nhà Thuốc FPT Long Châu — 141-143, Đường Trần Hưng Đạo, Phường Quế Võ, Thành phố Bắc Ninh [osm:node/12795264477]
  8. Nhà Thuốc FPT Long Châu — 57, Đường Trần Hưng Đạo, Phường Kinh Bắc, Thành phố Bắc Ninh [osm:node/12765645731]
  9. Nhà Thuốc FPT Long Châu — 246-248, Đường Trần Hưng Đạo, Phường Kinh Bắc, Thành phố Bắc Ninh [osm:node/13688773950]
  10. 3, đường Châu Văn Liêm — 3, đường Châu Văn Liêm, Phường Từ Liêm, Hà Nội [osm:node/14007976186]

### `g150-132-v2` · len=43 · tokens=9 · dense_rank=164 · lex_rank=1
- **query:** `Cua hang Tuan Thao Nguyen Dinh Chieu Mui Ne`
- family=`ORTHOGRAPHIC_IME` · operator=`strip_diacritics` · stratum=`explicit_area_cross_region`
- **target:** tuấn thảo [osm:node/5118696521]
- **mE5 top-10:**
  1. Cua Hang Xang Dau Nguyen Dinh Chieu — Phường Hai Bà Trưng, Hà Nội [osm:node/729787574]
  2. Cua hang Dien thoai Phuong Tung — Nguyễn Trãi, Phường Cái Khế, Thành phố Cần Thơ [osm:node/5177612401]
  3. Hun Sen Keo Seima —  [osm:way/655505384]
  4. TH Huyền Trân — 216, Nguyễn Đình Chiểu, Phường Mũi Né, Tỉnh Lâm Đồng [osm:node/4780511322]
  5. Cua hang Dung cu y te Mien Tay — 12, 3/2, Phường Ninh Kiều, Thành phố Cần Thơ [osm:node/5253694490]
  6. Huyền tran — 216, Nguyễn Đình Chiểu, Phường Mũi Né, Tỉnh Lâm Đồng [osm:node/4735604122]
  7. Minh Koi — 149, Nguyen Dinh Chieu, Phường Mũi Né, Tỉnh Lâm Đồng [osm:node/3699510925]
  8. Viet's Hotel — 69 Nguyen Dinh Chieu, Central Mui Ne Beach, Mui Ne, Phường Mũi Né, Tỉn [osm:node/4264372895]
  9. Svay Ah Ngoung —  [osm:node/4710985991]
  10. Bia Hoi — Nguyen Dinh Chieu, Phường Mũi Né, Tỉnh Lâm Đồng [osm:node/5999910085]
- **BM25 top-10:**
  1. tuấn thảo — 45D, Nguyễn Đình Chiểu, Phường Mũi Né, Tỉnh Lâm Đồng [osm:node/5118696521] <<TARGET
  2. Tuấn Thảo 180 — 120, Nguyễn Đình Chiểu, Phường Mũi Né, Tỉnh Lâm Đồng [osm:node/4275693598]
  3. tuấn thảo 181 — 191, Nguyễn Đình Chiểu, Phường Mũi Né, Tỉnh Lâm Đồng [osm:node/5112028122]
  4. Pickleball Mui Ne — 68A, Nguyễn Đình Chiểu, Phường Mũi Né, Tỉnh Lâm Đồng [osm:node/13074106619]
  5. Yentown Mui Ne — 120a, Nguyễn Đình Chiểu, Phường Mũi Né, Tỉnh Lâm Đồng [osm:node/12358975687]
  6. Ganesh Mui Ne — 57, Nguyễn Đình Chiểu, Phường Mũi Né, Tỉnh Lâm Đồng [osm:node/886005638]
  7. Mui Ne Laundry — 139B, Nguyễn Đình Chiểu, Phường Mũi Né, Tỉnh Lâm Đồng [osm:node/13070259027]
  8. Yentown Mui Ne — 120A, Nguyễn Đình Chiểu, Phường Mũi Né, Tỉnh Lâm Đồng [osm:way/1336086171]
  9. Venus Mui Ne Hotel — Nguyễn Đình Chiểu, Phường Mũi Né, Tỉnh Lâm Đồng [osm:node/4101229290]
  10. mũi né 888 — 181, Nguyễn Đình Chiểu, Phường Mũi Né, Tỉnh Lâm Đồng [osm:node/5151008821]

### `g150-120-v2` · len=43 · tokens=9 · dense_rank=187 · lex_rank=2
- **query:** `Mam Non Huong Duong Hoang Tang Bi Dong Ngac`
- family=`ORTHOGRAPHIC_IME` · operator=`strip_diacritics` · stratum=`explicit_area_cross_region`
- **target:** Trường Mầm Non Hướng Dương [osm:node/8361034090]
- **mE5 top-10:**
  1. Svay Ah Ngoung —  [osm:node/4710985991]
  2. Truong Mam Non Du Sing — Huyền Trân Công Chúa, Phường Cam Ly - Đà Lạt, Tỉnh Lâm Đồng [osm:node/13762436901]
  3. Langeach Neuk —  [osm:node/7114482986]
  4. Hun Sen Keo Seima —  [osm:way/655505384]
  5. Loungaloun —  [osm:node/4679739193]
  6. Nuoc Mia Hang Dieu — Phường Hoàn Kiếm, Hà Nội [osm:node/6420370485]
  7. Sauce Nuoc Mam — Xã Duy Nghĩa, Thành phố Đà Nẵng [osm:node/7259793385]
  8. Chợ Bà Vẹt —  [osm:way/668071432]
  9. Cua hang Dung cu y te Mien Tay — 12, 3/2, Phường Ninh Kiều, Thành phố Cần Thơ [osm:node/5253694490]
  10. Truong Mam Non Thien Y — 49, Thiện Ý, Phường Xuân Hương - Đà Lạt, Tỉnh Lâm Đồng [osm:node/13644998401]
- **BM25 top-10:**
  1. Trường Mầm non Hoàng Tăng Bí — Phường Đông Ngạc, Hà Nội [osm:way/1376687641]
  2. Trường Mầm Non Hướng Dương — 11, Hoàng Tăng Bí, Phường Đông Ngạc, Hà Nội [osm:node/8361034090] <<TARGET
  3. Trường Mầm non Đông Ngạc — 74, Đường Cầu Noi, Phường Đông Ngạc, Hà Nội [osm:way/699065682]
  4. Trường Mầm non Đông Ngạc A — Phường Đông Ngạc, Hà Nội [osm:way/1198857571]
  5. Trường Mầm non Hoa Hướng Dương — Phường Hoàng Liệt, Hà Nội [osm:way/905067705]
  6. Trường mầm non — Hoàng Tăng Bí, Phường Đông Ngạc, Hà Nội [osm:node/8361081284]
  7. 95, Hoàng Tăng Bí — 95, Hoàng Tăng Bí, Phường Đông Ngạc, Hà Nội [osm:node/8361563270]
  8. 29, Hoàng Tăng Bí — 29, Hoàng Tăng Bí, Phường Đông Ngạc, Hà Nội [osm:node/8361081242]
  9. 51 Hoàng Tăng Bí — Phường Đông Ngạc, Hà Nội [osm:node/8954351040]
  10. Trường Mầm Non 1 — Phường Xuân Hương - Đà Lạt, Tỉnh Lâm Đồng [osm:way/1304439983]

