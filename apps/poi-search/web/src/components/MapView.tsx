import { useEffect, useRef, useState } from 'react'
import type { FeatureCollection } from 'geojson'
import * as maplibregl from 'maplibre-gl'
import { setWorkerUrl } from 'maplibre-gl'
import type { Map as MaplibreMap, Marker, StyleSpecification } from 'maplibre-gl'
import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { MapPoint, Result } from '../types/api'
import { resultSubtitle } from '../lib/resultSubtitle'

// Vite production: bundle worker + shared chunk (plain ?url breaks Goong vector tiles).
setWorkerUrl(maplibreWorkerUrl)

type Props = {
  results: Result[]
  hoveredId: string | null
  selectedId: string | null
  originPoint: MapPoint | null
  routeCoordinates?: [number, number][] | null
}

const GOONG_MAPTILES_KEY = (
  import.meta.env.VITE_GOONG_MAPTILES_KEY as string | undefined
)?.trim()
const GOONG_STYLE =
  'https://tiles.goong.io/assets/goong_map_web.json'

/** Fallback when no Goong Map tiles key (Docker/local without VITE_GOONG_MAPTILES_KEY). */
const FALLBACK_RASTER_STYLE: StyleSpecification = {
  version: 8,
  sources: {
    basemap: {
      type: 'raster',
      tiles: [
        'https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
      ],
      tileSize: 256,
      attribution: '© Esri',
    },
  },
  layers: [{ id: 'basemap', type: 'raster', source: 'basemap' }],
}

function withGoongKey(url: string, key: string): string {
  if (!key || url.includes('api_key=')) return url
  return `${url}${url.includes('?') ? '&' : '?'}api_key=${encodeURIComponent(key)}`
}

function resolveMapStyle(): string | StyleSpecification {
  const override = (import.meta.env.VITE_MAP_STYLE_URL as string | undefined)?.trim()
  if (override) {
    if (GOONG_MAPTILES_KEY && override.includes('tiles.goong.io')) {
      return withGoongKey(override, GOONG_MAPTILES_KEY)
    }
    return override
  }
  if (GOONG_MAPTILES_KEY) return withGoongKey(GOONG_STYLE, GOONG_MAPTILES_KEY)
  return FALLBACK_RASTER_STYLE
}

const STYLE = resolveMapStyle()
const CENTER: [number, number] = [
  Number(import.meta.env.VITE_MAP_CENTER_LON ?? 105.8542),
  Number(import.meta.env.VITE_MAP_CENTER_LAT ?? 21.0285),
]
const ZOOM = Number(import.meta.env.VITE_MAP_ZOOM ?? 12)
/** Street-level zoom when user picks a result. */
const SELECT_ZOOM = 17

const RESULT_PIN_SVG =
  '<svg viewBox="0 0 28 36" width="28" height="36" focusable="false" aria-hidden="true">' +
  '<path d="M14 35S27 23.5 27 13A13 13 0 1 0 1 13c0 10.5 13 22 13 22Z"/>' +
  '<circle cx="14" cy="13" r="5"/></svg>'

function makeResultPinEl(active: boolean, selected: boolean): HTMLDivElement {
  const el = document.createElement('div')
  el.className = `poi-result-pin${active ? ' is-active' : ''}${selected ? ' is-selected' : ''}`
  el.innerHTML = RESULT_PIN_SVG
  return el
}

function ensurePoiCatalogLayers(map: MaplibreMap) {
  if (!map.getSource('poi-catalog')) {
    map.addSource('poi-catalog', {
      type: 'geojson',
      data: '/v1/map/pois',
      cluster: true,
      clusterMaxZoom: 15,
      clusterRadius: 42,
    })
  }
  if (!map.getLayer('poi-catalog-clusters')) {
    map.addLayer({
      id: 'poi-catalog-clusters',
      type: 'circle',
      source: 'poi-catalog',
      filter: ['has', 'point_count'],
      paint: {
        'circle-color': '#dc2626',
        'circle-opacity': 0.38,
        'circle-stroke-color': '#fff',
        'circle-stroke-width': 1.5,
        'circle-radius': ['step', ['get', 'point_count'], 7, 20, 10, 100, 14],
      },
    })
  }
  if (!map.getLayer('poi-catalog-points')) {
    map.addLayer({
      id: 'poi-catalog-points',
      type: 'circle',
      source: 'poi-catalog',
      filter: ['!', ['has', 'point_count']],
      paint: {
        'circle-color': '#dc2626',
        'circle-opacity': 0.6,
        'circle-stroke-color': '#fff',
        'circle-stroke-width': 0.8,
        'circle-radius': 3.5,
      },
    })
  }
}

function makePoiPopup(properties: Record<string, unknown>): HTMLDivElement {
  const root = document.createElement('div')
  root.className = 'poi-map-popup'
  const name = document.createElement('strong')
  name.textContent = String(properties.name || 'POI')
  root.appendChild(name)
  const address = String(properties.address || '').trim()
  if (address) {
    const line = document.createElement('span')
    line.textContent = address
    root.appendChild(line)
  }
  return root
}

function routeCollection(
  coords: [number, number][] | null | undefined,
): FeatureCollection {
  if (!coords || coords.length < 2) {
    return { type: 'FeatureCollection', features: [] }
  }
  return {
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        properties: {},
        geometry: { type: 'LineString', coordinates: coords },
      },
    ],
  }
}

/** Keep route under basemap symbol layers so street names stay readable. */
function firstLabelLayerId(map: MaplibreMap): string | undefined {
  const layers = map.getStyle()?.layers
  if (!layers) return undefined
  const withText = layers.find(
    (layer) =>
      layer.type === 'symbol' &&
      !layer.id.startsWith('route-') &&
      Boolean((layer as { layout?: Record<string, unknown> }).layout?.['text-field']),
  )
  if (withText) return withText.id
  const hit = layers.find(
    (layer) =>
      layer.type === 'symbol' &&
      !layer.id.startsWith('route-') &&
      (layer.id.includes('label') ||
        layer.id.includes('place') ||
        layer.id.includes('road_name') ||
        layer.id.includes('highway') ||
        layer.id.includes('poi')),
  )
  return hit?.id ?? layers.find((layer) => layer.type === 'symbol')?.id
}

function ensureRouteLayers(map: MaplibreMap) {
  if (!map.getSource('route')) {
    map.addSource('route', {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: [] },
    })
  }
  if (!map.getSource('route-approach')) {
    map.addSource('route-approach', {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: [] },
    })
  }

  const beforeId = firstLabelLayerId(map)

  // Drop legacy soft-glow layer if a previous session still has it.
  if (map.getLayer('route-line-soft')) map.removeLayer('route-line-soft')

  if (!map.getLayer('route-approach-line')) {
    map.addLayer(
      {
        id: 'route-approach-line',
        type: 'line',
        source: 'route-approach',
        layout: { 'line-join': 'round', 'line-cap': 'round' },
        paint: {
          'line-color': '#2f6fed',
          'line-width': 3.5,
          'line-opacity': 0.45,
          'line-dasharray': [1.4, 1.8],
        },
      },
      beforeId,
    )
  }

  // White casing + blue core — both under labels so street names stay readable.
  const casingWidth: maplibregl.ExpressionSpecification = [
    'interpolate',
    ['linear'],
    ['zoom'],
    12,
    8,
    16,
    12,
  ]
  const coreWidth: maplibregl.ExpressionSpecification = [
    'interpolate',
    ['linear'],
    ['zoom'],
    12,
    4.5,
    16,
    7,
  ]

  if (!map.getLayer('route-line-casing')) {
    map.addLayer(
      {
        id: 'route-line-casing',
        type: 'line',
        source: 'route',
        layout: { 'line-join': 'round', 'line-cap': 'round' },
        paint: {
          'line-color': '#ffffff',
          'line-width': casingWidth,
          'line-opacity': 0.92,
        },
      },
      beforeId,
    )
  }
  if (!map.getLayer('route-line')) {
    map.addLayer(
      {
        id: 'route-line',
        type: 'line',
        source: 'route',
        layout: { 'line-join': 'round', 'line-cap': 'round' },
        paint: {
          'line-color': '#2f6fed',
          'line-width': coreWidth,
          'line-opacity': 0.88,
        },
      },
      beforeId,
    )
  } else {
    map.setPaintProperty('route-line', 'line-width', coreWidth)
    map.setPaintProperty('route-line', 'line-opacity', 0.88)
    map.setPaintProperty('route-line', 'line-blur', 0)
  }

  // Re-stack under labels if style/layers shifted.
  if (beforeId && map.getLayer(beforeId)) {
    if (map.getLayer('route-approach-line')) map.moveLayer('route-approach-line', beforeId)
    if (map.getLayer('route-line-casing')) map.moveLayer('route-line-casing', beforeId)
    if (map.getLayer('route-line')) map.moveLayer('route-line', beforeId)
  }
}

function approachCollection(
  origin: MapPoint | null | undefined,
  routeCoords: [number, number][] | null | undefined,
): FeatureCollection {
  if (!origin || !routeCoords || routeCoords.length < 1) {
    return { type: 'FeatureCollection', features: [] }
  }
  const start = routeCoords[0]
  const originCoord: [number, number] = [origin.lon, origin.lat]
  // Skip a near-zero connector when GPS already sits on the first route vertex.
  const dLon = originCoord[0] - start[0]
  const dLat = originCoord[1] - start[1]
  if (dLon * dLon + dLat * dLat < 1e-12) {
    return { type: 'FeatureCollection', features: [] }
  }
  return {
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        properties: {},
        geometry: {
          type: 'LineString',
          coordinates: [originCoord, start],
        },
      },
    ],
  }
}

export function MapView({
  results,
  hoveredId,
  selectedId,
  originPoint,
  routeCoordinates = null,
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<MaplibreMap | null>(null)
  const markersRef = useRef<Marker[]>([])
  const resultPopupRef = useRef<maplibregl.Popup | null>(null)
  const focusedResultsRef = useRef('')
  const originMarkerRef = useRef<Marker | null>(null)
  const didFlyToGps = useRef(false)
  const routeRef = useRef(routeCoordinates)
  routeRef.current = routeCoordinates
  const originRef = useRef(originPoint)
  originRef.current = originPoint
  /** Fit camera once per route geometry — ignore GPS jitter. */
  const fittedRouteKeyRef = useRef<string | null>(null)
  const [mapReady, setMapReady] = useState(false)

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return
    const container = containerRef.current
    const map = new maplibregl.Map({
      container,
      style: STYLE,
      center: CENTER,
      zoom: ZOOM,
      transformRequest: (url) => {
        if (!GOONG_MAPTILES_KEY) return { url }
        if (!url.includes('goong.io')) return { url }
        return { url: withGoongKey(url, GOONG_MAPTILES_KEY) }
      },
    })
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    map.on('error', (e) => {
      console.error('[maplibre]', e.error ?? e)
    })
    if (!GOONG_MAPTILES_KEY && !import.meta.env.VITE_MAP_STYLE_URL) {
      console.warn(
        '[map] VITE_GOONG_MAPTILES_KEY missing — Esri raster fallback. Set GOONG_MAP_API_KEY for Docker build / web/.env for Vite dev.',
      )
    } else if (GOONG_MAPTILES_KEY) {
      console.info('[map] Goong Map tiles style enabled')
    }
    const markReady = () => {
      map.resize()
      setMapReady(true)
    }
    if (map.isStyleLoaded()) markReady()
    else map.once('load', markReady)

    const ro = new ResizeObserver(() => map.resize())
    ro.observe(container)
    const t1 = window.setTimeout(() => map.resize(), 50)
    const t2 = window.setTimeout(() => map.resize(), 250)

    mapRef.current = map
    return () => {
      window.clearTimeout(t1)
      window.clearTimeout(t2)
      ro.disconnect()
      markersRef.current.forEach((m) => m.remove())
      resultPopupRef.current?.remove()
      originMarkerRef.current?.remove()
      setMapReady(false)
      map.remove()
      mapRef.current = null
    }
  }, [])

  // Render the full catalog through one clustered GeoJSON source. Individual
  // POIs get a name/address popup on hover; search-result markers remain above it.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !mapReady) return
    ensurePoiCatalogLayers(map)
    const popup = new maplibregl.Popup({
      closeButton: false,
      closeOnClick: false,
      offset: 12,
    })

    const onEnter = () => {
      map.getCanvas().style.cursor = 'pointer'
    }
    const onLeave = () => {
      map.getCanvas().style.cursor = ''
      popup.remove()
    }
    const onMove = (event: any) => {
      const feature = event.features?.[0]
      if (!feature || feature.geometry?.type !== 'Point') return
      popup
        .setLngLat(event.lngLat)
        .setDOMContent(makePoiPopup(feature.properties || {}))
        .addTo(map)
    }
    const onClusterClick = async (event: any) => {
      const feature = event.features?.[0]
      const clusterId = feature?.properties?.cluster_id
      const source = map.getSource('poi-catalog') as maplibregl.GeoJSONSource | undefined
      if (clusterId == null || !source) return
      try {
        const zoom = await source.getClusterExpansionZoom(Number(clusterId))
        const coordinates = feature.geometry?.coordinates
        if (Array.isArray(coordinates)) {
          map.easeTo({ center: coordinates as [number, number], zoom })
        }
      } catch {
        // The cluster may disappear while the map is moving; ignore stale clicks.
      }
    }

    map.on('mouseenter', 'poi-catalog-points', onEnter)
    map.on('mouseleave', 'poi-catalog-points', onLeave)
    map.on('mousemove', 'poi-catalog-points', onMove)
    map.on('click', 'poi-catalog-clusters', onClusterClick)
    return () => {
      map.off('mouseenter', 'poi-catalog-points', onEnter)
      map.off('mouseleave', 'poi-catalog-points', onLeave)
      map.off('mousemove', 'poi-catalog-points', onMove)
      map.off('click', 'poi-catalog-clusters', onClusterClick)
      popup.remove()
      map.getCanvas().style.cursor = ''
    }
  }, [mapReady])

  // Update markers without moving the camera while the user is typing.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !mapReady) return

    markersRef.current.forEach((m) => m.remove())
    const popup =
      resultPopupRef.current ??
      new maplibregl.Popup({
        closeButton: false,
        closeOnClick: false,
        offset: [0, -36],
        anchor: 'bottom',
        maxWidth: '280px',
        className: 'poi-result-popup',
      })
    resultPopupRef.current = popup

    const showResultPopup = (result: Result) => {
      popup
        .setLngLat([result.ranking_point.lon, result.ranking_point.lat])
        .setDOMContent(
          makePoiPopup({
            name: result.name,
            address: resultSubtitle(result),
          }),
        )
        .addTo(map)
    }

    const visibleResults = results.slice(0, 10)
    markersRef.current = visibleResults.map((r) => {
      const active = r.poi_id === hoveredId
      const el = makeResultPinEl(active, r.poi_id === selectedId)
      el.addEventListener('mouseenter', () => showResultPopup(r))
      el.addEventListener('mouseleave', () => {
        if (r.poi_id !== hoveredId) popup.remove()
      })
      const marker = new maplibregl.Marker({ element: el, anchor: 'bottom' })
        .setLngLat([r.ranking_point.lon, r.ranking_point.lat])
        .addTo(map)
      if (active) marker.getElement().style.zIndex = '3'
      return marker
    })

    const hovered = visibleResults.find((r) => r.poi_id === hoveredId)
    if (hovered) showResultPopup(hovered)
    else popup.remove()
  }, [results, hoveredId, selectedId, originPoint, mapReady])

  // Keep the current map center. Zoom out, without animation, only when a
  // result pin would otherwise sit outside the view. Never fly to one POI.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !mapReady) return
    if (routeCoordinates && routeCoordinates.length >= 2) return
    const visible = results.slice(0, 10)
    const focusKey = visible.map((result) => result.poi_id).join('|')
    if (!focusKey) {
      focusedResultsRef.current = ''
      return
    }
    if (focusKey === focusedResultsRef.current) return
    const timer = window.setTimeout(() => {
      const current = mapRef.current
      if (!current) return
      focusedResultsRef.current = focusKey
      const center = current.getCenter()
      let spanLon = 0
      let spanLat = 0
      for (const result of visible) {
        spanLon = Math.max(spanLon, Math.abs(result.ranking_point.lon - center.lng))
        spanLat = Math.max(spanLat, Math.abs(result.ranking_point.lat - center.lat))
      }
      if (spanLon === 0 && spanLat === 0) return
      const bounds = new maplibregl.LngLatBounds(
        [center.lng - spanLon * 1.2, center.lat - spanLat * 1.2],
        [center.lng + spanLon * 1.2, center.lat + spanLat * 1.2],
      )
      const camera = current.cameraForBounds(bounds, { padding: 64, maxZoom: current.getZoom() })
      const nextZoom = camera?.zoom
      if (nextZoom == null || current.getZoom() - nextZoom < 0.2) return
      current.jumpTo({ center, zoom: nextZoom })
    }, 500)
    return () => window.clearTimeout(timer)
  }, [results, routeCoordinates, mapReady])

  // Click a result → zoom into that coordinate / street.
  // Skip when a road route is present — fitBounds owns the camera.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !mapReady || !selectedId) return
    if (routeCoordinates && routeCoordinates.length >= 2) return
    const hit = results.find((r) => r.poi_id === selectedId)
    if (!hit) return
    map.flyTo({
      center: [hit.ranking_point.lon, hit.ranking_point.lat],
      zoom: SELECT_ZOOM,
      duration: 900,
      essential: true,
    })
  }, [selectedId, results, routeCoordinates, mapReady])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !mapReady) return
    originMarkerRef.current?.remove()
    originMarkerRef.current = null
    if (!originPoint) return
    const el = document.createElement('div')
    el.className = 'gps-marker'
    el.title = 'Vị trí hiện tại'
    originMarkerRef.current = new maplibregl.Marker({ element: el })
      .setLngLat([originPoint.lon, originPoint.lat])
      .addTo(map)

    if (!didFlyToGps.current && results.length === 0) {
      didFlyToGps.current = true
      map.flyTo({ center: [originPoint.lon, originPoint.lat], zoom: 14, duration: 800 })
    }
  }, [originPoint, results.length, mapReady])

  // Draw / clear road route + dashed GPS→route approach once style is ready.
  // Camera fit only when route geometry changes — GPS watch must not re-zoom.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !mapReady) return
    try {
      ensureRouteLayers(map)
      const routeSource = map.getSource('route') as maplibregl.GeoJSONSource | undefined
      const approachSource = map.getSource('route-approach') as maplibregl.GeoJSONSource | undefined
      if (!routeSource || !approachSource) return

      const coords = routeRef.current
      const origin = originRef.current
      const collection = routeCollection(coords)
      const approach = approachCollection(origin, coords)
      routeSource.setData(collection)
      approachSource.setData(approach)

      if (!coords || coords.length < 2) {
        fittedRouteKeyRef.current = null
        return
      }
      const first = coords[0]
      const last = coords[coords.length - 1]
      const routeKey = `${coords.length}:${first[0]},${first[1]}:${last[0]},${last[1]}`
      if (fittedRouteKeyRef.current === routeKey) return
      fittedRouteKeyRef.current = routeKey

      const bounds = new maplibregl.LngLatBounds(first, first)
      for (const coord of coords) bounds.extend(coord as [number, number])
      if (origin) bounds.extend([origin.lon, origin.lat])
      map.fitBounds(bounds, { padding: 72, maxZoom: 16, duration: 900 })
    } catch (err) {
      console.error('[maplibre] route layer', err)
    }
  }, [routeCoordinates, originPoint, mapReady])

  return <div className="map-root" ref={containerRef} />
}
