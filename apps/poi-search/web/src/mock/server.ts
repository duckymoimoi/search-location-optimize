import type {
  DemoUser,
  OriginList,
  OriginRef,
  RouteResponse,
  SelectResponse,
  SessionResponse,
  Status,
  SuggestResponse,
} from '../types/api'
import { ApiError } from '../types/api'
import { fold, haversineM, uid } from '../lib/geo'
import {
  CORPUS_VERSION,
  DEFAULT_VERSIONS,
  DEMO_USERS,
  MOCK_ORIGINS,
  MOCK_POIS,
} from './fixtures'

type Exposure = {
  exposure_id: string
  session_id: string
  context_revision: number
  shown_ids: string[]
  displayed: boolean
  created_at: number
}

const state = {
  sessionId: null as string | null,
  exposures: new Map<string, Exposure>(),
  selectCache: new Map<string, SelectResponse>(),
}

function delay(ms = 40 + Math.random() * 80): Promise<void> {
  return new Promise((r) => setTimeout(r, ms))
}

function versions() {
  return { ...DEFAULT_VERSIONS }
}

function matchScore(query: string, poi: (typeof MOCK_POIS)[number]): number {
  const q = fold(query)
  if (!q) return 0
  const name = fold(poi.name)
  const aliases = poi.aliases.map(fold)
  if (name === q || aliases.includes(q)) return 100
  if (name.startsWith(q) || aliases.some((a) => a.startsWith(q))) return 80
  if (name.includes(q) || aliases.some((a) => a.includes(q))) return 60
  const tokens = q.split(/\s+/).filter(Boolean)
  const hit = tokens.filter((t) => name.includes(t) || aliases.some((a) => a.includes(t)))
  return hit.length ? 20 + hit.length * 10 : 0
}

function originPoint(origin: OriginRef): { lat: number; lon: number } | null {
  if (!origin) return null
  if (origin.kind === 'poi') {
    const o = MOCK_ORIGINS.find((x) => x.poi_id === origin.poi_id)
    return o?.ranking_point ?? null
  }
  return origin.point
}

export const mockApi = {
  async createSession(): Promise<SessionResponse> {
    await delay()
    state.sessionId = uid('demo-session')
    return { session_id: state.sessionId }
  },

  async getStatus(): Promise<Status> {
    await delay(20)
    return {
      ready: true,
      versions: versions(),
      coverage_id: 'hanoi-boundary-1903516',
      profile: 'lexical_only',
      capabilities: ['suggest', 'suggest_personalized', 'route_preview_straight_line', 'mock'],
    }
  },

  async listDemoUsers(): Promise<DemoUser[]> {
    await delay(20)
    return DEMO_USERS
  },

  async listOrigins(q: string): Promise<OriginList> {
    await delay()
    const f = fold(q)
    const items = MOCK_ORIGINS.filter((o) => !f || fold(o.name).includes(f))
    return { corpus_version: CORPUS_VERSION, items, next_cursor: null }
  },

  async suggest(input: {
    request_id: string
    session_id: string
    context_revision: number
    query: string
    top_k?: number
    personalized?: boolean
    origin?: OriginRef
    demo_user_id?: string | null
    context_time?: string | null
  }): Promise<SuggestResponse> {
    await delay()
    const started = performance.now()
    const q = input.query.trim()
    const topK = Math.min(5, input.top_k ?? 5)
    const anchor = originPoint(input.origin ?? null)

    let scored = MOCK_POIS.map((p) => ({
      poi: p,
      score: matchScore(q, p),
      dist: anchor ? haversineM(anchor, p.ranking_point) : null,
    })).filter((x) => x.score > 0)

    if (!q) scored = []

    scored.sort((a, b) => {
      if (b.score !== a.score) return b.score - a.score
      if (a.dist != null && b.dist != null) return a.dist - b.dist
      return a.poi.name.localeCompare(b.poi.name, 'vi')
    })

    const results = scored.slice(0, topK).map((x, i) => ({
      poi_id: x.poi.poi_id,
      name: x.poi.name,
      rank: i + 1,
      address_text: x.poi.address_text,
      context_text: x.poi.context_text,
      ranking_point: x.poi.ranking_point,
      routing_point: x.poi.routing_point,
      pickup_access_verified: x.poi.pickup_access_verified,
      ranking_distance_m: x.dist,
    }))

    const exposure_id = results.length ? uid('exp') : null
    if (exposure_id) {
      state.exposures.set(exposure_id, {
        exposure_id,
        session_id: input.session_id,
        context_revision: input.context_revision,
        shown_ids: results.map((r) => r.poi_id),
        displayed: false,
        created_at: Date.now(),
      })
    }

    return {
      request_id: input.request_id,
      context_revision: input.context_revision,
      exposure_id,
      selectable: Boolean(exposure_id),
      versions: versions(),
      scope_summary: {
        mode: input.personalized && anchor ? 'primary_plus_global' : 'global',
        coverage_id: 'hanoi-boundary-1903516',
        primary_region_id: null,
        primary_radius_m: input.personalized && anchor ? 15000 : null,
        notes: input.personalized
          ? ['mock personalized: distance sort after lexical score']
          : ['mock query-only: fixed global corpus Hà Nội'],
      },
      resolved_context_time: input.context_time ?? new Date().toISOString(),
      history_version: input.demo_user_id ? `hist-${input.demo_user_id}` : null,
      candidate_count: results.length,
      results,
      degraded_reasons: [],
      timings_ms: { total: Math.round(performance.now() - started) },
    }
  },

  async markDisplayed(input: {
    session_id: string
    exposure_id: string
    context_revision: number
  }): Promise<{ exposure_id: string; displayed: true }> {
    await delay(15)
    const exp = state.exposures.get(input.exposure_id)
    if (!exp || exp.session_id !== input.session_id) {
      throw new ApiError(404, 'exposure_not_found', 'Exposure không tồn tại', null)
    }
    if (exp.context_revision !== input.context_revision) {
      throw new ApiError(409, 'revision_conflict', 'context_revision không khớp', null)
    }
    exp.displayed = true
    return { exposure_id: exp.exposure_id, displayed: true }
  },

  async select(input: {
    session_id: string
    exposure_id: string
    context_revision: number
    selected_poi_id: string
    idempotency_key: string
  }): Promise<SelectResponse> {
    await delay(20)
    const cacheKey = `${input.session_id}:${input.idempotency_key}`
    const cached = state.selectCache.get(cacheKey)
    if (cached) {
      if (cached.selected_poi_id !== input.selected_poi_id) {
        throw new ApiError(409, 'idempotency_conflict', 'Idempotency key đã dùng với payload khác', null)
      }
      return cached
    }

    const exp = state.exposures.get(input.exposure_id)
    if (!exp || exp.session_id !== input.session_id) {
      throw new ApiError(404, 'exposure_not_found', 'Exposure không tồn tại', null)
    }
    if (exp.context_revision !== input.context_revision) {
      throw new ApiError(409, 'revision_conflict', 'context_revision không khớp', null)
    }
    if (!exp.displayed) {
      throw new ApiError(409, 'not_displayed', 'Phải ACK displayed trước khi select', null)
    }
    if (!exp.shown_ids.includes(input.selected_poi_id)) {
      throw new ApiError(409, 'not_in_exposure', 'POI không nằm trong exposure đã hiển thị', null)
    }

    const resp: SelectResponse = {
      selection_id: uid('sel'),
      exposure_id: input.exposure_id,
      selected_poi_id: input.selected_poi_id,
      corpus_version: CORPUS_VERSION,
      recorded_at: new Date().toISOString(),
      history_version: uid('hist'),
      event_source: 'demo_selection',
    }
    state.selectCache.set(cacheKey, resp)
    return resp
  },

  async routePreview(input: {
    corpus_version: string
    origin_poi_id: string | null
    destination_poi_id: string
  }): Promise<RouteResponse> {
    await delay(25)
    const dest =
      MOCK_POIS.find((p) => p.poi_id === input.destination_poi_id) ??
      MOCK_ORIGINS.find((p) => p.poi_id === input.destination_poi_id)
    if (!dest) {
      throw new ApiError(404, 'poi_not_found', 'Destination không có trong mock corpus', null)
    }

    if (!input.origin_poi_id) {
      return {
        status: 'missing_origin',
        corpus_version: CORPUS_VERSION,
        mode_used: null,
        geometry: null,
        geodesic_distance_m: null,
        route_distance_m: null,
        route_duration_s: null,
        reason: 'missing_origin',
      }
    }

    const origin = MOCK_ORIGINS.find((p) => p.poi_id === input.origin_poi_id)
    if (!origin) {
      return {
        status: 'missing_origin',
        corpus_version: CORPUS_VERSION,
        mode_used: null,
        geometry: null,
        geodesic_distance_m: null,
        route_distance_m: null,
        route_duration_s: null,
        reason: 'origin_not_in_pool',
      }
    }

    const o = origin.ranking_point
    const d = 'ranking_point' in dest ? dest.ranking_point : origin.ranking_point
    const dist = haversineM(o, d)
    return {
      status: 'ok',
      corpus_version: CORPUS_VERSION,
      mode_used: 'straight_line',
      geometry: {
        type: 'LineString',
        coordinates: [
          [o.lon, o.lat],
          [d.lon, d.lat],
        ],
      },
      geodesic_distance_m: Math.round(dist),
      route_distance_m: null,
      route_duration_s: null,
      reason: 'straight_line_illustration_not_road_route',
    }
  },
}
