import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // MapLibre v6 starts its worker as an ES module (`type: 'module'`), so the
  // worker bundle built for it must be ESM too.
  worker: { format: 'es' },
  server: {
    port: 5173,
    proxy: {
      '/chat': 'http://localhost:8000',
      '/library': 'http://localhost:8000',
      '/reports': 'http://localhost:8000',
      '/research': 'http://localhost:8000',
      '/health': 'http://localhost:8000'
    }
  }
})
