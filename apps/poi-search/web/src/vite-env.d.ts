/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_USE_MOCK?: string
  readonly VITE_API_BASE_URL?: string
  readonly VITE_MAP_STYLE_URL?: string
  readonly VITE_MAP_CENTER_LON?: string
  readonly VITE_MAP_CENTER_LAT?: string
  readonly VITE_MAP_ZOOM?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
