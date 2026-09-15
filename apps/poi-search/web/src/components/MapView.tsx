import { useEffect, useRef, useState } from 'react'
import type { FeatureCollection } from 'geojson'
import * as maplibregl from 'maplibre-gl'
import type { Map as MaplibreMap, Marker } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { MapPoint, Result } from '../types/api'

type Props = {
  results: Result[]
  hoveredId: string | null
  selectedId: string | null
  originPoint: MapPoint | null
  routeCoordinates?: [number, number][] | null
  flyToken?: number
}

const STYLE =
  (import.meta.env.VITE_MAP_STYLE_URL as string) ||
  'https://tiles.openfreemap.org/styles/bright'
const CENTER: [number, number] = [
  Number(import.meta.env.VITE_MAP_CENTER_LON ?? 105.8542),
  Number(import.meta.env.VITE_MAP_CENTER_LAT ?? 21.0285),
]
const ZOOM = Number(import.meta.env.VITE_MAP_ZOOM ?? 12)
/** Street-level zoom when user picks a result. */
const SELECT_ZOOM = 17

function makeNumberedEl(rank: number, active: boolean, selected: boolean): HTMLDivElement {
  const el = document.createElement('div')
  el.className = `poi-marker${active ? ' is-active' : ''}${selected ? ' is-selected' : ''}`
  el.textContent = String(rank)
  return el
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

  // Soft wide underlay (fake glow) + thinner core — both under labels.
  if (!map.getLayer('route-line-soft')) {
    map.addLayer(
      {
        id: 'route-line-soft',
        type: 'line',
        source: 'route',
        layout: { 'line-join': 'round', 'line-cap': 'round' },
        paint: {
          'line-color': '#4d8dff',
          'line-width': 10,
          'line-opacity': 0.22,
          'line-blur': 2.5,
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
          'line-width': 4.5,
          'line-opacity': 0.55,
          'line-blur': 0.4,
        },
      },
      beforeId,
    )
  }

  // Re-stack under labels if style/layers shifted.
  if (beforeId && map.getLayer(beforeId)) {
    if (map.getLayer('route-approach-line')) map.moveLayer('route-approach-line', beforeId)
    if (map.getLayer('route-line-soft')) map.moveLayer('route-line-soft', beforeId)
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
  flyToken = 0,
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<MaplibreMap | null>(null)
  const markersRef = useRef<Marker[]>([])
  const originMarkerRef = useRef<Marker | null>(null)
  const didFlyToGps = useRef(false)
  const routeRef = useRef(routeCoordinates)
  routeRef.current = routeCoordinates
  const originRef = useRef(originPoint)
  originRef.current = originPoint
  const [mapReady, setMapReady] = useState(false)

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return
    const container = containerRef.current
    const map = new maplibregl.Map({
      container,
      style: STYLE,
      center: CENTER,
      zoom: ZOOM,
    })
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    map.on('error', (e) => {
      console.error('[maplibre]', e.error ?? e)
    })
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
      originMarkerRef.current?.remove()
      setMapReady(false)
      map.remove()
      mapRef.current = null
    }
  }, [])

  // Update markers without moving the camera while the user is typing.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !mapReady) return

    markersRef.current.forEach((m) => m.remove())
    markersRef.current = results.map((r) => {
      const el = makeNumberedEl(
        r.rank,
        r.poi_id === hoveredId,
        r.poi_id === selectedId,
      )
      return new maplibregl.Marker({ element: el })
        .setLngLat([r.ranking_point.lon, r.ranking_point.lat])
        .addTo(map)
    })
  }, [results, hoveredId, selectedId, originPoint, mapReady])

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

  useEffect(() => {
    if (!flyToken || !originPoint || !mapRef.current || !mapReady) return
    mapRef.current.flyTo({
      center: [originPoint.lon, originPoint.lat],
      zoom: 15,
      duration: 700,
    })
  }, [flyToken, originPoint, mapReady])

  // Draw / clear road route + dashed GPS→route approach once style is ready.
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

      if (collection.features.length > 0 && coords && coords.length >= 2) {
        const bounds = new maplibregl.LngLatBounds(
          coords[0] as [number, number],
          coords[0] as [number, number],
        )
        for (const coord of coords) bounds.extend(coord as [number, number])
        if (origin) bounds.extend([origin.lon, origin.lat])
        map.fitBounds(bounds, { padding: 72, maxZoom: 16, duration: 900 })
      }
    } catch (err) {
      console.error('[maplibre] route layer', err)
    }
  }, [routeCoordinates, originPoint, mapReady])

  return <div className="map-root" ref={containerRef} />
}
