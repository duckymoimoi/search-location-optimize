import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from './api/client'
import { MapView } from './components/MapView'
import { DebugDrawer } from './components/DebugDrawer'
import { SearchSheet } from './components/SearchSheet'
import { TopBar } from './components/TopBar'
import { formatDistance, haversineM, uid } from './lib/geo'
import { useGeolocation } from './hooks/useGeolocation'
import type { DemoUser, Mode, OriginRef, Result, Status, SuggestResponse } from './types/api'
import { ApiError } from './types/api'
import './styles.css'

const DEBOUNCE_MS = 120
const FE_TOP_K = 10
const DEFAULT_DEMO_USER = 'demo-cold'

type Field = 'origin' | 'destination'
type PlaceChoice = { kind: 'gps' } | { kind: 'poi'; poi: Result }

export default function App() {
  const gps = useGeolocation()
  const [status, setStatus] = useState<Status | null>(null)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [contextRevision, setContextRevision] = useState(1)
  const [sheetOpen, setSheetOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [composing, setComposing] = useState(false)
  const [debouncedQuery, setDebouncedQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [results, setResults] = useState<Result[]>([])
  const [lastSuggest, setLastSuggest] = useState<SuggestResponse | null>(null)
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  const [activeField, setActiveField] = useState<Field>('destination')
  const [originChoice, setOriginChoice] = useState<PlaceChoice>({ kind: 'gps' })
  const [destination, setDestination] = useState<Result | null>(null)
  const [routeCoordinates, setRouteCoordinates] = useState<[number, number][] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)
  const [debugOpen, setDebugOpen] = useState(false)
  const [mode, setMode] = useState<Mode>('personalized')
  const [demoUsers, setDemoUsers] = useState<DemoUser[]>([])
  const [demoUserId, setDemoUserId] = useState(DEFAULT_DEMO_USER)

  const abortRef = useRef<AbortController | null>(null)
  const seqRef = useRef(0)
  const displayedFor = useRef<string | null>(null)

  const originPoint = useMemo(() => {
    if (originChoice.kind === 'poi') return originChoice.poi.ranking_point
    if (gps.status === 'ready' || gps.status === 'stale') return gps.point
    return null
  }, [originChoice, gps])

  const originRef: OriginRef = useMemo(() => {
    if (originChoice.kind === 'poi') {
      return { kind: 'map', point: originChoice.poi.ranking_point }
    }
    if (gps.status !== 'ready') return null
    return {
      kind: 'gps',
      point: gps.point,
      accuracy_m: gps.accuracy_m,
      observed_at: gps.observed_at,
    }
  }, [originChoice, gps])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const [s, st, users] = await Promise.all([
          api.createSession(),
          api.getStatus(),
          api.listDemoUsers(),
        ])
        if (cancelled) return
        setSessionId(s.session_id)
        setStatus(st)
        setDemoUsers(users)
        if (users.length && !users.some((user) => user.demo_user_id === DEFAULT_DEMO_USER)) {
          setDemoUserId(users[0].demo_user_id)
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e))
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (composing) return
    const t = window.setTimeout(() => setDebouncedQuery(query), DEBOUNCE_MS)
    return () => window.clearTimeout(t)
  }, [query, composing])

  useEffect(() => {
    displayedFor.current = null
  }, [debouncedQuery])

  const contextKey = `${mode}|${demoUserId}`
  const seenContext = useRef(contextKey)
  useEffect(() => {
    if (seenContext.current === contextKey) return
    seenContext.current = contextKey
    setContextRevision((r) => r + 1)
    setDestination(null)
    setRouteCoordinates(null)
    displayedFor.current = null
  }, [contextKey])

  // GPS ready → bump revision once so suggest re-runs with distance
  const gpsReadyKey =
    gps.status === 'ready' ? `${gps.point.lat.toFixed(5)},${gps.point.lon.toFixed(5)}` : ''
  useEffect(() => {
    if (!gpsReadyKey) return
    setContextRevision((r) => r + 1)
  }, [gpsReadyKey])

  useEffect(() => {
    if (!sessionId || !sheetOpen) return
    const q = debouncedQuery.trim()
    abortRef.current?.abort()
    const ac = new AbortController()
    abortRef.current = ac
    const seq = ++seqRef.current
    const request_id = uid('req')

    if (!q) {
      setResults([])
      setLastSuggest(null)
      setLoading(false)
      return
    }

    setLoading(true)
    setError(null)
    ;(async () => {
      try {
        const resp =
          mode === 'query_only'
            ? await api.suggestQueryOnly({
                request_id,
                session_id: sessionId,
                context_revision: contextRevision,
                query: q,
                top_k: FE_TOP_K,
                signal: ac.signal,
              })
            : await api.suggestPersonalized({
                request_id,
                session_id: sessionId,
                context_revision: contextRevision,
                query: q,
                top_k: FE_TOP_K,
                origin: originRef,
                demo_user_id: demoUserId,
                context_time: null,
                signal: ac.signal,
              })
        if (seq !== seqRef.current) return
        setLastSuggest(resp)
        setResults(resp.results.slice(0, FE_TOP_K))

        if (resp.exposure_id && resp.selectable) {
          await api.markDisplayed({
            session_id: sessionId,
            exposure_id: resp.exposure_id,
            context_revision: resp.context_revision,
          })
          displayedFor.current = resp.exposure_id
        }
      } catch (e) {
        if (ac.signal.aborted) return
        if (e instanceof ApiError) setError(`${e.status} ${e.code}: ${e.message}`)
        else setError(e instanceof Error ? e.message : String(e))
      } finally {
        if (seq === seqRef.current) setLoading(false)
      }
    })()

    return () => ac.abort()
  }, [sessionId, debouncedQuery, contextRevision, originRef, sheetOpen, mode, demoUserId])

  const previewRoute = async (from: { lat: number; lon: number }, to: Result) => {
    try {
      const route = await api.routePreview({
        corpus_version: status?.versions.corpus_version ?? 'vn-poi-core-v3-semantic-address-dedup50',
        origin_point: { lat: from.lat, lon: from.lon },
        destination_point: { lat: to.ranking_point.lat, lon: to.ranking_point.lon },
        destination_poi_id: to.poi_id,
        mode: 'road',
        vehicle: 'bike',
        allow_fallback: true,
      })
      if (route.status === 'ok' && route.geometry?.coordinates?.length) {
        setRouteCoordinates(route.geometry.coordinates as [number, number][])
        const road =
          route.route_distance_m != null
            ? formatDistance(route.route_distance_m)
            : formatDistance(Math.round(haversineM(from, to.ranking_point)))
        const eta =
          route.route_duration_s != null
            ? ` · ~${Math.max(1, Math.round(route.route_duration_s / 60))} phút`
            : ''
        setNote(`${road} · xe máy${eta}`)
        return
      }
      setRouteCoordinates(null)
      const dist = Math.round(haversineM(from, to.ranking_point))
      setNote(
        `Đã chọn · ${formatDistance(dist)} (chim bay)${route.reason ? ` · ${route.reason}` : ''}`,
      )
    } catch (e) {
      setRouteCoordinates(null)
      const dist = Math.round(haversineM(from, to.ranking_point))
      const detail = e instanceof ApiError ? ` · ${e.code}` : e instanceof Error ? ` · ${e.message}` : ''
      setNote(`Đã chọn · ${formatDistance(dist)}${detail}`)
    }
  }

  const onActivate = (field: Field) => {
    if (field !== activeField) setQuery('')
    setActiveField(field)
    setSheetOpen(true)
  }

  const onSelectCurrentLocation = () => {
    setOriginChoice({ kind: 'gps' })
    setQuery('')
    if (!destination) {
      setActiveField('destination')
      return
    }
    if (gps.status === 'ready' || gps.status === 'stale') {
      void previewRoute(gps.point, destination)
    }
  }

  const onSelectResult = async (poiId: string) => {
    const hit = results.find((item) => item.poi_id === poiId)
    if (!hit) return
    setError(null)
    if (activeField === 'origin') {
      setOriginChoice({ kind: 'poi', poi: hit })
      setQuery('')
      if (!destination) setActiveField('destination')
      else void previewRoute(hit.ranking_point, destination)
      return
    }
    if (!sessionId || !lastSuggest?.exposure_id) return
    try {
      if (displayedFor.current !== lastSuggest.exposure_id) {
        await api.markDisplayed({
          session_id: sessionId,
          exposure_id: lastSuggest.exposure_id,
          context_revision: lastSuggest.context_revision,
        })
        displayedFor.current = lastSuggest.exposure_id
      }
      await api.select({
        session_id: sessionId,
        exposure_id: lastSuggest.exposure_id,
        context_revision: lastSuggest.context_revision,
        selected_poi_id: poiId,
        idempotency_key: uid('idem'),
      })
      setDestination(hit)
      setSheetOpen(false)
      if (originPoint) await previewRoute(originPoint, hit)
      else setNote('Đã chọn điểm đến. Cần điểm đi để vẽ đường.')
    } catch (e) {
      if (e instanceof ApiError) setError(`${e.status} ${e.code}: ${e.message}`)
      else setError(e instanceof Error ? e.message : String(e))
    }
  }

  return (
    <div className="app-shell maps-like">
      <div className="map-full">
        <MapView
          results={results}
          hoveredId={hoveredId}
          selectedId={destination?.poi_id ?? null}
          originPoint={originPoint}
          routeCoordinates={routeCoordinates}
        />
      </div>

      <div className="overlay-ui">
        <div className="overlay-stack">
        <TopBar
          mode={mode}
          onMode={setMode}
          status={status}
          users={demoUsers}
          demoUserId={demoUserId}
          onDemoUser={setDemoUserId}
        />
        <SearchSheet
          open={sheetOpen}
          query={query}
          loading={loading}
          results={results}
          hoveredId={hoveredId}
          selectedId={
            activeField === 'origin' && originChoice.kind === 'poi'
              ? originChoice.poi.poi_id
              : destination?.poi_id ?? null
          }
          activeField={activeField}
          originLabel={originChoice.kind === 'gps' ? 'Vị trí hiện tại' : originChoice.poi.name}
          destinationLabel={destination?.name ?? 'Chọn điểm đến'}
          originIsCurrent={originChoice.kind === 'gps'}
          onActivate={onActivate}
          onSelectCurrentLocation={onSelectCurrentLocation}
          onClose={() => setSheetOpen(false)}
          onQueryChange={setQuery}
          onCompositionStart={() => setComposing(true)}
          onCompositionEnd={(v) => {
            setComposing(false)
            setQuery(v)
          }}
          onHover={setHoveredId}
          onSelect={onSelectResult}
        />
        </div>
        {note ? (
          <div className="status-pill">
            <span className="status-note">{note}</span>
          </div>
        ) : null}
      </div>

      <DebugDrawer
        open={debugOpen}
        onToggle={() => setDebugOpen((v) => !v)}
        last={lastSuggest}
        error={error}
        note={note}
      />
    </div>
  )
}
