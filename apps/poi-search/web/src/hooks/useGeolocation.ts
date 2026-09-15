import { useEffect, useRef, useState } from 'react'
import type { MapPoint } from '../types/api'

export type GpsState =
  | { status: 'idle' }
  | { status: 'pending' }
  | { status: 'ready'; point: MapPoint; accuracy_m: number; observed_at: string }
  | { status: 'denied'; message: string }
  | { status: 'error'; message: string }
  | { status: 'stale'; point: MapPoint; accuracy_m: number; observed_at: string; message: string }

const MAX_AGE_MS = 120_000
const MAX_ACCURACY_M = 200

export function useGeolocation(): GpsState {
  const [state, setState] = useState<GpsState>({ status: 'pending' })
  const watchId = useRef<number | null>(null)

  useEffect(() => {
    if (!('geolocation' in navigator)) {
      setState({ status: 'error', message: 'Trình duyệt không hỗ trợ GPS' })
      return
    }

    const apply = (pos: GeolocationPosition) => {
      const point = { lat: pos.coords.latitude, lon: pos.coords.longitude }
      const accuracy_m = pos.coords.accuracy
      const observed_at = new Date(pos.timestamp).toISOString()
      const age = Date.now() - pos.timestamp
      if (accuracy_m > MAX_ACCURACY_M) {
        setState({
          status: 'stale',
          point,
          accuracy_m,
          observed_at,
          message: `GPS accuracy ${Math.round(accuracy_m)} m > ${MAX_ACCURACY_M} m — không dùng cho scope`,
        })
        return
      }
      if (age > MAX_AGE_MS) {
        setState({
          status: 'stale',
          point,
          accuracy_m,
          observed_at,
          message: 'GPS quá cũ — bỏ khỏi geo policy',
        })
        return
      }
      setState({ status: 'ready', point, accuracy_m, observed_at })
    }

    const onError = (err: GeolocationPositionError) => {
      if (err.code === err.PERMISSION_DENIED) {
        setState({ status: 'denied', message: 'Bạn đã từ chối quyền vị trí' })
      } else {
        setState({ status: 'error', message: err.message || 'Không lấy được GPS' })
      }
    }

    setState({ status: 'pending' })
    navigator.geolocation.getCurrentPosition(apply, onError, {
      enableHighAccuracy: true,
      timeout: 12_000,
      maximumAge: 30_000,
    })
    watchId.current = navigator.geolocation.watchPosition(apply, onError, {
      enableHighAccuracy: true,
      maximumAge: 15_000,
    })

    return () => {
      if (watchId.current != null) navigator.geolocation.clearWatch(watchId.current)
    }
  }, [])

  return state
}

export function gpsLabel(gps: GpsState): string {
  switch (gps.status) {
    case 'pending':
    case 'idle':
      return 'Đang lấy vị trí…'
    case 'ready':
      return `GPS ±${Math.round(gps.accuracy_m)} m`
    case 'stale':
      return gps.message
    case 'denied':
    case 'error':
      return gps.message
  }
}
