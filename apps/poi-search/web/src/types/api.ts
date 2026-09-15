export type MapPoint = {
  lat: number
  lon: number
}

export type Versions = {
  release_id: string
  corpus_version: string
  index_version: string
  encoder_id: string | null
  embedding_space_id: string | null
  passage_builder_version: string
  scope_policy_version: string
  candidate_policy_version: string
  ranker_id: string
  feature_version: string
}

export type ScopeSummary = {
  mode: string
  coverage_id: string
  primary_region_id: string | null
  primary_radius_m: number | null
  notes: string[]
}

export type Result = {
  poi_id: string
  name: string
  rank: number
  address_text: string
  context_text: string
  ranking_point: MapPoint
  routing_point: MapPoint | null
  pickup_access_verified: boolean
  ranking_distance_m: number | null
}

export type SuggestResponse = {
  request_id: string
  context_revision: number
  exposure_id: string | null
  selectable: boolean
  versions: Versions
  scope_summary: ScopeSummary
  resolved_context_time: string
  history_version: string | null
  candidate_count: number
  results: Result[]
  degraded_reasons: string[]
  timings_ms: Record<string, number>
}

export type OriginItem = {
  poi_id: string
  name: string
  ranking_point: MapPoint
  pickup_access_verified: boolean
}

export type OriginList = {
  corpus_version: string
  items: OriginItem[]
  next_cursor: string | null
}

export type DemoUser = {
  demo_user_id: string
  label: string
}

export type Status = {
  ready: boolean
  versions: Versions
  coverage_id: string
  profile: 'lexical_only' | 'dense_only' | 'hybrid' | 'personalized'
  capabilities: string[]
}

export type SessionResponse = {
  session_id: string
}

export type SelectResponse = {
  selection_id: string
  exposure_id: string
  selected_poi_id: string
  corpus_version: string
  recorded_at: string
  history_version: string
  event_source: 'demo_selection'
}

export type RouteResponse = {
  status: 'ok' | 'missing_origin' | 'unavailable'
  corpus_version: string
  mode_used: 'straight_line' | 'road' | null
  geometry: {
    type: 'LineString'
    coordinates: [number, number][]
  } | null
  geodesic_distance_m: number | null
  route_distance_m: number | null
  route_duration_s: number | null
  reason: string | null
}

export type OriginRef =
  | { kind: 'poi'; poi_id: string }
  | { kind: 'map'; point: MapPoint }
  | { kind: 'gps'; point: MapPoint; accuracy_m: number; observed_at: string }
  | null

export type Mode = 'query_only' | 'personalized'

export class ApiError extends Error {
  code: string
  status: number
  request_id: string | null

  constructor(status: number, code: string, message: string, request_id: string | null = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.request_id = request_id
  }
}
