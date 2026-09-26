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

const BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '') ?? ''
const CORPUS_VERSION =
  (import.meta.env.VITE_CORPUS_VERSION as string | undefined)?.trim() || 'vn-poi-core-v3-semantic-address-dedup50'

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    ...init,
  })
  if (!res.ok) {
    let code = `http_${res.status}`
    let message = res.statusText
    let request_id: string | null = null
    try {
      const body = (await res.json()) as { code?: string; message?: string; request_id?: string | null }
      code = body.code ?? code
      message = body.message ?? message
      request_id = body.request_id ?? null
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, code, message, request_id)
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

export const api = {
  createSession(): Promise<SessionResponse> {
    return http('/v1/sessions', { method: 'POST', body: '{}' })
  },

  getStatus(): Promise<Status> {
    return http('/v1/status')
  },

  listDemoUsers(): Promise<DemoUser[]> {
    return http('/v1/demo/users')
  },

  listOrigins(q: string): Promise<OriginList> {
    const qs = new URLSearchParams({ q, limit: '20' })
    return http(`/v1/origins?${qs}`)
  },

  suggestQueryOnly(input: {
    request_id: string
    session_id: string
    context_revision: number
    query: string
    top_k?: number
    signal?: AbortSignal
  }): Promise<SuggestResponse> {
    return http('/v1/suggest', {
      method: 'POST',
      body: JSON.stringify({
        request_id: input.request_id,
        session_id: input.session_id,
        context_revision: input.context_revision,
        query: input.query,
        top_k: input.top_k ?? 10,
        expected_corpus_version: CORPUS_VERSION,
      }),
      signal: input.signal,
    })
  },

  suggestPersonalized(input: {
    request_id: string
    session_id: string
    context_revision: number
    query: string
    top_k?: number
    origin: OriginRef
    demo_user_id: string | null
    context_time: string | null
    signal?: AbortSignal
  }): Promise<SuggestResponse> {
    return http('/v1/suggest/personalized', {
      method: 'POST',
      body: JSON.stringify({
        request_id: input.request_id,
        session_id: input.session_id,
        context_revision: input.context_revision,
        query: input.query,
        top_k: input.top_k ?? 10,
        expected_corpus_version: CORPUS_VERSION,
        search_kind: 'destination',
        origin: input.origin,
        demo_user_id: input.demo_user_id,
        context_time: input.context_time,
        preferred_region_id: null,
      }),
      signal: input.signal,
    })
  },

  markDisplayed(input: {
    session_id: string
    exposure_id: string
    context_revision: number
  }) {
    return http('/v1/exposures/displayed', {
      method: 'POST',
      body: JSON.stringify(input),
    })
  },

  select(input: {
    session_id: string
    exposure_id: string
    context_revision: number
    selected_poi_id: string
    idempotency_key: string
  }): Promise<SelectResponse> {
    return http('/v1/select', { method: 'POST', body: JSON.stringify(input) })
  },

  routePreview(input: {
    corpus_version: string
    origin_poi_id?: string | null
    destination_poi_id?: string | null
    origin_point?: { lat: number; lon: number } | null
    destination_point?: { lat: number; lon: number } | null
    mode?: 'straight_line' | 'road'
    vehicle?: 'car' | 'bike' | 'taxi' | 'truck' | 'hd'
    allow_fallback?: boolean
  }): Promise<RouteResponse> {
    return http('/v1/route-preview', {
      method: 'POST',
      body: JSON.stringify({
        corpus_version: input.corpus_version,
        origin_poi_id: input.origin_poi_id ?? null,
        destination_poi_id: input.destination_poi_id ?? null,
        origin_point: input.origin_point ?? null,
        destination_point: input.destination_point ?? null,
        mode: input.mode ?? 'road',
        vehicle: input.vehicle ?? 'bike',
        allow_fallback: input.allow_fallback ?? true,
      }),
    })
  },
}
