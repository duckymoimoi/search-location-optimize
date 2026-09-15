import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // Same-origin so session cookies work whether the UI is opened as
      // localhost or 127.0.0.1 (and on alternate Vite ports).
      '/v1': 'http://127.0.0.1:8000',
      '/health': 'http://127.0.0.1:8000',
    },
  },
  optimizeDeps: {
    // Avoid broken prebundle of the MapLibre web worker (white map / missing tiles).
    exclude: ['maplibre-gl'],
  },
  worker: {
    format: 'es',
  },
})
