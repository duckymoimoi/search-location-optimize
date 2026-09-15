import type { OriginItem, Result, Versions } from '../types/api'

export const CORPUS_VERSION = 'hn-poi-stable-v1'

export const DEFAULT_VERSIONS: Versions = {
  release_id: 'mock-lexical-v1',
  corpus_version: CORPUS_VERSION,
  index_version: 'mock-index-v1',
  encoder_id: null,
  embedding_space_id: null,
  passage_builder_version: 'stable-v1-address',
  scope_policy_version: 'scope-v1',
  candidate_policy_version: 'candidate-v1',
  ranker_id: 'identity-v1',
  feature_version: 'tabular-v1',
}

/** Curated Hanoi fixtures for mock suggest / origins. */
export const MOCK_POIS: Array<
  Omit<Result, 'rank' | 'ranking_distance_m'> & {
    aliases: string[]
    category: string
  }
> = [
  {
    poi_id: 'osm:node/mock-highlands-hk',
    name: 'Highlands Coffee — Hồ Hoàn Kiếm',
    aliases: ['highlands', 'highland coffee hoan kiem'],
    category: 'amenity=cafe',
    address_text: '1 Đinh Tiên Hoàng, Hoàn Kiếm',
    context_text: 'Gần Hồ Gươm',
    ranking_point: { lat: 21.0288, lon: 105.852 },
    routing_point: null,
    pickup_access_verified: false,
  },
  {
    poi_id: 'osm:node/mock-highlands-cg',
    name: 'Highlands Coffee — Cầu Giấy',
    aliases: ['highlands', 'highlands cau giay'],
    category: 'amenity=cafe',
    address_text: 'Xuân Thủy, Cầu Giấy',
    context_text: 'Gần ĐHQG',
    ranking_point: { lat: 21.0365, lon: 105.782 },
    routing_point: null,
    pickup_access_verified: false,
  },
  {
    poi_id: 'osm:way/mock-lotte-center',
    name: 'Lotte Center Hanoi',
    aliases: ['lotte', 'lotte center'],
    category: 'building=commercial',
    address_text: '54 Liễu Giai, Ba Đình',
    context_text: 'Quận Ba Đình',
    ranking_point: { lat: 21.0322, lon: 105.8125 },
    routing_point: null,
    pickup_access_verified: false,
  },
  {
    poi_id: 'osm:node/mock-bv-bach-mai',
    name: 'Bệnh viện Bạch Mai',
    aliases: ['bach mai', 'bệnh viện bạch mai'],
    category: 'amenity=hospital',
    address_text: '78 Giải Phóng, Đống Đa',
    context_text: 'Phương Mai',
    ranking_point: { lat: 20.9995, lon: 105.8402 },
    routing_point: null,
    pickup_access_verified: false,
  },
  {
    poi_id: 'osm:node/mock-ga-hn',
    name: 'Ga Hà Nội',
    aliases: ['ga ha noi', 'hanoi station'],
    category: 'railway=station',
    address_text: '120 Lê Duẩn, Hoàn Kiếm',
    context_text: 'Ga trung tâm',
    ranking_point: { lat: 21.0245, lon: 105.8412 },
    routing_point: null,
    pickup_access_verified: false,
  },
  {
    poi_id: 'osm:node/mock-aeon-hd',
    name: 'AEON Mall Hà Đông',
    aliases: ['aeon', 'aeon ha dong'],
    category: 'shop=mall',
    address_text: 'Dương Nội, Hà Đông',
    context_text: 'Hà Đông',
    ranking_point: { lat: 20.986, lon: 105.7505 },
    routing_point: null,
    pickup_access_verified: false,
  },
  {
    poi_id: 'osm:node/mock-vincom-bd',
    name: 'Vincom Center Bà Triệu',
    aliases: ['vincom', 'vincom ba trieu'],
    category: 'shop=mall',
    address_text: '191 Bà Triệu, Hai Bà Trưng',
    context_text: 'Hai Bà Trưng',
    ranking_point: { lat: 21.0188, lon: 105.8495 },
    routing_point: null,
    pickup_access_verified: false,
  },
  {
    poi_id: 'osm:node/mock-starbucks-tt',
    name: 'Starbucks — Tràng Tiền',
    aliases: ['starbucks', 'starbucks trang tien'],
    category: 'amenity=cafe',
    address_text: 'Tràng Tiền, Hoàn Kiếm',
    ranking_point: { lat: 21.0255, lon: 105.8535 },
    context_text: 'Phố đi bộ',
    routing_point: null,
    pickup_access_verified: false,
  },
]

export const MOCK_ORIGINS: OriginItem[] = [
  {
    poi_id: 'osm:node/mock-origin-times-city',
    name: 'Times City',
    ranking_point: { lat: 20.9952, lon: 105.868 },
    pickup_access_verified: false,
  },
  {
    poi_id: 'osm:node/mock-origin-keangnam',
    name: 'Keangnam Hanoi Landmark Tower',
    ranking_point: { lat: 21.017, lon: 105.7838 },
    pickup_access_verified: false,
  },
  {
    poi_id: 'osm:node/mock-origin-royal-city',
    name: 'Royal City',
    ranking_point: { lat: 21.0028, lon: 105.8155 },
    pickup_access_verified: false,
  },
]

export const DEMO_USERS = [
  { demo_user_id: 'demo-user-a', label: 'Demo A — cold user' },
  { demo_user_id: 'demo-user-b', label: 'Demo B — history nhẹ' },
]
