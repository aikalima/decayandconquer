import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 6161,
    proxy: {
      "/ai-access": "http://localhost:6173",
      "/data-health": "http://localhost:6173",
      "/app-defaults": "http://localhost:6173",
      "/chat": "http://localhost:6173",
      "/predict": "http://localhost:6173",
      "/predict-stream": "http://localhost:6173",
      "/market-context": "http://localhost:6173",
      "/theta-plays": "http://localhost:6173",
      "/theta-expiries": "http://localhost:6173",
      "/heatmap-stream": "http://localhost:6173",
      "/theta-plays-stream": "http://localhost:6173",
      "/ping": "http://localhost:6173",
    },
  },
})
