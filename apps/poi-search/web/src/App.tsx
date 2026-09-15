import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from './api/client'
import { MapView } from './components/MapView'
import { DebugDrawer } from './components/DebugDrawer'
import { SearchSheet } from './components/SearchSheet'
import { formatDistance, haversineM, uid } from './lib/geo'
import { gpsLabel, useGeolocation } from './hooks/useGeolocation'
import type { OriginRef, Result, Status, SuggestResponse } from './types/api'
import { ApiError } from './types/api'
import './styles.css'

const DEBOUNCE_MS = 120

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
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [routeCoordinates, setRouteCoordinates] = useState<[number, number][] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)
  const [debugOpen, setDebugOpen] = useState(false)
  const [mapFlyToken, setMapFlyToken] = useState(0)

  const abortRef = useRef<AbortController | null>(null)
  const seqRef = useRef(0)
  const displayedFor = useRef<string | null>(null)

  const originPoint = useMemo(() => {
    if (gps.status === 'ready' || gps.status === 'stale') return gps.point
    return null
  }, [gps])

  const originRef: OriginRef = useMemo(() => {
    if (gps.status !== 'ready') return null
    return {
      kind: 'gps',
      point: gps.point,
      accuracy_m: gps.accuracy_m,
      observed_at: gps.observed_at,
    }
  }, [gps])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const [s, st] = await Promise.all([api.createSession(), api.getStatus()])
        if (cancelled) return
        setSessionId(s.session_id)
        setStatus(st)
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

  // New query → drop previous selection/route (do not clear on every suggest refresh).
  useEffect(() => {
    setSelectedId(null)
    setRouteCoordinates(null)
    displayedFor.current = null
  }, [debouncedQuery])

  // GPS ready → bump revision once so suggest re-runs with distance
  const gpsReadyKey =
    gps.status === 'ready' ? `${gps.point.lat.toFixed(5)},${gps.point.lon.toFixed(5)}` : ''
  useEffect(() => {
    if (!gpsReadyKey) return
    setContextRevision((r) => r + 1)
    setNote('Đã gắn origin từ GPS hiện tại.')
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
        const resp = await api.suggestPersonalized({
          request_id,
          session_id: sessionId,
          context_revision: contextRevision,
          query: q,
          origin: originRef,
          demo_user_id: null,
          context_time: null,
          signal: ac.signal,
        })
        if (seq !== seqRef.current) return
        setLastSuggest(resp)
        setResults(resp.results)

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
  }, [sessionId, debouncedQuery, contextRevision, originRef, sheetOpen])

  const onSelectResult = async (poiId: string) => {
    if (!sessionId || !lastSuggest?.exposure_id) return
    setError(null)
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
      setSelectedId(poiId)
      setSheetOpen(false)

      const hit = results.find((r) => r.poi_id === poiId)
      if (hit && originPoint) {
        try {
          const route = await api.routePreview({
            corpus_version: status?.versions.corpus_version ?? 'hn-poi-stable-v1',
            origin_point: { lat: originPoint.lat, lon: originPoint.lon },
            destination_point: {
              lat: hit.ranking_point.lat,
              lon: hit.ranking_point.lon,
            },
            destination_poi_id: poiId,
            mode: 'road',
            vehicle: 'bike',
            allow_fallback: true,
          })
          if (route.status === 'ok' && route.geometry?.coordinates?.length) {
            const coords = route.geometry.coordinates as [number, number][]
            setRouteCoordinates(coords)
            const road =
              route.route_distance_m != null
                ? formatDistance(route.route_distance_m)
                : formatDistance(Math.round(haversineM(originPoint, hit.ranking_point)))
            const eta =
              route.route_duration_s != null
                ? ` · ~${Math.max(1, Math.round(route.route_duration_s / 60))} phút`
                : ''
            setNote(`${road} · xe máy${eta}`)
          } else {
            setRouteCoordinates(null)
            const dist = Math.round(haversineM(originPoint, hit.ranking_point))
            setResults((prev) =>
              prev.map((r) => (r.poi_id === poiId ? { ...r, ranking_distance_m: dist } : r)),
            )
            setNote(
              `Đã chọn · ${formatDistance(dist)} (chim bay)${
                route.reason ? ` · ${route.reason}` : ''
              }`,
            )
          }
        } catch (e) {
          setRouteCoordinates(null)
          const dist = Math.round(haversineM(originPoint, hit.ranking_point))
          const detail =
            e instanceof ApiError ? ` · ${e.code}` : e instanceof Error ? ` · ${e.message}` : ''
          setNote(`Đã chọn · ${formatDistance(dist)} từ vị trí hiện tại${detail}`)
        }
      } else {
        setRouteCoordinates(null)
        setNote('Đã chọn destination (cần GPS để vẽ đường)')
      }
    } catch (e) {
      if (e instanceof ApiError) setError(`${e.status} ${e.code}: ${e.message}`)
      else setError(e instanceof Error ? e.message : String(e))
    }
  }

  const onRecenterGps = useCallback(() => {
    setMapFlyToken((n) => n + 1)
    if (gps.status === 'ready') {
      setNote('Đã căn map theo GPS hiện tại')
    }
  }, [gps.status])

  return (
    <div className="app-shell maps-like">
      <div className="map-full">
        <MapView
          results={results}
          hoveredId={hoveredId}
          selectedId={selectedId}
          originPoint={originPoint}
          routeCoordinates={routeCoordinates}
          flyToken={mapFlyToken}
        />
      </div>

      <div className="overlay-ui">
        <SearchSheet
          open={sheetOpen}
          query={query}
          loading={loading}
          results={results}
          hoveredId={hoveredId}
          selectedId={selectedId}
          gpsLabel={gpsLabel(gps)}
          gpsOk={gps.status === 'ready'}
          onOpen={() => setSheetOpen(true)}
          onClose={() => setSheetOpen(false)}
          onQueryChange={setQuery}
          onCompositionStart={() => setComposing(true)}
          onCompositionEnd={(v) => {
            setComposing(false)
            setQuery(v)
          }}
          onHover={setHoveredId}
          onSelect={onSelectResult}
          onRecenterGps={onRecenterGps}
        />
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
